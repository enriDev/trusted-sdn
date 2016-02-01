'''
Created on Jan 11, 2016

@author: root
'''

import sys
import logging
import struct

from ryu.base import app_manager
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
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
from ryu.topology import event
from ryu.lib import hub
from ryu.lib.packet.arp import ARP_REQUEST, ARP_REPLY
from __builtin__ import True

import networkx as nx


import trust_event
import of_tb_func as of_func
from ryu.ofproto.ofproto_v1_3 import OFPFC_MODIFY_STRICT, OFPP_ANY, OFPG_ANY




class ArpProxy(app_manager.RyuApp):
    
    OFP_VERSION = [ofproto13.OFP_VERSION, ofproto10.OFP_VERSION]
    
    ARP_BROADCAST_PRIORITY = 32769
    
    def __init__(self, *args, **kwargs):
        
        super(ArpProxy, self).__init__(*args, **kwargs)
        self.name = "ArpProxy"
        self.arp_table = {}     # ip => mac      
        self.current_msg = None  
    
    
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _init_switch_oftable(self, ev):
        
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # install table-miss flow entry
        # NO BUFFER option set
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                           ofproto.OFPCML_NO_BUFFER)]
        of_func.ofAddFlow(datapath, match, actions, priority = 0)
        
        
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _arp_message_handler(self, ev):
        
        self.current_msg = ev.msg
        
        pkt = packet.Packet(self.current_msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        
        # arp packet, update ip address
        if eth.ethertype == ETH_TYPE_ARP:
            
            arp_pkt = pkt.get_protocols(arp.arp)[0]
            src_ip = arp_pkt.src_ip
            src_mac = arp_pkt.src_mac
            
            if src_ip not in self.arp_table:
                self.arp_table[src_ip] = src_mac
                print 'ARP-PROXY: arp table: ', self.arp_table
            
            if arp_pkt.opcode == ARP_REQUEST:
                self.arp_request_handler(arp_pkt)
        
            else:
                # arp code not handled
                return
    
            
    def arp_request_handler(self, arp_pkt):
        
        src_mac = arp_pkt.dst_mac
        src_ip = arp_pkt.src_ip
        dst_ip = arp_pkt.dst_ip
        
        if dst_ip not in self.arp_table:
            self.broadcast_arp()
            
        else:
            self.build_arp_reply_from_req(arp_pkt)
            
            
    def broadcast_arp(self):
            
        switch_list = get_switch(self, None)
        
        # modify flows to drop temporarily arp request
        match = parser13.OFPMatch(eth_dst = BROADCAST_STR, eth_type = ETH_TYPE_ARP)     
        actions = []
        for switch in switch_list:
            of_func.ofAddFlow(switch.dp, match, actions, self.ARP_BROADCAST_PRIORITY)
            
        for switch in switch_list: 
            of_func.ofPckOut(self.current_msg, ofproto13.OFPP_FLOOD)
        
        # del flows to drop arp request
        for switch in switch_list:
            of_func.ofDelFlow(switch.dp, match, self.ARP_BROADCAST_PRIORITY)
        
    def build_arp_reply_from_req(self, arp_req):
        
        datapath = self.current_msg.datapath
        out_port = self.current_msg.match['in_port']
        
        # ip and mac for arp reply
        sender_ip = arp_req.dst_ip
        target_ip = arp_req.src_ip
        target_mac = arp_req.src_mac
        sender_mac = self.arp_table[sender_ip]
        
        
        pkt = packet.Packet()
        pkt.add_protocol( ethernet.ethernet( ethertype =  ETH_TYPE_ARP, 
                                             src = sender_mac, dst = target_mac) )
        pkt.add_protocol( arp.arp( opcode = ARP_REPLY, 
                                   src_mac = sender_mac, src_ip = sender_ip, 
                                   dst_mac = target_mac, dst_ip = target_ip) )
        
        of_func.ofSendPck(datapath, pkt, out_port)
        
        
    

