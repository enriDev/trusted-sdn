'''
Created on Feb 5, 2016

@author: root
'''

import logging
import ConfigParser
from ryu.base import app_manager

from ryu.controller import ofp_event, event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.ofproto.ether import ETH_TYPE_ARP
from ryu.lib.mac import BROADCAST_STR
from ryu.lib.packet import packet, ethernet, arp
from ryu.lib.packet.arp import ARP_REQUEST, ARP_REPLY
from ryu.topology.event import EventSwitchEnter
from __builtin__ import True
from ryu.exception import RyuException

from flow_table_db import FlowTableDb


LOG = logging.getLogger(__name__)


class OFTblModProvider(app_manager.RyuApp):

    _instance = None    #singleton
     
    def __init__(self, *args, **kwargs):
        
        super(OFTblModProvider, self).__init__(*args, **kwargs)
        self.name = "of_tbl_mod_provider"
        
        self.flow_table_cache = FlowTableDb()
        
     
    @staticmethod   
    def get_instance(self):
        
        if not OFTblModProvider._instance:
            OFTblModProvider._instance = OFTblModProvider()
        return OFTblModProvider._instance
    
    
    
    
    def ofAddFlow(self, datapath, match, actions, priority=ofproto13.OFP_DEFAULT_PRIORITY, idle_timeout = 0, buffer_id=None):
        """" Utility method: add OpenFlow table entry"""
        
        LOG.info("**ADD_FLOW: dp: %s | match: %s | actions: %s | prio: %s", datapath.id, match, actions, priority)
        
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
    
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, idle_timeout=idle_timeout, 
                                    match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, idle_timeout=idle_timeout,
                                    instructions=inst)
        datapath.send_msg(mod)
        # update flow table db
        self.flow_table_cache.insert_dp(datapath.id)
        self.flow_table_cache.insert_flow_entry(mod)


    def ofDelFlow(self, datapath, match, priority = ofproto13.OFP_DEFAULT_PRIORITY):
        """" Utility method: del OpenFlow table entry"""
        
        LOG.info("**DEL_FLOW: dp: %s | match: %s | prio: %s", datapath.id, match, priority)
        
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        mod = parser.OFPFlowMod(datapath = datapath, command = ofproto13.OFPFC_DELETE_STRICT, 
                                priority = priority, match = match,
                                out_port = ofproto13.OFPP_ANY, out_group = ofproto13.OFPG_ANY)
        datapath.send_msg(mod)
        
        
    
    def ofPckOut(self, msg, out_port):
        """ Utility method: send OpenFlow PacketOut"""
            
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(out_port)]
        
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
            
        of_pckOut = parser.OFPPacketOut(datapath = datapath, buffer_id = msg.buffer_id,
                                        in_port = msg.match['in_port'], actions = actions, data = data)
        
        pck = packet.Packet(msg.data)
        LOG.info("**PKT_OUT: dp: %s | msg: %s | out_port: %s", datapath.id, (pck,), out_port)
        
        datapath.send_msg(of_pckOut)
        
        
    def ofSendPck(self, datapath, pkt, port):
        
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        pkt.serialize()
        data = pkt.data
        actions = [parser.OFPActionOutput(port = port)]
        of_pkt= parser.OFPPacketOut(datapath = datapath, buffer_id = ofproto.OFP_NO_BUFFER,
                                        in_port = ofproto.OFPP_CONTROLLER, actions = actions, data = data)
        datapath.send_msg(of_pkt)
            
        
        