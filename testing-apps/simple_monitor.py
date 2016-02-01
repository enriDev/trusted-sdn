'''

Simple monitor sdn application to retrive swithces statistics

Created on Nov 23, 2015

@author: root
'''

from __future__ import division
from operator import attrgetter

from ryu.base import app_manager
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.controller import ofp_event 
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, HANDSHAKE_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls


# time interval between requests
DEFAULT_REQUEST_INTERVAL = 5
# lowest priority
TABLE_MISS_PRIORITY = 0
# table id for miss priority
TABLE_MISS_TB_ID = 0
# switch to controller port
SW_TO_CONTR_PORT = 4294967294
# misalignement between rx pkts and tabe-miss pkts due to the separate, non synchronized statistics requests 
STAT_REQ_TIMING_THRESH = 5


class SwitchLinkTrustEvaluator(app_manager.RyuApp):
    " Monitor switches statistics "
    
    OFP_VERSIONS = [ofproto13.OFP_VERSION]
    
    def __init__(self, *args, **kwargs):
        
        super(SwitchLinkTrustEvaluator, self).__init__(*args, **kwargs)
        #store a list of connected switches
        self.datapaths = {} 
        #time interval between requests
        self.interval = DEFAULT_REQUEST_INTERVAL
        #reference to thread
        self.monitor_thread = hub.spawn(self._stats_request_loop)
        
        # dict datapths statistics
        self.datapaths_stats = {}
    
    
    class _SwDropStatistics(object):
        "Utility class for representing statistics for drop rate computation"
        tx_pkts = rx_pkts = table_miss_pkts = 0 
        drop_rate = 0.0
    
        
    def _stats_request_loop(self):
        "  Run method of thread  "
        while True:
            for datapath in self.datapaths.values():
                self._multi_stats_request(datapath)
            hub.sleep(self.interval)
            
        
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        
        datapath = ev.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                
                self.datapaths[datapath.id] = datapath
                self.datapaths_stats.setdefault(datapath.id, self._SwDropStatistics()) 
                self.logger.info('Register datapath: %016x', datapath.id)
                
                # install table-miss entry: drop
                priority = TABLE_MISS_PRIORITY
                table_id = TABLE_MISS_TB_ID
                match = parser.OFPMatch()
                #actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          #ofproto.OFPCML_NO_BUFFER)] # changed
                actions = []
                self._add_flow(datapath, match, actions, priority, table_id)
                self.logger.info('Install table-miss entry to dp: %016x - action: drop', datapath.id)
                
                
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
                del self.datapaths_stats[datapath.id]
                self.logger.info('Unregister datapath: %016x', datapath.id)
                
    
    def _add_flow (self, datapath, match, actions, priority = 0, table_id = 0):
        
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        flow_mod = parser.OFPFlowMod(
                                     datapath = datapath, match = match, table_id = table_id,
                                     command = ofproto.OFPFC_ADD, 
                                     priority = priority, instructions = inst)
        datapath.send_msg(flow_mod)
    
    
    def _multi_stats_request(self, datapath):
        
        self.logger.info('Statistic request: dp %016x', datapath.id)
        
        self._table_miss_stats_request(datapath)
        self._port_stats_request(datapath)    
    
    
    def _table_miss_stats_request(self, datapath):
        
        self.logger.info('Table-miss statistics request: dp %016x', datapath.id)
        
        ofproto = datapath.ofproto
        of_parser = datapath.ofproto_parser
        
        # table-miss flow statistics request
        match = of_parser.OFPMatch()
        out_port = ofproto.OFPP_ANY
        request = of_parser.OFPFlowStatsRequest(datapath = datapath, match = match, table_id = TABLE_MISS_TB_ID, out_port = out_port) 
        datapath.send_msg(request)
        
    def _port_stats_request(self, datapath):
        
        self.logger.info('Port statistic request: dp %016x', datapath.id)
        
        ofproto = datapath.ofproto
        of_parser = datapath.ofproto_parser
                
        # port statistics request
        request = of_parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(request)
        
    
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _table_miss_stats_reply_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        body = msg.body
        
        if datapath.id in self.datapaths_stats:
            rx_dropped = 0
            for stat in body: rx_dropped = stat.packet_count
            self.datapaths_stats[datapath.id].table_miss_pkts = rx_dropped
            self.logger.info('Dropped packet for dp %016x : %d', datapath.id, rx_dropped)
        
    
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        body = msg.body
        
        # stats for switch drop rate computation
        tx_pkts = rx_pkts = 0
        
        # retrive statistics summation
        for stat in body:
            if not stat.port_no == SW_TO_CONTR_PORT:    # ignore stats for this port
                tx_pkts += stat.tx_packets
                rx_pkts += stat.rx_packets
                
        # stores statistics 
        self.datapaths_stats[datapath.id].rx_pkts = rx_pkts
        self.datapaths_stats[datapath.id].tx_pkts = tx_pkts
        
        self.logger.info('computing for: %016x', datapath.id)
        self._log_port_statistics(msg, self.logger)    
        self.sw_drop_rate()
                         
    
    
    def sw_drop_rate(self):    
        
        def drop_rate_condition(rx_tx_sum, tx, true_positive_rx ):
            # if assertion fails problems related o statistics requests timing have to be considered
            assert (true_positive_rx >= 0)
            return  (not rx_tx_sum == 0) and not( (tx == 0) and (true_positive_rx < STAT_REQ_TIMING_THRESH) )
        
        for dp in self.datapaths_stats.values():
            
            # alias only for clarity
            tx = dp.tx_pkts
            rx = dp.rx_pkts
            miss = dp.table_miss_pkts
            
            # packet drop rate computation
            true_positive_rx = rx - miss        
            rx_tx_diff = true_positive_rx - tx  
            rx_tx_sum = true_positive_rx  + tx 
                                    
            if drop_rate_condition(rx_tx_sum, tx, true_positive_rx):     
                
                drop_rate = (rx_tx_diff / rx_tx_sum)
                dp.drop_rate = drop_rate
            
            else:
                dp.drop_rate = 0
        
        
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
        logger.info('Measured pakets drop rate: %f', self.datapaths_stats[port_msg.datapath.id].drop_rate)
        logger.info('')
        