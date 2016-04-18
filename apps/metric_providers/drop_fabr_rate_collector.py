'''
Created on Feb 18, 2016
The module monitors switches and links in a network, evaluates the trust
according to some parameters and raise events for publishing the trust evaluation:

- Switch trust :
    - dropping / fabrication rate

@version: 2.0
@author: root
'''

from __future__ import division
from operator import attrgetter
import logging

from ryu.base import app_manager
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.controller import ofp_event 
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.topology import event
from ryu.topology.switches import LLDPCounter



import trustevents
from trust_collector_base import TrustCollectorBase

##### GLOBAL VARIABLE ####

LOG = logging.getLogger(__name__)   # logger for module

TABLE_MISS_PRIORITY = 0             # lowest priority
TABLE_MISS_TB_ID = 0                # table id for miss priority
# misalignement between rx pkts and tabe-miss pkts due to the separate, non synchronized statistics requests 
STAT_REQ_TIMING_THRESH = 5


        
class DropFabrRateCollector(TrustCollectorBase):
    """ Monitor switches port statistics to evaluate:
        - switch drop rate
        - switch fabrication rate
        - link drop rate
    """
    
    SW_TO_CONTR_PORT = 4294967294   # port from switch to controller
    DEFAULT_REQUEST_INTERVAL = 7    # time interval between port stats requests 
    STABILIZATION_PARAM = 10        # stabilize drop and fabr rate. (see line 327)
    
    # events raised by the app
    _EVENTS = [trustevents.EventLinkDropRateUpdate, trustevents.EventFabrRateUpdate]
    
    def __init__(self, *args, **kwargs):
        
        super(DropFabrRateCollector, self).__init__(*args, **kwargs)
        self.name = 'drop_fabr_rate_collector'
        #store a list of connected switches
        self.datapaths = {}         #TODO use only datapaths_stats to track alive switches
        # dict datapths statistics    
        self.datapaths_stats = {}   #TODO thread-safe needed ?
        # link list
        self.link_list = {}
        # counter for pending statistics requests
        self.pending_stats_req = 0      #TODO thread-safe needed ?
        # bool to check if first statistic request
        self.is_first_stat_req = True
        
        self.threads.append( hub.spawn_after(self.LOAD_TIME, self._stats_request_loop) )     
        
        
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        
        datapath = ev.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                
                self.datapaths[datapath.id] = datapath
                self.datapaths_stats.setdefault(datapath.id, SwStatistic(datapath.id)) 
                LOG.info('Register datapath: %016x', datapath.id)                
                
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
                del self.datapaths_stats[datapath.id]
                LOG.info('Unregister datapath: %016x', datapath.id)
                    

    @set_ev_cls(event.EventLinkAdd)
    def new_link_event_handler(self, ev):
        
        LOG.info('DROP-FABR-RATE: New link detected %s -> %s', ev.link.src.dpid, ev.link.dst.dpid)
        
        self.link_list.setdefault( ev.link , )
        #print '***links'
        #print self.link_list

        
    def _stats_request_loop(self):
        
        LOG.info("DROP-FABR-RATE: Starting statistics requests...")
        while True:
            for datapath in self.datapaths.values():
                self._port_stats_request(datapath)
            hub.sleep(self.DEFAULT_REQUEST_INTERVAL)
            self.is_first_stat_req = False

        
    def _port_stats_request(self, datapath):
        
        #LOG.info('SWITCH_EVAL: Port statistic request: dp %016x', datapath.id)
        
        ofproto = datapath.ofproto
        of_parser = datapath.ofproto_parser
                
        # port statistics request
        request = of_parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(request)
        self.pending_stats_req += 1
      
    
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        body = msg.body
        
        #self._log_port_statistics(msg, LOG)
        
        # TODO in case of EventSwitchLeave while a request is pending, the counter is
        #      never reset
        self.pending_stats_req -= 1
        
        # update lldp counter
        sw_ref = app_manager.lookup_service_brick('switches')
        lldp_counter = sw_ref.lldp_count_dict[datapath.id]
        self.datapaths_stats[datapath.id].update_lldp_counter(lldp_counter)
        
        # update port statistics 
        for stat in body:
            if not stat.port_no == self.SW_TO_CONTR_PORT:   # ignore port for controller communication
                
                new_stat = SwStatistic.PortStat(datapath.id, stat.port_no)
                new_stat.rx_pkts = stat.rx_packets
                new_stat.tx_pkts = stat.tx_packets
                self.datapaths_stats[datapath.id].update_port_stat(new_stat, stat.port_no)
        
        # compute drop rate for the switch
        sw_drop_rate, sw_fabr_rate = self.datapaths_stats[datapath.id].get_flow_conservation()
        LOG.info("DROP-FABR-RATE: Flow conservation property for dp %s: drop=%s%%  fabr=%s%%", datapath.id, sw_drop_rate*100, sw_fabr_rate*100) 
              
        if not self.is_first_stat_req:
            # compute drop rate for all links if no requests are pending
            if self.pending_stats_req == 0 :
                self.link_drop_rate()

    
    def link_drop_rate(self):
            
        for link in self.link_list:
            
            src = link.src
            dst = link.dst
            src_sw_statistic = self.datapaths_stats[src.dpid]
            dst_sw_statistic = self.datapaths_stats[dst.dpid]
            src_tw_port_stat = src_sw_statistic.tw_port_stat_dict[src.port_no]
            dst_tw_port_stat = dst_sw_statistic.tw_port_stat_dict[dst.port_no] 
            
            # Note: in the case of link drop rate computation, the lldp pkts are not subtracted from the rx and tx
            # pkts because it doesn't matter which type of packet is dropped in the link.
            src_tx = src_tw_port_stat.tx_pkts
            dst_rx = dst_tw_port_stat.rx_pkts
            link_drp_rate = 0.0
            
            try:
                diff_tx_rx = src_tx - dst_rx
                
                # see line 327
                if diff_tx_rx >= self.STABILIZATION_PARAM:
                    link_drp_rate = (src_tx - dst_rx) / (src_tx)
                    link_drp_rate = round( link_drp_rate, 4 )
                
            except ZeroDivisionError:
                # if no packets has been sent or received ignore zero division 
                pass
            
            dst_sw_drp_rate = dst_sw_statistic.drop_rate                                   # drop rate dst switch
            overall_drop_rate = self.get_drop_probability(dst_sw_drp_rate, link_drp_rate)  # drop rate of link and switch   
            dst_sw_fabr_rate = dst_sw_statistic.fabrication_rate                           # fabrication rate of dst switch
            
            event_droprate = trustevents.EventLinkDropRateUpdate(link, overall_drop_rate)
            event_fabrrate = trustevents.EventFabrRateUpdate(link.dst.dpid, dst_sw_fabr_rate) 
            self.send_event_to_observers(event_droprate)
            self.send_event_to_observers(event_fabrrate)      
        
        
    def get_drop_probability(self, sw_drop, link_drop):      
        ''' compute the probability of drop in the switch or link'''
        
        drop_rate = sw_drop + link_drop - (sw_drop * link_drop)
        
        if drop_rate < 0: 
            print "DEBUG NEGATIVE DROP RATE: "
            print "sw_drop= ", sw_drop," link_drop= ", link_drop
            
        drop_rate = round(drop_rate, 4)        
        return drop_rate
    
        
    def _log_port_statistics (self, port_msg, logger):
             
        # counters for statistic    
        rx_pkts = tx_pkts = rx_err = tx_err = 0     
                
        logger.info('datapath         port        rx-pkts  tx-pkts  rx-err   tx-err   rx_drop   tx_drop  tx_bytes duration ')
        logger.info('---------------- ---------- -------- -------- -------- -------- -------- -------- -------- --------')
            
        for stat in sorted( port_msg.body, key =  attrgetter('port_no') ):
            logger.info('%016x %10d %8d %8d %8d %8d %8d %8d %16d %8d',
                             port_msg.datapath.id, stat.port_no,
                             stat.rx_packets, stat.tx_packets,
                             stat.rx_errors, stat.tx_errors, 
                             stat.rx_dropped, stat.tx_dropped, stat.tx_bytes, stat.duration_sec)
            rx_pkts += stat.rx_packets
            tx_pkts += stat.tx_packets
            rx_err += stat.rx_errors
            tx_err += stat.tx_errors
        
        logger.info('-------------------------------------------------------------------------------')
        logger.info('            Tot:          %8d %8d %8d %8d',
                         rx_pkts, tx_pkts, rx_err, tx_err)
       #logger.info('Measured pakets drop rate: %f', self.get_flow_conservation(port_msg.datapath.id))
        logger.info('')
    

