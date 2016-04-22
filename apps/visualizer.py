'''
Created on Feb 25, 2016

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
from ryu.lib.dpid import str_to_dpid, dpid_to_str
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
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from pylab import *
import ytime
import threading
import thread
from multiprocessing import Process, Queue

from metric_providers import trustevents
from trust_based_forwarder import TrustBasedForwarder
from ofp_table_mod.of_tbl_mod_provider import OFTblModProvider
from service_manager import ServiceManager, ServiceDiscoveryPacket
from metric_providers.metric_provider import get_links_metric
from metric_providers.trust_metric_provider import TrustMetricProvider
from pip.locations import src_prefix


LOG = logging.getLogger(__name__)       # module logger



class MetricPlotter(app_manager.RyuApp):
    

    def __init__(self, *args, **kwargs):
        
        super(MetricPlotter, self).__init__(*args, **kwargs)
        self.name = "metric_plotter"
        
        self.links_queue = Queue()
    
        
    def start(self):
        app_manager.RyuApp.start(self) #TODO check the override method
        hub.spawn(self.log_trust_data)
        hub.spawn(self.load_plotter_engine)
        
        
    def load_plotter_engine(self):
        
        plotter_engine = Plotter(self.links_queue)
        plotter_engine.start()
        #plotter = MultiPlotter(self.links_queue, self.link_features)
        #plotter.start()
    
    
    def log_trust_data(self):
        
        while True:
            trust_metric_prov_ref = app_manager.lookup_service_brick('trust_metric_provider')
            trust_frw_ref = app_manager.lookup_service_brick('trusted_based_forwarder')
            self.link_features = trust_metric_prov_ref.link_features
            link_metric = trust_metric_prov_ref.links_metric
            
            #for link in self.link_features.keys():
            #    self.link_features[link]['metric'] = link_metric[link]
                
            #self.links_queue.put(self.link_features)
            
            for (s,d,w) in trust_frw_ref.net.edges(data='weight'):
                if str(s) == '4' and str(d) == '2':
                    self.links_queue.put(1-w)
            hub.sleep(1)
            
            

'''
class MultiPlotter(Process):
    
    fig, ax = plt.subplots()
    plt.subplots_adjust(bottom=0.2)
    ax.grid()
    axnext = plt.axes([0.81, 0.05, 0.1, 0.075])
    bnext = Button(axnext, 'Next')
    
    line, = ax.plot([], [], lw=2)
    xdata = []
    ydata = []
    
    class Link_data():
        ydata = []
        xdata = []
    
    
    def __init__(self, queue, link_features):
            
        super(MultiPlotter, self).__init__()
        self.queue = queue
        self.links_data = {}
        for link in link_features:
            self.links_data.setdefault(link, self.Link_data() ) 
            
    def init_graph(self):
        
        self.ax.set_ylim(0.0, 1.0)
        self.ax.set_xlim(0, 50)
        del self.xdata[:]
        del self.ydata[:]
        self.line.set_data(self.xdata, self.ydata)
        return self.line, 
    
    
    def run(self):
        
        self.start_time = ytime.ytime()
        print 'starting gui and queue reader'
        
        self.anim = animation.FuncAnimation(self.fig, self.update_plot, blit=False, interval=20,
                                            repeat=False, init_func=self.init_graph )
        plt.show()
        ytime.sleep(2)
        
        
    def update_plot(self, data):
        
        delta_time = ytime.ytime() - self.start_time
        
        try:
            msg = self.queue.get(block=False)
        
            for link in self.links_data:
                self.links_data[link].xdata.append( delta_time )
                self.links_data[link].ydata.append( msg[link]['metric'] )
            
        except Exception:
            for link in self.links_data:
                self.links_data[link].xdata.append( delta_time )
                yd = self.links_data[link].ydata
                last_value = yd[ len(yd)-1 ]
                self.links_data[link].ydata.append( last_value )
        
        
        xmin, xmax = self.ax.get_xlim()
        
        if delta_time >= xmax:
            self.ax.set_xlim(xmin, 2*xmax)
            self.ax.figure.canvas.draw()
        
        xdata = []
        ydata = []
        for link in self.links_data:
            if str(link.src.dpid) == '4' and str(link.dst.dpid) == '2': 
                xdata = self.links_data[link].xdata
                ydata = self.links_data[link].ydata
                break
                
        self.line.set_data(xdata, ydata)
        return self.line,
'''    
    

class Plotter(Process):    
    
    fig, ax = plt.subplots()
    plt.subplots_adjust(bottom=0.2)
    ax.grid()
    axnext = plt.axes([0.81, 0.05, 0.1, 0.075])
    bnext = Button(axnext, 'Next')
    
    line, = ax.plot([], [], lw=2)
    xdata, ydata = [], []
        
        
    class Index():
        
        def __init__(self, indexes):
            self.indexes = indexes
            self.ind = 0
            
        def next(self, event):
            self.ind += 1
            self.ind = self.ind % len(self.indexes)
            
    
    def __init__(self, queue):
            
        super(Plotter, self).__init__()
        self.queue = queue
        self.actual_value = 0.99
    
    
    def init_graph(self):
        
        self.ax.set_ylim(0.0, 1.0)
        self.ax.set_xlim(0, 50)
        del self.xdata[:]
        del self.ydata[:]
        self.line.set_data(self.xdata, self.ydata)
        return self.line, 
    
        
    def run(self):
        
        self.start_time = ytime.time()
        print 'starting gui and queue reader'
        
        self.anim = animation.FuncAnimation(self.fig, self.update_plot, blit=False, interval=20,
                                            repeat=False, init_func=self.init_graph )
        plt.show()
        ytime.sleep(2)
    

    def update_plot(self, data):
        
        try:
            msg = self.queue.get(block=False)
            self.actual_value = float(msg)
        except Exception:
            pass
        
        metric = self.actual_value
        
        delta_time = ytime.time() - self.start_time
        
        self.xdata.append(delta_time)
        self.ydata.append(metric)
        xmin, xmax = self.ax.get_xlim()
        
        if delta_time >= xmax:
            self.ax.set_xlim(xmin, 2*xmax)
            self.ax.figure.canvas.draw()
        self.line.set_data(self.xdata, self.ydata)
        return self.line,
        