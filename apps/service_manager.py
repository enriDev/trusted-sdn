'''
Created on Jan 26, 2016

@author: root
'''


import sys
import logging
import struct
import ConfigParser

from ryu.base import app_manager
from ryu.controller import handler
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.ofproto import ofproto_v1_0 as ofproto10
from ryu.ofproto.ether import ETH_TYPE_LLDP, ETH_TYPE_ARP
from ryu.lib.mac import haddr_to_bin, BROADCAST, BROADCAST_STR
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp
from ryu.lib import dpid
from ryu.topology.api import get_switch, get_link, get_host
from ryu.app.wsgi import ControllerBase
from ryu.topology.event import EventSwitchEnter
from ryu.lib import hub
from ryu.lib.packet.arp import ARP_REQUEST, ARP_REPLY
from __builtin__ import True
from ryu.ofproto.ofproto_v1_3 import OFP_NO_BUFFER
from ryu.lib.dpid import str_to_dpid
from ryu.controller import handler
from ryu.controller import event
from ryu.exception import RyuException


import networkx as nx


import trust_event
import of_tb_func as of_func
import trust_based_forwarder as tbs
from security_class import SecurityClass




SERVICE_CFG_PATH = 'services_cfg.conf'  # conf file path for services
LOG = logging.getLogger(__name__)       # module logger


class EventServiceDiscovered(event.EventBase):
    """ Announce the discovery of a Service """
    
    def __init__(self, service, dpid, port):
        
        super(EventServiceDiscovered, self).__init__()
        self.service = service
        self.dpid = dpid
        self.port = port


class ServiceManager(app_manager.RyuApp):
    
    
    TIMEOUT = 10            # time interval between discovery probing
    NUM_PROB_PKT = 2        # nr probing pkts sent for services discovery
    PROB_SEND_GUARD = 0.5   # interval for avoiding burst
    TRUST_THRES_DEF = 1     # define which security class must use trusted routing
    
    
    _EVENTS = [EventServiceDiscovered]
    
    class ServiceNotFound(RyuException):
        message = '%(msg)s'
        
        
    def __init__(self, *args, **kwargs):
        
        super(ServiceManager, self).__init__(*args, **kwargs)
        self.name = "ServiceManager"
        
        self.dp_dict = {}            # dpid -> datapath
        self.services_dict = {}      # service ip -> service obj
        self.discovered_service = 0  # counter for discovered services 
        
        self.load_services_config()


    def load_services_config(self):
         
        self.config = ConfigParser.ConfigParser()
        self.config.read(SERVICE_CFG_PATH) 

        try:       
            services = self.config.sections()
            for service in services:
                params = self.config.options(service)
                param_dict = {}
                for param in params:
                    param_dict[param] = self.config.get(service, param)
                service_obj = Service(**param_dict)
                service_ip = service_obj.ip
                self.services_dict[service_ip] = service_obj
                
            LOG.info("SERVICE_MGR: services loaded:")
            LOG.info(self.services_dict)
            
        except ConfigParser.Error:
            LOG.info("SERVIE_MGR: error during conf services loading.")
            
            
    def get_service_from_mac(self, mac):
        
        for service in self.services_dict.values():
            if service.mac == mac:
                return service
        return None
    
    
    def set_routing_path_method(self, ip_dst, ip_src):
        
        service = None
        if ip_dst in self.services_dict.keys():
            service = self.services_dict[ip_dst]
            
        elif ip_src in self.services_dict.keys():
            service = self.services_dict[ip_src]
            
        else:
            raise self.ServiceNotFound
        
        # the service is or dst either src
        # evaluate security class
        print 'SERVICE_MGR: flow with: ', service.ip, ' sec clss: ', service.security_class
        serv_sec_cl = service.security_class
        if SecurityClass[serv_sec_cl] <= self.TRUST_THRES_DEF:
            return tbs.TrustedRoutingPath()
        return tbs.RandomRoutingPath()
            
        
    
    @set_ev_cls(ofp_event.EventOFPStateChange, CONFIG_DISPATCHER)
    def set_flowtable(self, ev):
        
        datapath = ev.datapath
        
        # drop arp requests to avoid arp storm
        match_arp_req = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REQUEST)
        actions_arp_req = []
        of_func.ofAddFlow(datapath, match_arp_req, actions_arp_req)
        
        # forward arp replies to the controller
        match_arp_rep = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REPLY)
        actions_arp_rep = [parser13.OFPActionOutput(ofproto13.OFPP_CONTROLLER, ofproto13.OFPCML_NO_BUFFER)]
        of_func.ofAddFlow(datapath, match_arp_rep, actions_arp_rep)

    
    def setup_flowtable(self, datapath):
        
        # drop arp requests to avoid arp storm
        match_arp_req = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REQUEST)
        actions_arp_req = []
        of_func.ofAddFlow(datapath, match_arp_req, actions_arp_req)
        
        # forward arp replies to the controller
        match_arp_rep = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REPLY)
        actions_arp_rep = [parser13.OFPActionOutput(ofproto13.OFPP_CONTROLLER, ofproto13.OFPCML_NO_BUFFER)]
        of_func.ofAddFlow(datapath, match_arp_rep, actions_arp_rep)
    
    
    def reset_flowtable(self, datapath):
        
        # drop arp requests to avoid arp storm
        match_arp_req = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REQUEST)
        of_func.ofDelFlow(datapath, match_arp_req)
        
        # forward arp replies to the controller
        match_arp_rep = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REPLY)
        of_func.ofDelFlow(datapath, match_arp_rep)
    
        
    @set_ev_cls(EventSwitchEnter, MAIN_DISPATCHER)
    def _probe_switch(self, ev):
        
        datapath = ev.switch.dp
        #datapath = ev.datapath
        #ofproto = datapath.ofproto
        #parser = datapath.ofproto_parser
        
        self.dp_dict[datapath.id] = datapath
        #self.setup_flowtable(datapath)
        
        for service in self.services_dict.values():
            
            discovery_pkt = ServiceDiscoveryPacket.build_from_service(service)
            for i in range(0, self.NUM_PROB_PKT):
                of_func.ofSendPck(datapath, discovery_pkt, ofproto13.OFPP_FLOOD)
                
    
                
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def service_discovery_packet_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        in_port = msg.match["in_port"]
            
        try:
            sdp = ServiceDiscoveryPacket(self)
            service = sdp.parse(msg.data)
            
            if service.discovered:
                # return if service already discovered
                return
            
            #print "Found new service: ",service.name,"-",service.ip,"-",service.discovered
            event = EventServiceDiscovered(service, dpid, in_port)
            self.send_event_to_observers(event)
            
            #self.reset_flowtable(datapath)
            
            # update the status of service (discovered)
            self.services_dict[service.ip].discovered = True
            self.discovered_service += 1
            print "discovered services:",self.discovered_service, '-',service.ip
            if self.all_services_discovered():
                self.stop_service_discovery()
                LOG.info("SERVICE_MGR: All services discovered.")
                
        except sdp.InvalidServiceDiscoveryPacket:
            # this handler could handle other pkt type
            # Ignore silently
            pass
            
    def all_services_discovered(self):
        return self.discovered_service == len(self.services_dict)
      
        
    
    def stop_service_discovery(self):
        self.unregister_handler(ofp_event.EventOFPPacketIn, self.service_discovery_packet_handler)
        self.unregister_handler(EventSwitchEnter, self._probe_switch)
        for datapath in self.dp_dict.values():
            self.reset_flowtable(datapath)


