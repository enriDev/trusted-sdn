'''
Created on Nov 29, 2015

- Unique module that learns hosts on-the fly
- Discard doubled ARP requests to avoid ARP storming 

@version: 1.0
@author: root
'''

import sys
import logging
import struct
import ConfigParser
import six
import abc
from random import randint

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
from ryu.lib.mac import BROADCAST_STR
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import icmp
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp
from ryu.lib.packet import lldp
from ryu.lib import dpid
from ryu.topology.api import get_switch, get_link, get_host
from ryu.app.wsgi import ControllerBase
from ryu.topology import event
from ryu.lib import hub
from ryu.lib.packet.arp import ARP_REQUEST, ARP_REPLY
from __builtin__ import True

import networkx as nx

from metric_providers import trustevents
from ofp_table_mod.of_tbl_mod_provider import OFTblModProvider
from service_manager import ServiceManager, ServiceDiscoveryPacket
from metric_providers.metric_provider import get_links_metric
from metric_providers.trust_metric_provider import TrustMetricProvider
from gi.overrides import deprecated


LOG = logging.getLogger(__name__)       # module logger


# required apps for TrustBasedForwarder 
# TODO integrate as a additional option in ryu manager
app_manager.require_app('metric_providers.trust_metric_provider')




class TrustBasedForwarder(app_manager.RyuApp):
    
    OFP_VERSION = [ofproto13.OFP_VERSION, ofproto10.OFP_VERSION]
    
    TABLE_MISS_PRIORITY = 0         # lowest priority
    LLDP_PRIORITY = 0xFFFF          # priority for lldp flow entry  
    IDLE_TIME_OUT = 15              # idle time out for new flow entries
    DEF_EDGE_WEIGHT = 0.01          # default link weight
    
    # weight used to balance a new trust update
    # The NEW_TRUST_VALUE_WEIGHT = (1 - OLD_TRUST_VALUE_WEIGHT)
    OLD_TRUST_VALUE_WEIGHT = 0.6
    METRIC_UPDATE_INTER = 7        # interval between metric update


    def __init__(self, *args, **kwargs):
        
        super(TrustBasedForwarder, self).__init__(*args, **kwargs)
        self.name = "trusted_based_forwarder"
        self.CONF.observe_links = True      #observe link option !!Not working
        self.topology_api_app = self        # self reference for topology api
        self.net = nx.DiGraph()             # graph topology
        self.dp_ref_dict = {}               # dpid -> datapath  
        self.cache_ip_mac = {}              # ip -> mac
        
        self.of_provider = OFTblModProvider()
        
        #trial for metric request
        self.threads.append( hub.spawn_after(self.METRIC_UPDATE_INTER, self.metric_update_loop) )
    

    
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def setup_flowtable(self, ev):
        
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # install table-miss flow entry
        # BUFFER option set so that the pkt are 
        # buffered on switch
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]   #TODO set buffer on the switched
        priority = TrustBasedForwarder.TABLE_MISS_PRIORITY
        self.of_provider.ofAddFlow(datapath, match, actions, priority)
        
        # install lldp packet flow entry
        # OFPCML_NO_BUFFER is set so that the LLDP is not
        # buffered on switch
        match = parser.OFPMatch(
                            eth_type=ETH_TYPE_LLDP,
                            eth_dst=lldp.LLDP_MAC_NEAREST_BRIDGE)
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        priority = TrustBasedForwarder.LLDP_PRIORITY
        self.of_provider.ofAddFlow(datapath, match, actions, priority, buffer_id=ofproto.OFPCML_NO_BUFFER)
    
    
    @set_ev_cls(event.EventSwitchEnter, MAIN_DISPATCHER)
    def _new_switch_event(self, ev):
             
        LOG.info('TOPO_EVENT: New switch detected %016x', ev.switch.dp.id)
        
        # add switches
        switch_list = get_switch(self.topology_api_app, None)
        #switches = [switch.dp.id for switch in switch_list]
        switches = []
        for switch in switch_list:
            switches.append(switch.dp.id)
            self.dp_ref_dict[switch.dp.id] = switch.dp
            
        self.net.add_nodes_from(switches)
                
        #print '****List of switches:'
        #print switches
        #for sw in switch_list:
        #    for p in sw.ports:
        #        print p
        
        
    @set_ev_cls(event.EventSwitchLeave)
    def _switch_leave_event(self, ev):
        
        LOG.info('TOPO_EVENT: !!!! ALERT Switch leave %016x', ev.switch.dp.id)
        #TODO handle the switch leave event
        
    @set_ev_cls(event.EventLinkAdd, MAIN_DISPATCHER)
    def _new_link_event(self, ev):
        
        LOG.info('TOPO_EVENT: New link detected %s -> %s', ev.link.src.dpid, ev.link.dst.dpid)
        
        link_list = get_link(self.topology_api_app, None)
        links = [(link.src.dpid, link.dst.dpid, {'port':link.src.port_no, 'weight':self.DEF_EDGE_WEIGHT}) for link in link_list]
        self.net.add_edges_from(links)
        
        print '****List of links:'
        print links
        
    
    @set_ev_cls(event.EventLinkDelete)
    def _link_delete_event(self,ev):
        
        LOG.info('TOPO_EVENT: !!!! ALERTLink deleted %s -> %s', ev.link.src.dpid, ev.link.dst.dpid)
    
    
    #set_ev_cls(service_manager.EventServiceDiscovered)
    def service_discovered_event(self, ev):
        
        LOG.info('TOPO_EVENT: New service detected: %s - %s', ev.service.name, ev.service.ip)
        
        service = ev.service
        dpid = ev.dpid
        port = ev.port
        mac = service.mac
        
        self.net.add_node(mac)
        self.net.add_edge(dpid, mac, {'port':port})
        self.net.add_edge(mac, dpid)
        
        self.cache_ip_mac[service.ip] = mac
        
    
        
    @set_ev_cls(event.EventHostAdd, MAIN_DISPATCHER)
    def _new_host_event(self, ev):   
        
        host = ev.host
        host_mac = host.mac
        dp_port = host.port.port_no
        dpid = host.port.dpid
        
        # TODO temporary solution for fake host discovery. Refactoring needed
        if host_mac == ServiceDiscoveryPacket.CONTROLLER_MAC:
            return
        
        # check if host already in net graph
        if host_mac not in self.net:
            LOG.info('TOPO_EVENT: New host detected: %s - %s', ev.host.mac, ev.host.ipv4) 
            self.net.add_node(host_mac)  
            self.net.add_edge(dpid, host_mac, {'port': dp_port})
            self.net.add_edge(host_mac, dpid)
            self.cache_ip_mac[host.ipv4[0]] = host_mac
            LOG.info('update ip-mac cache: %s', self.cache_ip_mac)
                
        
    #deprecated
    #set_ev_cls(trust_event.EventLinkTrustChange, MAIN_DISPATCHER)
    def _link_trust_change_handler(self, ev):
        
        link = ev.link
        trust = ev.link_trust
        #LOG.info('TRUST_EVENT: Trust Metric update for link: %s -> %s - TM: %s%%', link.src.dpid, link.dst.dpid, trust*100)
        
        # keep a minimun trust value for dijkstra algorithm
        if trust < self.DEF_EDGE_WEIGHT: 
            trust = self.DEF_EDGE_WEIGHT
        
        self.update_link_trust (link, trust)
        
    
    def metric_update_loop(self):
        
        LOG.info('TRUST_FORWARDER: Starting metric update loop (%ss interval)...', 
                 self.METRIC_UPDATE_INTER)
        
        while True:
            links_metric = get_links_metric(self, TrustMetricProvider.APP_NAME)
            print 'metric update: '
            for lk in links_metric.keys():
                print lk.src.dpid,' -> ', lk.dst.dpid, ' : ', links_metric[lk]
                self.update_link_trust(lk, links_metric[lk])
                
            hub.sleep(self.METRIC_UPDATE_INTER)
    
    
    def update_link_trust(self, link, metric_value):
        """ Allow to edit the edges weight of the graph"""
        
        src = link.src.dpid
        dst = link.dst.dpid

        try:
            #cur_val = self.net[src][dst]['weight']

            #LOG.info('TOPO_EDGE_WEIGHT: updating trust metric: %s -> %s = %s', src, dst, metric_value)
            self.net[src][dst]['weight'] = metric_value
            
        except KeyError as e:
            LOG.info('TOPO_EDGE_WEIGHT: node not found: %016x ...', e.args[0])
   
       
    #
    # At this point the controller has a global view of the network.
    # The packet are forwarded based on shortest path first computation.
    # Exceptions in forwarding are needed:
    # - arp msgs are managed by ArpProxy object
    # - lldp msgs are ignored
    #
    
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
            
        pck = packet.Packet(msg.data)        
        eth = pck.get_protocol(ethernet.ethernet)
        src = eth.src
        dst = eth.dst
        dpid = datapath.id
        
        # ignore lldp packet
        if eth.ethertype == ETH_TYPE_LLDP:
            return
        
        # ignore broadcast src
        if src == BROADCAST_STR:
            return
        
        #LOG.info('\n'+'**PKT-IN: from dpid %s: %s \n',dpid, (pck,))
        
        ip_dst = ip_src = None
        
        # arp packet, update ip address
        if eth.ethertype == ETH_TYPE_ARP:
    
            arp_pkt = pck.get_protocols(arp.arp)[0]
            ip_dst = arp_pkt.dst_ip
            ip_dst = arp_pkt.src_ip

        # ipv4 packet, update ipv4 address
        elif eth.ethertype == ETH_TYPE_IP:
            ipv4_pkt = pck.get_protocols(ipv4.ipv4)[0]
            ip_dst = ipv4_pkt.dst
            ip_src = ipv4_pkt.src
        
        else:
            LOG.info("TRUST_FORWARDER: Unhandled case, ip not found:")
            LOG.info('\t'+'From dpid %s: %s \n',dpid, (pck,))
            return
        
        routing_path = self.set_routing_path_method(ip_dst, ip_src)    
        
        try:
            # retrive the mac from ip
            dst = self.cache_ip_mac[ip_dst]
        except KeyError:
            LOG.info("TRUST_FORWARDER: ip->mac mapping error")
            return 
        
        LOG.info("TRUST_FORWARDER: RoutingPath used: %s", routing_path.__class__.__name__)
        path = routing_path.compute_routing_path(dpid, dst)
        self.install_routing_path(path, msg)
     
     
    def set_routing_path_method(self, ip_dst, ip_src):
        
        routing_path = RandomRoutingPath(self.net)
        srv_mgr_ref = app_manager.lookup_service_brick('ServiceManager')
        
        try:
            # ask for routing_path object in case of msg directed to service
            routing_path = srv_mgr_ref.set_routing_path_method(ip_dst, ip_src)
            routing_path.net = self.net
        except AttributeError:
            # this error is raised for None value @srv_mgr_ref
            # ignore silently
            pass
        except ServiceManager.ServiceNotFound:
            # the dst_ip or src_ip are not registered services: use non-trusted path
            pass
        return routing_path
                    
             
    def compute_routing_path(self, src, dst, weight = None):
        """ Return a list of nodes for the path
            @weight String. If "weight" trusted path is computed 
        """        
        try:
            LOG.info("PATH_SEARCH: Path %s --> %s",src, dst)
            path = nx.shortest_path(self.net, src, dst, weight)
            LOG.info("PATH_SEARCH: Path %s --> %s :\n %s",src, dst, path)
            return path
        
        except nx.NetworkXNoPath:
            if dst not in self.net:
                LOG.info('NET_VIEW: Dst not found: %s', dst)
            else:
                LOG.info('NET_VIEW: No path found: %s -> %s ', src, dst)
        except nx.NetworkXError as e:
            LOG.info('NET_VIEW: Node not found: %s', e.args)
  
      
    def install_routing_path(self, path, msg):
        """ Set the flow tables for the new routing path and
            forward the message
        """
        if path != None:
            
            pck = packet.Packet(msg.data)        
            eth = pck.get_protocol(ethernet.ethernet)
            src = eth.src
            dst = eth.dst
            
            # build match from msg
            match = CustomOFPMatch.build_from_msg(msg)
            print "DEBUG: build match from msg:/n", match 
            
            # exclude in the loop the last node in the path because it is an host
            for i in range( len(path)-2, -1, -1 ):
                
                node = path[i]
                out_port = self.get_next_out_port(path, node)
                datapath = self.dp_ref_dict.get(node)
                
                actions = [parser13.OFPActionOutput(out_port)]
                self.of_provider.ofAddFlow(datapath = datapath, match = match,
                        actions = actions, idle_timeout = self.IDLE_TIME_OUT, buffer_id = msg.buffer_id)
        
        
    def get_next_out_port(self, path, node):
        
        next_hop = path[ path.index(node)+1 ]
        out_port = self.net[node][next_hop]['port']
        return out_port



