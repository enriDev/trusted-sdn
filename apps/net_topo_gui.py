'''
Created on Feb 2, 2016

Gui for displaing the network graph
@author: root
'''


import sys
import thread
import time
import logging
import struct
import ConfigParser
import six
import abc

from ryu.base import app_manager
from ryu.controller import handler
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.ofproto.ofproto_v1_3 import OFP_NO_BUFFER
from ryu.lib.dpid import str_to_dpid
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.ofproto import ofproto_v1_0 as ofproto10
from ryu.ofproto.ether import ETH_TYPE_LLDP, ETH_TYPE_ARP, ETH_TYPE_IP
from ryu.lib.mac import haddr_to_bin, BROADCAST, BROADCAST_STR
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import icmp
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp
from ryu.lib import dpid
from ryu.topology.api import get_switch, get_link, get_host
from ryu.app.wsgi import ControllerBase
from ryu.topology import event
from ryu.lib import hub
from ryu.lib.packet.arp import ARP_REQUEST, ARP_REPLY
from __builtin__ import True

import networkx as nx
from matplotlib.pyplot import pause, clf
import pylab

import trust_event
import of_tb_func as of_func
import trust_evaluator
from service_manager import ServiceManager
from trust_based_forwarder import TrustBasedForwarder
from time import sleep



LOG = logging.getLogger(__name__)       # module logger




class NetTopoGui(app_manager.RyuApp):
    
    REFRESH_TIME = 2 # (sec) time between refreshing graph draw 
    
    #_CONTEXTS = {
    #        'TrustBasedForwarder' : TrustBasedForwarder
     #   }
    

    def __init__(self, *args, **kwargs):
        
        super(NetTopoGui, self).__init__(*args, **kwargs)
        self.name = "NetTopoGui"
        
        #self.trust_based_forwarder = kwargs['TrustBasedForwarder']
        #self.service_manager = kwargs['ServiceManager']
        thread.start_new_thread(self.start_loop)
        
        
    def get_fig(self):
        tbf = app_manager.lookup_service_brick('TrustedBasedForwarder')
        net = tbf.net
        
        pos = nx.spring_layout(net, weight = None, k = 0.5, iterations = 1,center = (0,0))
        #pos = nx.random_layout(net, center = (0,0))
        #pos = nx.pydot_layout(net, prog = "dot")
        #pos = nx.spectral_layout(net, dim = 2, weight = None, center = (0,0))
        #pos = nx.circular_layout(net, center = (0,0))
        
        fixed_pos = {1:(0,0), 2:(1,2)}
        fixed_nodes = fixed_pos.keys()
        
        nx.draw_networkx(net, pos = pos)
        nx.draw_networkx_edge_labels(net, pos = pos)
        
    def start_loop(self):
        
        pylab.ion()
        pylab.show()
        while True:    
            self.get_fig()
            pylab.draw()
            pause(self.REFRESH_TIME)
            clf()
        
            
        
  
  
  
  
  
  
  
  
  
  
  
  