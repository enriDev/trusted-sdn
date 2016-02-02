'''
Created on Dec 7, 2015

The module monitors switches and links in a network, evaluates the trust
according to some parameters and raise events for publishing the trust evaluation:

- Switch trust :
    - dropping / fabrication rate

@version: 1.0
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
from ryu.controller import handler
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, HANDSHAKE_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.topology.api import get_switch, get_link
from ryu.topology import event, switches 
from ryu.topology.switches import LLDPCounter
from ryu.ofproto import ether
from ryu.lib.packet import packet, ethernet, vlan


import trust_event
import of_tb_func
from ryu.lib.mac import BROADCAST_STR
from ryu.lib.packet.lldp import LLDP_MAC_NEAREST_BRIDGE
from ryu.lib.packet.ether_types import ETH_TYPE_LLDP


##### GLOBAL VARIABLE ####

LOG = logging.getLogger(__name__)

# lowest priority
TABLE_MISS_PRIORITY = 0
# table id for miss priority
TABLE_MISS_TB_ID = 0

# misalignement between rx pkts and tabe-miss pkts due to the separate, non synchronized statistics requests 
STAT_REQ_TIMING_THRESH = 5


    
    
        
class SwitchLinkTrustEvaluator(app_manager.RyuApp):
    """ Monitor switches port statistics to evaluate:
        - switch drop rate
        - switch fabrication rate
        - link drop rate
    """
    
    # time before starting request
    INIT_TIME = 5
    # time interval between port stats requests 
    DEFAULT_REQUEST_INTERVAL = 10  #(sec)
    
    
    # balance between drop rate and fabrication rate
    # the link trust is (1 - SW_TRUST_WEIGHT)
    DROP_WEIGHT = 0.8
    FABRICATION_WEIGHT = 1 - DROP_WEIGHT
    
    # parameter used for stabilize drop and fabr rate. (see line 474)
    STABILIZATION_PARAM = 10
    
    # switch to controller port
    SW_TO_CONTR_PORT = 4294967294
    
    # events raised by the app
    _EVENTS = [trust_event.EventSwitchTrustChange, trust_event.EventLinkTrustChange]
    
    
    def __init__(self, *args, **kwargs):
        
        super(SwitchLinkTrustEvaluator, self).__init__(*args, **kwargs)
        self.name = 'trust_evaluator'
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
        
        self.threads.append( hub.spawn_after(self.INIT_TIME, self._stats_request_loop) )
        
        

    
    #Utility class for representing statistics for drop rate computation
    class _SwDropStatistics(object):
        
        tx_pkts = rx_pkts = table_miss_pkts = 0 
        drop_rate = 0.0
        
        
    class _PortStat(object):
        
        port_no = 0
        tx_pkts = 0
        rx_pkts = 0
        
        def get_string(self):
            return "port: ", self.port_no,' rx: ',self.rx_pkts,' tx: ',self.tx_pkts
        
    
    # runs statistics requests in a separate thread
    def _stats_request_loop(self):
        
        # stop lldp_loop thread in switches module
        #sw = app_manager.lookup_service_brick('switches')
        #sw.is_active = False
        
        self.logger.info("TRUST_EVAL: Starting statistics requests...")
        while True:
            for datapath in self.datapaths.values():
                self._multi_stats_request(datapath)
            hub.sleep(self.DEFAULT_REQUEST_INTERVAL)
            self.is_first_stat_req = False
        
        
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        
        datapath = ev.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                
                self.datapaths[datapath.id] = datapath
                self.datapaths_stats.setdefault(datapath.id, SwStatistic(datapath.id)) 
                self.logger.info('Register datapath: %016x', datapath.id)
                
                # install table-miss entry: drop
                #priority = TABLE_MISS_PRIORITY
                #table_id = TABLE_MISS_TB_ID
                #match = parser.OFPMatch()
                #actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          #ofproto.OFPCML_NO_BUFFER)] # changed
                #actions = []
                #self._add_flow(datapath, match, actions, priority, table_id)
                #self.logger.info('Install table-miss entry to dp: %016x - action: drop', datapath.id)
                
                
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
                del self.datapaths_stats[datapath.id]
                self.logger.info('Unregister datapath: %016x', datapath.id)
                
    
    #def _add_flow (self, datapath, match, actions, priority = 0, table_id = 0):
        
    #    ofproto = datapath.ofproto
    #    parser = datapath.ofproto_parser
        
    #    inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
    #    flow_mod = parser.OFPFlowMod(
    #                                 datapath = datapath, match = match, table_id = table_id,
    #                                 command = ofproto.OFPFC_ADD, 
    #                                 priority = priority, instructions = inst)
    #    datapath.send_msg(flow_mod)
    

    @set_ev_cls(event.EventLinkAdd)
    def new_link_event_handler(self, ev):
        
        self.logger.info('TRUST_EVAL: New link detected %s -> %s', ev.link.src.dpid, ev.link.dst.dpid)
        
        self.link_list.setdefault( ev.link , )
        #print '***links'
        #print self.link_list



    def _multi_stats_request(self, datapath):
        
        #self.logger.info('SWITCH_EVAL: Statistic request: dp %016x', datapath.id)
        
        #self._lldp_match_stats_request(datapath)
        self._port_stats_request(datapath)    
    
 
    def _lldp_match_stats_request(self, datapath):
        
        #self.logger.info('Table-miss statistics request: dp %016x', datapath.id)
        
        ofproto = datapath.ofproto
        of_parser = datapath.ofproto_parser
        
        # table-miss flow statistics request
        match = of_parser.OFPMatch(eth_dst = LLDP_MAC_NEAREST_BRIDGE, eth_type = ETH_TYPE_LLDP)
        out_port = ofproto.OFPP_CONTROLLER
        request = of_parser.OFPFlowStatsRequest(datapath = datapath, match = match, table_id = TABLE_MISS_TB_ID, out_port = out_port) 
        datapath.send_msg(request)

        
    def _port_stats_request(self, datapath):
        
        #self.logger.info('SWITCH_EVAL: Port statistic request: dp %016x', datapath.id)
        
        ofproto = datapath.ofproto
        of_parser = datapath.ofproto_parser
                
        # port statistics request
        request = of_parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(request)
        self.pending_stats_req += 1
        
    
    #set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _lldp_match_stats_reply_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        body = msg.body
        
        if datapath.id in self.datapaths_stats:
            lldp_match = 0
            for stat in body: lldp_match = stat.packet_count
            self.datapaths_stats[datapath.id].update_lldp_stat(lldp_match)
            self.logger.info('TRUST_EVAL-EVENT: LLDP match for dp %016x : %d', datapath.id, lldp_match)

      
    
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        body = msg.body
        
        #self.logger.info('TRUST_EVAL-EVENT: port statistics for dp %016x', datapath.id)
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
                
        #self._log_inter_port_stats(self.logger, datapath.id)
        
        
        # compute drop rate for the switch
        sw_drop_rate, sw_fabr_rate = self.datapaths_stats[datapath.id].get_flow_conservation()
        self.logger.info("DEBUG: Flow conservation property for dp %s: drop=%s%%  fabr=%s%%", datapath.id, sw_drop_rate*100, sw_fabr_rate*100)
        #self._log_port_statistics(msg, self.logger)    
              
        # raise event for switch drop rate
        #trust_ev = trust_event.EventSwitchTrustChange(datapath.id, sw_drop_rate)
        if not self.is_first_stat_req:
            # self.send_event_to_observers(trust_ev)
            # compute drop rate for all links if no requests are pending
            if self.pending_stats_req == 0 :
                self.link_drop_rate()

    
    def link_drop_rate(self):
            
        #print 'DEBUG: link drop rate eval'
            
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
                
                # see line 474
                if diff_tx_rx >= self.STABILIZATION_PARAM:
                    link_drp_rate = (src_tx - dst_rx) / (src_tx)
                    link_drp_rate = round( link_drp_rate, 4 )
                
            except ZeroDivisionError:
                # if no packets has been sent or received ignore zero division 
                pass
            
            # drop rate of destination switch
            dst_sw_drp_rate = dst_sw_statistic.drop_rate 
            combined_drop_rate = self.get_combined_drop_rate(dst_sw_drp_rate, link_drp_rate)
            dst_sw_fabr_rate = dst_sw_statistic.fabrication_rate
        
            #print "DEBUG trust metric for dp: ", dst.dpid," comb drop= ", combined_drop_rate," fabr= ",dst_sw_fabr_rate
            
            trust_metric = self.get_trust_metric(combined_drop_rate, dst_sw_fabr_rate)
            
            assert (trust_metric >= 0)
            
            trust_ev = trust_event.EventLinkTrustChange(link, trust_metric)
            self.send_event_to_observers(trust_ev)       
        
        
    def get_combined_drop_rate(self, sw_drop, link_drop):      
        # the following computation return the probability of the pkt drop
        
        drop_rate = sw_drop + link_drop - (sw_drop * link_drop)
        
        if drop_rate < 0: 
            print "DEBUG NEGATIVE DROP RATE: "
            print "sw_drop= ", sw_drop," link_drop= ", link_drop
            
        
        drop_rate = round(drop_rate, 4)        
        return drop_rate
        
        
    def get_trust_metric(self, drop_rate, fabr_rate):
        
        trust_metric = (self.DROP_WEIGHT*drop_rate) + (self.FABRICATION_WEIGHT*fabr_rate)
        trust_metric = round(trust_metric, 4) 
        return trust_metric
    
        
    def _log_port_statistics (self, port_msg, logger):
             
        # counters for statistic    
        rx_pkts = tx_pkts = rx_err = tx_err = 0     
                
        logger.info('datapath         port        rx-pkts  tx-pkts  rx-err   tx-err   rx_drop   tx_drop')
        logger.info('---------------- ---------- -------- -------- -------- -------- -------- --------')
            
        for stat in sorted( port_msg.body, key =  attrgetter('port_no') ):
            logger.info('%016x %10d %8d %8d %8d %8d %8d %8d',
                             port_msg.datapath.id, stat.port_no,
                             stat.rx_packets, stat.tx_packets,
                             stat.rx_errors, stat.tx_errors, 
                             stat.rx_dropped, stat.tx_dropped)
            rx_pkts += stat.rx_packets
            tx_pkts += stat.tx_packets
            rx_err += stat.rx_errors
            tx_err += stat.tx_errors
        
        logger.info('-------------------------------------------------------------------------------')
        logger.info('            Tot:          %8d %8d %8d %8d',
                         rx_pkts, tx_pkts, rx_err, tx_err)
        logger.info('Measured pakets drop rate: %f', self.get_flow_conservation(port_msg.datapath.id))
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
        
        # referenc to switches app
        self.switches_app_ref = app_manager.lookup_service_brick('switches')
        self.dpid = dpid
        
        # statistics "history"
        self.port_stat_dict = {}     # current statistics per port
        self.tw_port_stat_dict = {}  # time window statistics per port
        self.lldp_counter = LLDPCounter(dpid)     # current lldp counter
        self.tw_lldp_counter = LLDPCounter(dpid)  # time window lldp counter
        
        self.drop_rate = 0.0         
        self.fabrication_rate = 0.0  
    
    
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
            LOG.info("SW_STATS: Negative tot rx pkts for dp %s = %s ", self.dpid, rx)
            rx = 0
        if tx < 0 :
            LOG.info("SW_STATS: Negative tot rx pkts for dp %s = %s ", self.dpid, tx) 
            tx = 0
                    
        # For the computation of drop rate and fabrication rate we take into 
        # account a margin below which the computations are not done.
        # The reasons are:
        #    - it makes no sense to consider the drop and fabr rate when the pkts exchanged 
        #      are too few
        #    - the retrived rx and tx values are error prone, therefore we must consider
        #      a margin error
        if (rx - tx) > SwitchLinkTrustEvaluator.STABILIZATION_PARAM :      # pkts dropping 
            drop_rate = (rx - tx) / rx 
            drop_rate = round(drop_rate, 4)
            
        elif (tx - rx) > SwitchLinkTrustEvaluator.STABILIZATION_PARAM :    # pkts fabrication
            fabr_rate = (tx - rx) / tx
            fabr_rate = round(fabr_rate, 4)
            
            
        #print 'DEBUG: drop-rate: ', drop_rate
        self.drop_rate = drop_rate
        self.fabrication_rate = fabr_rate
            
        return drop_rate, fabr_rate
 
             
        
        
        