class RoutingPathBase(object):
    __metaclass__ = abc.ABCMeta
    
    def __init__(self, network_graph=None):
        self.net = network_graph
    
    @abc.abstractmethod
    def compute_routing_path(self, src, dst):
        """ Return a list of nodes for the path
            @weight String. Indicate the attribute to be used for 
                    shortest path algorithm
        """  
        return

class RandomRoutingPath(RoutingPathBase):
    
    def __init__(self, network_graph=None):
        super(RandomRoutingPath, self).__init__(network_graph)
        
    def compute_routing_path(self, src, dst):
        
        try:
            LOG.info("PATH_SEARCH: Path %s --> %s",src, dst)
            
            path_generator = nx.all_shortest_paths(self.net, src, dst, weight=None) 
            path_list = [p for p in path_generator]
            selected_path = randint( 0, len(path_list)-1 )
            path = path_list[selected_path]
            
            LOG.info("PATH_SEARCH: Path %s --> %s :\n %s",src, dst, path)
            return path
        
        except nx.NetworkXNoPath:
            if dst not in self.net:
                LOG.info('NET_VIEW: Dst not found: %s', dst)
            else:
                LOG.info('NET_VIEW: No path found: %s -> %s ', src, dst)
        except nx.NetworkXError as e:
            LOG.info('NET_VIEW: Node not found: %s', e.args)
        
        
        