class ServiceDiscoveryPacket():
        
    #TODO the src ip should be computed from the service ip
    # For a valid arp req it must be an address belonging to the service lan
    src_ip = '10.0.0.255'
    #TODO the mac should point to the controller
    CONTROLLER_MAC = '01:02:03:04:05:06'
    
    class InvalidServiceDiscoveryPacket(RyuException):
        message = '%(msg)s'
    
    def __init__(self, service_manager):
        self.service_manager = service_manager
        
        
    def parse(self, data):
        
        pck = packet.Packet(data)    
        eth_pkt = pck.get_protocol(ethernet.ethernet)
        arp_pkt = pck.get_protocol(arp.arp)
    
        if not arp_pkt or arp_pkt.opcode !=  ARP_REPLY:
            raise self.InvalidServiceDiscoveryPacket()
        
        # the mac src must be the mac of a valid service
        try:
            service = self.service_manager.get_service_from_mac(eth_pkt.src)
            # the pkt is valid ServiceDiscovery response
            return service 
        
        except ServiceManager.ServiceNotFound():
            raise self.InvalidServiceDiscoveryPacket(
                    msg = 'ServiceDiscovery from invalid service: %s' % eth_pkt.src)
        
    @staticmethod
    def build_from_service(service):
        
        pkt = packet.Packet()
        pkt.add_protocol( ethernet.ethernet( ethertype =  ETH_TYPE_ARP, 
                                             src = ServiceDiscoveryPacket.CONTROLLER_MAC, 
                                             dst = BROADCAST_STR) )
        pkt.add_protocol( arp.arp( opcode = ARP_REQUEST, 
                                   src_mac = ServiceDiscoveryPacket.CONTROLLER_MAC, 
                                   src_ip = ServiceDiscoveryPacket.src_ip,   #TODO change srcmac and src ip
                                   dst_mac = BROADCAST_STR, dst_ip = service.ip) )          
        return pkt
    
    @staticmethod
    def build_match_from_service(service):
        
        match_arp_rep = parser13.OFPMatch(eth_type = ETH_TYPE_ARP, arp_op = ARP_REPLY,
                                          arp_spa = service.ip )
        return match_arp_rep
    
    




class Service():
    
    def __init__(self, name, ip, mac, security_class = 'public', discovered = False):
        self.name = name
        self.ip = ip
        self.mac = mac
        self.security_class = security_class
        self.discovered = discovered




        
