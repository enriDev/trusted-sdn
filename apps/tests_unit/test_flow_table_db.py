'''
Created on Feb 6, 2016

@author: root
'''

import logging

from ..ofp_table_mod.flow_table_db import FlowTableDb

from ryu.ofproto import ofproto_protocol
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.ofproto.ether import ETH_TYPE_ARP
from ryu.lib.mac import BROADCAST_STR
from ryu.lib.packet.arp import ARP_REQUEST, ARP_REPLY
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER


LOG = logging.getLogger(__name__)

class Test_FlowTableDb():
    
    def __init__(self):
        
        self.flow_db = FlowTableDb("test_db")
   
                    
    def test_insert_dp(self):
        
        for i in range(1,5):
            self.flow_db.insert_dp(i)
        print "5 datapath inserted"
        
"""        
    def test_insert_flow_entry(self):
        
        # flow entry 1
        dp = Datapath()
        prio = 155
        timeout = 20
        match = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REQUEST)
        actions = []
        inst = [parser13.OFPInstructionActions(ofproto13.OFPIT_APPLY_ACTIONS, actions)]
        
        of_mod_1 = parser13.OFPFlowMod(datapath=dp, priority=prio,
                            match=match, idle_timeout=timeout,
                            instructions=inst)
        
        #flow entry 2
        dp = Datapath()
        prio = 200
        timeout = 30
        match= parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REPLY)
        actions = [parser13.OFPActionOutput(ofproto13.OFPP_CONTROLLER, ofproto13.OFPCML_NO_BUFFER)]
        inst = [parser13.OFPInstructionActions(ofproto13.OFPIT_APPLY_ACTIONS, actions)]
        
        of_mod_2 = parser13.OFPFlowMod(datapath=dp, priority=prio,
                            match=match, idle_timeout=timeout,
                            instructions=inst)
"""              

            


if __name__ == '__main__':
    
    test_db = Test_FlowTableDb()
    test_db.test_insert_dp()          
                
                
                
                
                
                
                
                
                
                
                

