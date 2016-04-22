'''
Created on Apr 21, 2016

@author: root
'''
import os
import sys
import logging
import struct
import ConfigParser
import six
import abc
from random import randint
import inspect
import datetime
from os.path import isfile, getsize

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
import time
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


import sqlite3 as lite
from ofp_table_mod.singleton import Singleton
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.lib.dpid import dpid_to_str
  

LOG = logging.getLogger(__name__)       # module logger

MODULE_PATH = os.path.dirname( os.path.abspath(__file__) ) 


class TrusterLogger(app_manager.RyuApp):
    

    def __init__(self, *args, **kwargs):
        
        super(TrusterLogger, self).__init__(*args, **kwargs)
        self.name = "truster_logger"
        self.trust_db = TrustDB()
        
    def start(self):
        app_manager.RyuApp.start(self) #TODO check the override method
        hub.spawn_after(4, self.log_trust_data)
        
    @set_ev_cls(event.EventLinkAdd)
    def insert_link_to_trust_db(self, ev):
        
        link = ev.link
        self.trust_db.insert_link(link)
    
    
    def log_trust_data(self):
        
        print 'Starting log trust data...'
        while True:
            trust_metric_prov_ref = app_manager.lookup_service_brick('trust_metric_provider')
            #trust_frw_ref = app_manager.lookup_service_brick('trusted_based_forwarder')
            self.link_features = trust_metric_prov_ref.link_features
            #link_metric = trust_metric_prov_ref.links_metric
            
            timestamp = datetime.datetime.now() 
                        
            for link in self.link_features.keys():
                
                self.trust_db.insert_trust_log(link, timestamp, self.link_features[link])
            
            hub.sleep(1)
            
     



