'''
Created on Dec 8, 2015

@author: root
'''

import logging

from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.lib.packet import packet
from ryu.ofproto.ofproto_v1_3 import OFPFC_DELETE, OFPFC_DELETE_STRICT, OFPP_ANY,\
    OFPG_ANY


# logger for OpenFlow utility function
OF_LOG = logging.getLogger('OF_LOGGER')


def ofAddFlow(datapath, match, actions, priority=ofproto13.OFP_DEFAULT_PRIORITY, idle_timeout = 0, buffer_id=None):
    """" Utility method: add OpenFlow table entry"""
    
    OF_LOG.info("**ADD_FLOW: dp: %s | match: %s | actions: %s | prio: %s", datapath.id, match, actions, priority)
    
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


def ofDelFlow(datapath, match, priority = ofproto13.OFP_DEFAULT_PRIORITY):
    """" Utility method: del OpenFlow table entry"""
    
    OF_LOG.info("**DEL_FLOW: dp: %s | match: %s | prio: %s", datapath.id, match, priority)
    
    ofproto = datapath.ofproto
    parser = datapath.ofproto_parser
    
    mod = parser.OFPFlowMod(datapath = datapath, command = OFPFC_DELETE_STRICT, priority = priority,
                            match = match, out_port = OFPP_ANY, out_group = OFPG_ANY)
    datapath.send_msg(mod)
    
    

def ofPckOut(msg, out_port):
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
    OF_LOG.info("**PKT_OUT: dp: %s | msg: %s | out_port: %s", datapath.id, (pck,), out_port)
    
    datapath.send_msg(of_pckOut)
    
    
def ofSendPck(datapath, pkt, port):
    
    ofproto = datapath.ofproto
    parser = datapath.ofproto_parser
    pkt.serialize()
    data = pkt.data
    actions = [parser.OFPActionOutput(port = port)]
    of_pkt= parser.OFPPacketOut(datapath = datapath, buffer_id = ofproto.OFP_NO_BUFFER,
                                    in_port = ofproto.OFPP_CONTROLLER, actions = actions, data = data)
    datapath.send_msg(of_pkt)
        