class TrustedRoutingPath(RoutingPathBase):
    
    def __init__(self, network_graph=None):
        super(TrustedRoutingPath, self).__init__(network_graph)
        
    def compute_routing_path(self, src, dst):
      
        try:
            LOG.info("PATH_SEARCH: Path %s --> %s",src, dst)
            path = nx.dijkstra_path(self.net, src, dst, weight='weight')
            LOG.info("PATH_SEARCH: Path %s --> %s :\n %s",src, dst, path)
            return path
        
        except nx.NetworkXNoPath:
            if dst not in self.net:
                LOG.info('NET_VIEW: Dst not found: %s', dst)
            else:
                LOG.info('NET_VIEW: No path found: %s -> %s ', src, dst)
        except nx.NetworkXError as e:
            LOG.info('NET_VIEW: Node not found: %s', e.args)




class CustomOFPMatch():
    
    @staticmethod
    def build_from_msg(msg):
        
        pck = packet.Packet(msg.data)   
        match_fields = {}               # match_field -> value
        
        try:     
            i = iter(pck)

            ## layer 2
            # ethernet
            eth_pkt = six.next(i)
            assert type(eth_pkt) == ethernet.ethernet
            match_fields['eth_dst'] = eth_pkt.dst
            match_fields['eth_src'] = eth_pkt.src
            match_fields['eth_type'] = eth_pkt.ethertype
            
            # layer 2.5 - 3
            net_pkt = six.next(i) 
    
            # arp
            if type(net_pkt) ==  arp.arp:
                #match_fields['arp_op'] = net_pkt.opcode
                match_fields['arp_spa'] = net_pkt.src_ip
                match_fields['arp_tpa'] = net_pkt.dst_ip
                #match_fields['arp_sha'] = net_pkt.src_mac
                #match_fields['arp_tha'] = net_pkt.dst_mac
                del match_fields['eth_dst']
            
            # ip 
            elif type(net_pkt) == ipv4.ipv4:
                match_fields['ip_proto'] = net_pkt.proto
                match_fields['ipv4_src'] = net_pkt.src
                match_fields['ipv4_dst'] = net_pkt.dst
            
            # layer 3.5 - 4
            net_pkt = six.next(i)
            
            # icmp
            #if type(net_pkt) == icmp.icmp:
            #    match_fields['icmpv4_type'] = net_pkt.type
            #    match_fields['icmpv4_code'] = net_pkt.code
                
            #TODO udp,tcp
            
        except StopIteration:
            # the packet has no more layer.
            # The match has been build
            pass 
        
        match = parser13.OFPMatch(**match_fields)
        return match



        
        
        
        
        
        
        
        
        