class TrustDB():
    
    __metaclass__ = Singleton
    
    DB_SCHEMA_SQL_PATH = MODULE_PATH + '/trust_db_schema.sql'
    DB_PATH = MODULE_PATH + "/trust_db.db"
    #DB_PATH = ":memory:"                    
    
    class TrustDBError(Exception):
        pass
    
    class EmptySelect(Exception): 
        pass
    
    def __init__(self, db_name = ":memory:"):
        self.db_name = TrustDB.DB_PATH
        self.conn = self.open_db()
        self.session_id = self.create_session()
        LOG.info("TRUST_DB: Database created succesfully: %s", self.db_name)
        
        
    def open_sql_script(self):
        f = open(TrustDB.DB_SCHEMA_SQL_PATH)
        sql = f.read()
        return sql
    
    
    def open_db(self):
        
        if self.isSQLite3(self.db_name):
            conn = lite.connect(self.db_name)
            return conn
        return self.create_db(self.db_name)
    
    
    def isSQLite3(self, db_name):
         
        if not isfile(db_name):
            return False
        fd = open(db_name, 'rb')
        header = fd.read(100)
        return header[:16] == 'SQLite format 3\x00'    

            
    def create_db(self, db_name):
        try:
            sql = self.open_sql_script()
            conn = lite.connect(db_name)
            conn.executescript(sql)
            return conn
        
        except lite.Error as ex:
            raise TrustDB.TrustDBError(
                        "{} - {}".format(type(ex), ex) )
        except IOError as ex:
            raise TrustDB.TrustDBError(
                        "{} - {}".format(type(ex), ex) )
        except Exception as ex:
            raise TrustDB.TrustDBError(
                        "{} - {}".format(type(ex), ex) )
        
        
    def create_session(self):
        
        today = datetime.date.today()
        now = datetime.datetime.now()
        record = (None, today, now)
        cur = self.conn.cursor()
        cur.execute("INSERT INTO session VALUES (?,?,?)", record)
        self.conn.commit()    
        return self.get_session_id()
        
        
    def get_session_id(self):
        
        cur = self.conn.cursor()
        cur.execute("SELECT MAX(session_id) FROM session ")
        row = cur.fetchone()
        return int( row[0] )
    
    
    def get_link_id(self, src, dst):
        
        cur = self.conn.cursor()
        param = (self.session_id, src, dst,)
        cur.execute("SELECT id FROM links WHERE session_id=? AND src=? AND dst=?", param)
        row = cur.fetchone()
        if row is None:
            raise TrustDB.EmptySelect("Link not found in TrustDB")
        return int( row[0] )
         
            
    def insert_link(self, link):
        
        attributes = []
        attributes.append( None )
        attributes.append( link.src.dpid )
        attributes.append( link.dst.dpid )
        attributes.append( self.session_id )
        record = tuple(attributes)
        records = [record]
        
        try:
            cursor = self.conn.cursor()
            cursor.executemany( 'INSERT INTO links VALUES (?,?,?,?)', records)
            self.conn.commit()
            #LOG.info("FLOW_CACHE: insert flow: %s", ofp_flow_mod)
            
        except lite.IntegrityError as ex:
            LOG.info(ex)
        except lite.Error as ex:
            raise TrustDB.TrustDBError(
                        "{} - {}".format( type(ex),ex ) )
        
    
    def insert_trust_log(self, link, time, trust_values):
        """
        link[IN]: link
        time[IN]: datetime.now
        trust_values[IN]: value_name -> value
        """
        
        attributes = []
        
        try:
            
            link_id = self.get_link_id(link.src.dpid, link.dst.dpid)       
            
            attributes.append( None )
            attributes.append( link_id )
            attributes.append( time )
            attributes.append( trust_values['trust_drop_rate'] )
            attributes.append( trust_values['trust_fabr_rate'] )
            attributes.append( trust_values['drop_rate'] )
            attributes.append( trust_values['fabr_rate'] )
            attributes.append( trust_values['trust_value'] )
            record = tuple(attributes)
            records = [record]   
        
            cursor = self.conn.cursor()
            cursor.executemany( 'INSERT INTO trust_logs VALUES (?,?,?,?,?,?,?,?)', records)
            self.conn.commit()
            #LOG.info("FLOW_CACHE: insert flow: %s", ofp_flow_mod)
            
        except TrustDB.EmptySelect as ex:
            LOG.info(ex)
        except lite.IntegrityError as ex:
            LOG.info(ex)
        except lite.Error as ex:
            raise TrustDB.TrustDBError(
                        "{} - {}".format( type(ex),ex ) )
        
    
    def insert_flow_entry(self, ofp_flow_mod):
        
        #print '***INSERT FLOW: ', ofp_flow_mod
        attributes = []
        
        # the following object are stored as string (sqlite TEXT) 
        match_str = str(ofp_flow_mod.match)
        instr_str = str(ofp_flow_mod.instructions)
        
        attributes.append( None )
        attributes.append( ofp_flow_mod.datapath.id )
        attributes.append( ofp_flow_mod.table_id )
        attributes.append( ofp_flow_mod.priority )
        attributes.append( ofp_flow_mod.idle_timeout )
        attributes.append( match_str )
        attributes.append( instr_str )
        attributes.append( self.session_id )
        record = tuple(attributes)
        records = [record]
        
        try:
            cursor = self.conn.cursor()
            cursor.executemany( 'INSERT INTO flowtable VALUES (?,?,?,?,?,?,?,?)', records)
            self.conn.commit()
            #LOG.info("FLOW_CACHE: insert flow: %s", ofp_flow_mod)
            
        except lite.IntegrityError as ex:
            LOG.info(ex)
        except lite.Error as ex:
            raise TrustDB.TrustDBError(
                        "{} - {}".format( type(ex),ex ) )
        
        
    def flow_table_query(self, dpid):
        ''' query flow table entry 
        @dpid    datapath id
        return   list of tuple that represent flow entries
        '''
        try:
            cur = self.conn.cursor()
        
            session = (self.session_id, )
            datapathid = (dpid, )
            query_param = [(self.session_id), (dpid)]
            cur.execute("SELECT tbl_id, priority, idle_timeout, match, instruction "
                    "FROM flowtable " 
                    "WHERE session_id=? and dpid=?", query_param)
            return cur.fetchall()
        
        except lite.Error as ex:
            raise TrustDB.TrustDBError(
                        "{} - {}".format(type(ex), ex) )
    
    