class SwStatistic(object):
    
    class PortStat():
        def __init__(self, dpid = None, port_no = 0):
            self.dpid = dpid
            self.port_no = port_no
            self.tx_pkts = 0
            self.rx_pkts = 0
                
        def get_string(self):
            return "dp :", self.dpid, "port: ", self.port_no,' rx=',self.rx_pkts,' tx=',self.tx_pkts
        
    
    def __init__(self, dpid):
        
        self.switches_app_ref = app_manager.lookup_service_brick('switches')
        self.dpid = dpid
        
        # statistics "history"
        self.port_stat_dict = {}                    # port -> PortStat (current)
        self.tw_port_stat_dict = {}                 # port -> PortStat (time window)
        self.lldp_counter = LLDPCounter(dpid)       # lldp counter (current)
        self.tw_lldp_counter = LLDPCounter(dpid)    # lldp counter (time window)
        self.drop_rate = 0.0                        # drop rate
        self.fabrication_rate = 0.0                 # fabrication rate
    
    
    def update_lldp_counter(self, new_lldp_counter):
        
        self.tw_lldp_counter.rx_lldp = new_lldp_counter.rx_lldp - self.lldp_counter.rx_lldp
        self.tw_lldp_counter.tx_lldp = new_lldp_counter.tx_lldp - self.lldp_counter.tx_lldp
        
        #print 'DEBUG: new LLDPCounter dp: ,', self.dpid, ' rx_lldp = ', new_lldp_counter.rx_lldp, ' tx_lldp = ', new_lldp_counter.tx_lldp
        #print 'DEBUG: tw LLDPCounter dp: ,', self.dpid, ' rx_lldp = ', self.tw_lldp_counter.rx_lldp, ' tx_lldp = ', self.tw_lldp_counter.tx_lldp
        
        self.lldp_counter.rx_lldp = new_lldp_counter.rx_lldp
        self.lldp_counter.tx_lldp = new_lldp_counter.tx_lldp
        
        
    def update_port_stat(self, new_stat, port_no):
        
        # if there is no current stat for port number, empty stat is returned
        current_stat = self.port_stat_dict.get( port_no, self.PortStat(self.dpid) )
        tw_stat = self.PortStat(self.dpid, port_no)
        tw_stat.rx_pkts = new_stat.rx_pkts - current_stat.rx_pkts
        tw_stat.tx_pkts = new_stat.tx_pkts - current_stat.tx_pkts
        
        #print 'DEBUG: old stat: ', current_stat.get_string()
        #print 'DEBUG: new stat:', new_stat.get_string() 
        #print 'DEBUG: time-win stat : ', tw_stat.get_string()
        
        self.tw_port_stat_dict[port_no] = tw_stat
        self.port_stat_dict[port_no] = new_stat
        
    def get_flow_conservation(self):
        
        tx = rx = 0
        drop_rate = 0.0
        fabr_rate = 0.0
        
        for stat in self.tw_port_stat_dict.values():
            rx += stat.rx_pkts
            tx += stat.tx_pkts
            
        # subtract lldp pkts from the total of tx and rx pkts 
        rx = rx - self.tw_lldp_counter.rx_lldp
        tx = tx - self.tw_lldp_counter.tx_lldp
        
        # the total num of rx and tx pkts can't be negative
        if rx < 0 :
            #LOG.info("SW_STATS: Negative tot rx pkts for dp %s = %s ", self.dpid, rx)
            rx = 0
        if tx < 0 :
            #LOG.info("SW_STATS: Negative tot rx pkts for dp %s = %s ", self.dpid, tx) 
            tx = 0
                    
        # For the computation of drop rate and fabrication rate we take into 
        # account a margin below which the computations are not done.
        # The reasons are:
        #    - it makes no sense to consider the drop and fabr rate when the pkts exchanged 
        #      are too few
        #    - the retrived rx and tx values are error prone, therefore we must consider
        #      a margin error
        if (rx - tx) > DropFabrRateCollector.STABILIZATION_PARAM :      # pkts dropping 
            drop_rate = (rx - tx) / rx 
            drop_rate = round(drop_rate, 4)
            
        elif (tx - rx) > DropFabrRateCollector.STABILIZATION_PARAM :    # pkts fabrication
            fabr_rate = (tx - rx) / tx
            fabr_rate = round(fabr_rate, 4)
            
            
        #print 'DEBUG: drop-rate: ', drop_rate
        self.drop_rate = drop_rate
        self.fabrication_rate = fabr_rate
            
        return drop_rate, fabr_rate
