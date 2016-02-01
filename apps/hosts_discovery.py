'''
Created on Dec 9, 2015

Discovery hosts in the network using arp protocol

@author: root
'''


import sys
import logging
import struct

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.ofproto import ofproto_v1_0 as ofproto10
from ryu.ofproto.ether import ETH_TYPE_LLDP, ETH_TYPE_ARP
from ryu.lib.mac import haddr_to_bin, BROADCAST, BROADCAST_STR
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib import dpid
from ryu.topology.api import get_switch, get_link, get_host
from ryu.app.wsgi import ControllerBase
from ryu.topology import event, switches 
from ryu.lib import hub
from ryu.lib.packet.arp import ARP_REQUEST, ARP_REPLY
from __builtin__ import True

import of_tb_func




class HostDiscovery(app_manager.RyuApp):
    
    # start host discovery after...
    START_AFTER = 3
    # time interval between discovery probing
    TIMEOUT = 10
    # interval for avoiding burst
    ARP_SEND_GUARD = 0.5
    
    def __init__(self, *args, **kwargs):
        
        super(HostDiscovery, self).__init__(*args, **kwargs)
        
        self.datapaths = {}
        self.is_active = True
        self.threads.append(hub.spawn_after(self.START_AFTER, self._arp_loop))


    def _init_switch_oftable(self, datapath):
        
        # drop arp requests to avoid arp storm
        match_arp_req = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REQUEST)
        actions_arp_req = []
        of_tb_func.ofAddFlow(datapath, match_arp_req, actions_arp_req)
        
        # forward arp replies to the controller
        match_arp_rep = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REPLY)
        actions_arp_rep = [parser13.OFPActionOutput(ofproto13.OFPP_CONTROLLER, ofproto13.OFPCML_NO_BUFFER)]
        of_tb_func.ofAddFlow(datapath, match_arp_rep, actions_arp_rep)
        
    
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        
        datapath = ev.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                
                self.datapaths[datapath.id] = datapath
                self.logger.info('HOST_DISCOVERTY: Register datapath: %016x', datapath.id)
                
                # initialize the OpenFlow tables for the hosts discovery
                self._init_switch_oftable(datapath)
                
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
                self.logger.info('HOST_DISCOVERY: Unregister datapath: %016x', datapath.id)


    def _arp_loop(self):
        
        self.logger.info('HOST_DISCOVERY: Starting arp requests loop...')
        
        while self.is_active:
            
            for dpid in self.datapaths:
    
                datapath = self.datapaths[dpid]
                self._send_arp_req(datapath)
                hub.sleep(self.ARP_SEND_GUARD)      # avoid burst
                
            self.logger.info('HOST_DISCOVERY: pause')
            hub.sleep(self.TIMEOUT)
    
    
    def _send_arp_req(self, datapath):
        
        pkt = packet.Packet()
        pkt.add_protocol( ethernet.ethernet( ethertype =  ETH_TYPE_ARP, 
                                             src = BROADCAST_STR, dst = BROADCAST_STR) )
        pkt.add_protocol( arp.arp( opcode = ARP_REQUEST, 
                                   src_mac = '01:02:03:04:05:06', src_ip = '192.168.0.1', 
                                   dst_mac = BROADCAST_STR, dst_ip = '255.255.255.255') )
        
        of_tb_func.ofSendPck(datapath, pkt, ofproto13.OFPP_FLOOD)
        


