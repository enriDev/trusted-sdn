'''
Created on Feb 9, 2016

The trust metric is computed from:
  - malicious flow table modification
  - switch drop rate
  - link drop rate
  - switch fabrication rate

@author: root
@version 2.0
'''


from __future__ import division
from operator import attrgetter
import logging

from ryu.base import app_manager
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.controller import event as app_event
from ryu.controller import ofp_event 
from ryu.controller import handler
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, HANDSHAKE_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.topology.api import get_switch, get_link
from ryu.topology import event, switches 
from ryu.topology.switches import LLDPCounter
from ryu.ofproto import ether
from ryu.lib.packet import packet, ethernet, vlan


import logging
import datetime
from os.path import isfile, getsize
import sqlite3 as lite
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.lib.dpid import dpid_to_str
from ryu.lib.mac import BROADCAST_STR
from ryu.lib.packet.lldp import LLDP_MAC_NEAREST_BRIDGE
from ryu.lib.packet.ether_types import ETH_TYPE_LLDP

import metric_provider
import trustevents


LOG = logging.getLogger(__name__)   # logger for module


# required trust collectors
app_manager.require_app('metric_providers.malicious_fl_tbl_mod')      # malicious flow table mod
app_manager.require_app('metric_providers.drop_fabr_rate_collector')  # drop/fabric rate of switches and links                   



class TrustMetricProvider(metric_provider.MetricProviderBase):
    
    APP_NAME = 'trust_metric_provider'
    
    DEFAULT_TRUST_METRIC = 0.01
    MAX_TRUST_METRIC = 1
    MIN_TRUST_METRIC = 0.01
    DROP_WEIGHT = 0.8
    FABR_WEIGHT = 1-DROP_WEIGHT
    CURRENT_METRIC_WEIGHT = 0.4
    NEW_METRIC_WEIGHT = 1-CURRENT_METRIC_WEIGHT  
    
    
    def __init__(self, *args, **kwargs):
        
        super(TrustMetricProvider, self).__init__(self.APP_NAME,
                                                  self.DEFAULT_TRUST_METRIC,
                                                  *args, **kwargs)
        self.link_features = {}   # link -> feature_name -> value
    
    
    @set_ev_cls(event.EventLinkAdd)
    def populate_features_dict(self, ev):
        
        #TODO refactor
        link = ev.link
        #the proprieties relative to switch only in a link are referred to the dst  
        self.link_features.setdefault( link, {'drop_rate':0.0, 'fabr_rate':0.0, 'trust_drop_rate':1.0, 'trust_fabr_rate':1.0, 'malicious_mod':1, 'trust_value':0.99 } )    
    
    
    @set_ev_cls(trustevents.EventMaliciousFlowTblMod)
    def malicious_flow_tbl_mod_hanlder(self, ev):
        
        dpid = ev.dpid
        for link in self.link_features.keys():
            if link.dst.dpid == dpid:
                self.link_features[link]['malicious_mod'] = 0
    
        
    @set_ev_cls(trustevents.EventFabrRateUpdate)
    def fabr_update_handler(self, ev):
        
        dpid = ev.dpid
        for link in self.link_features.keys():
            if link.dst.dpid == dpid:
                #custom non_fabr_rate
                non_fabr_rate = self.custom_non_fabr_rate(ev.fabr_rate) 
                self.link_features[link]['trust_fabr_rate'] = non_fabr_rate     # trust wrt fabr rate
                self.link_features[link]['fabr_rate'] = round((1-ev.fabr_rate),2)        # fabr rate
                #print 'EVENT-FABR_RATE: ',link.src.dpid,"->",link.dst.dpid," = ",ev.fabr_rate,"/",non_fabr_rate, "(real/custom trust)"
    
    def custom_non_fabr_rate(self, non_fabr_rate):
        custom_non_fabr = pow(non_fabr_rate,2)
        return round(custom_non_fabr, 2)
        
    @set_ev_cls(trustevents.EventLinkDropRateUpdate)
    def drop_update_handler(self, ev):
        
        link = ev.link
        self.link_features.setdefault(link, {})
        # custom non_drop_rate
        non_drop_rate = self.custom_non_drop_rate(ev.drop_rate)
        self.link_features[link]['trust_drop_rate'] = non_drop_rate     # trust wrt drop rate
        self.link_features[link]['drop_rate'] = round((1-ev.drop_rate),2)      # drop rate
        #print "EVENT-DROPRATE: ",link.src.dpid,"->",link.dst.dpid," = ",ev.drop_rate,"/",non_drop_rate, "(real/custom trust)"

    def custom_non_drop_rate(self, non_drop_rate):
        custom_non_drop = pow(non_drop_rate,2)
        return round(custom_non_drop, 2)

    def compute_metric(self):
        
        for link in self.links_metric:
            
            if self.link_features[link]['malicious_mod'] == 1:
               
                non_drop_rate = self.link_features[link]['trust_drop_rate']
                non_fabr_rate = self.link_features[link]['trust_fabr_rate']
                
                trust_value = self.aggregation_func(non_drop_rate, non_fabr_rate)
                new_trust_metric = (1 - trust_value)
                print "trust_value/metric:", link.src.dpid, "->",link.dst.dpid, " = ",  trust_value,"/",new_trust_metric
            
                current_trust_metric = self.links_metric[link]
            
                smoothed_metric = self.exp_smoothing(self.CURRENT_METRIC_WEIGHT, current_trust_metric,
                                                    self.NEW_METRIC_WEIGHT, new_trust_metric)
                smoothed_metric = round(smoothed_metric, 2)
            
                if smoothed_metric < self.DEFAULT_TRUST_METRIC:
                    smoothed_metric = self.DEFAULT_TRUST_METRIC
                
                self.links_metric[link] = smoothed_metric
                
            else:
                self.links_metric[link] = self.MAX_TRUST_METRIC
                
            self.link_features[link]["trust_value"] = (1-self.links_metric[link]) 
    
    def aggregation_func(self, non_drop, non_fabr):
        return min(non_drop, non_fabr)        
            
    @staticmethod        
    def exp_smoothing(weight_1, param_1, weight_2, param_2):
        return (weight_1 * param_1) + (weight_2 * param_2)
             
            
        
    
        
        
        
        
        
        
        