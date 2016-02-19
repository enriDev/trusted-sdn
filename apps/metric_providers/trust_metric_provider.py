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
    DEFAULT_METRIC = 0.01
    
    def __init__(self, *args, **kwargs):
        super(TrustMetricProvider, self).__init__(self.APP_NAME, *args, **kwargs)
    
    
    @set_ev_cls(trustevents.EventMaliciousFlowTblMod)
    def malicious_flow_tbl_mod_hanlder(self, ev):
        
        dpid = ev.dpid
        LOG.info('****mal update received%s', dpid)
        #TODO think of how to store the collected trust and how to merge
        
        
    @set_ev_cls(trustevents.EventDropFabrRate)
    def drop_fabr_rate_handler(self, ev):
        #TODO implement
        pass
        
        
    def compute_metric(self):
        for link_dict in self.links_metric:
            link_dict['metric'] = TrustMetricProvider.DEFAULT_METRIC 
        
    
      
        
        
        
        
        
        
        