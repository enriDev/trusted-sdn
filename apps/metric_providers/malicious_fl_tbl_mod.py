'''
Created on Feb 9, 2016

@author: root
@version: 1.0
'''

import logging
import sys
import os
import inspect

from ryu.topology import event as topoevent
from ryu.topology.api import get_switch
from ryu.controller import ofp_event
from ryu.controller import event
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.lib import hub

import trustevents
from trust_collector_base import TrustCollectorBase
from ofp_table_mod.of_tbl_mod_provider import OFTblModProvider  
# require add apps to PYTHONPATH
#TODO find better solution for imports


LOG = logging.getLogger(__name__)


class MaliciousFlTblMod(TrustCollectorBase):
    
    _EVENTS = [trustevents.EventMaliciousFlowTblMod]
    
    FLOW_TBL_REQUEST_INTERVAL = 10
    
    
    def __init__(self):
        
        super(MaliciousFlTblMod, self).__init__('malicious_fl_tbl_mod')
        self.switch_list = {}                                   # dpid -> datapath
        self.flow_cache = OFTblModProvider().flow_table_cache   # reference to flow table cache
         
        self.threads.append( hub.spawn_after(self.LOAD_TIME, self.flow_tbl_monitoring_loop) )
        
    
    @set_ev_cls(topoevent.EventSwitchEnter, MAIN_DISPATCHER)
    def switchEnterEvent_handler(self, ev):
        
        datapath = ev.switch.dp
        self.switch_list[datapath.id] = datapath
        
    
    def flow_tbl_monitoring_loop(self):
        
        LOG.info("MALICIOUS-MOD: Starting flow table monitoring...")
        while True:
            for datapath in self.switch_list.values():
                self.flow_tbl_status_request(datapath)
            hub.sleep(self.FLOW_TBL_REQUEST_INTERVAL)


    def flow_tbl_status_request(self, datapath):
        
        #LOG.info('Flow table status request: dp %016x', datapath.id)
        
        ofproto = datapath.ofproto
        of_parser = datapath.ofproto_parser
        
        # request all flow table entries
        match = of_parser.OFPMatch()
        request = of_parser.OFPFlowStatsRequest(datapath = datapath, match = match) 
        datapath.send_msg(request)
        
        
        
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def check_flow_table(self, ev):
        
        msg = ev.msg
        dpid = msg.datapath.id
        body = msg.body
        
        try:
            cached_flow_table = self.get_cached_hashed_fl_tbl(dpid)
            flow_table = {}
        
            for stat in body:
                flow_entry = (int (stat.table_id),
                              int (stat.priority),
                              int (stat.idle_timeout),
                              str (stat.match),
                              str (stat.instructions),
                              )
                flow_hash = hash(flow_entry)
                flow_table[flow_hash] = flow_entry
                cached_flow_table[flow_hash]
        
        except KeyError as e:
            # if the hash key is not found in the cached_flow_table dict,
            # the flow entry was not present in the cached
            LOG.info('\nMALICIOUS-MOD: Found flow table inconsistency in dp %s :\n'
                     '%s', dpid, flow_table[e.args[0]])
            
            trust_update = trustevents.EventMaliciousFlowTblMod(dpid)
            self.publish_trust_update(trust_update)
        
        
    def get_cached_hashed_fl_tbl(self, dpid):
        
            stored_flow_table = self.flow_cache.flow_table_query(dpid)
            cached_flow_table = {}
            for flow in stored_flow_table:
                flow_hash = hash(flow)
                cached_flow_table[flow_hash] = flow
            
            #LOG.info('\nCached flow table %s: \n%s', dpid, self.dict_to_str(cached_flow_table))
            return cached_flow_table
            
        
    def dict_to_str(self, dict):
        stri = ''
        for elem in dict.keys():
            stri = stri + str(elem) + ' : ' + str(dict[elem]) + '\n'
        return stri
        
        
        
        
