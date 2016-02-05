'''
Created on Feb 5, 2016

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

LOG = logging.getLogger(__name__)   # logger for module
    
        
class FlowTableChecker(app_manager.RyuApp):
    
    # time before starting request
    INIT_TIME = 5
    # time interval between port stats requests 
    DEFAULT_REQUEST_INTERVAL = 10  #(sec)
    
    # switch to controller port
    SW_TO_CONTR_PORT = 4294967294
    
    
    def __init__(self, *args, **kwargs):
        
        super(FlowTableChecker, self).__init__(*args, **kwargs)
        self.name = 'flow_table_checker'
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
        
    
        
    
    # runs statistics requests in a separate thread
    def _stats_request_loop(self):
        
        # stop lldp_loop thread in switches module
        #sw = app_manager.lookup_service_brick('switches')
        #sw.is_active = False
        
        LOG.info("TRUST_EVAL: Starting statistics requests...")
        while True:
            for datapath in self.datapaths.values():
                self.fl_tbl_status_request(datapath)
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
                LOG.info('Register datapath: %016x', datapath.id)
                
                # install table-miss entry: drop
                #priority = TABLE_MISS_PRIORITY
                #table_id = TABLE_MISS_TB_ID
                #match = parser.OFPMatch()
                #actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          #ofproto.OFPCML_NO_BUFFER)] # changed
                #actions = []
                #self._add_flow(datapath, match, actions, priority, table_id)
                #LOG.info('Install table-miss entry to dp: %016x - action: drop', datapath.id)
                
                
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
                LOG.info('Unregister datapath: %016x', datapath.id)
                
    
 
    def fl_tbl_status_request(self, datapath):
        
        LOG.info('Flow table status request: dp %016x', datapath.id)
        
        ofproto = datapath.ofproto
        of_parser = datapath.ofproto_parser
        
        # request all flow table entries
        match = of_parser.OFPMatch()
        request = of_parser.OFPFlowStatsRequest(datapath = datapath, match = match) 
        datapath.send_msg(request)
        
    
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def fl_tbl_status_reply_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        body = msg.body
        
        flow_entries = []
        for stat in body:
            flow_entries.append(
                                'dp=%s -- '
                                'table_id=%s -- '
                                'priority=%s -- '
                                'idle_timeout=%s -- '
                                'match=%s -- '
                                'instruction=%s -- ' %
                                (datapath.id,
                                 stat.table_id,
                                 stat.priority,
                                 stat.idle_timeout,
                                 stat.match,
                                 stat.instructions,
                                 ))
            
        LOG.info('\nFlow table status: \n%s', flow_entries)
            
            
            
            
            
            
            
            
            
            
            
            