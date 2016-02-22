'''
Created on Feb 9, 2016

@author: root
@version: 1.0
'''


from __future__ import division
from operator import attrgetter
import logging

from ryu.base import app_manager
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3 as ofproto13
from ryu.ofproto import ofproto_v1_3_parser as parser13
from ryu.controller import event as app_event
from ryu.controller import ofp_event 
from ryu.controller import handler
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, HANDSHAKE_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.topology.api import get_switch, get_link
from ryu.topology import event, switches 
from ryu.topology.switches import LLDPCounter
from ryu.ofproto import ether
from ryu.lib.packet import packet, ethernet, vlan


import logging
import datetime
from os.path import isfile, getsize
import sqlite3 as lite
from singleton_pattern import Singleton
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.lib.dpid import dpid_to_str

import trust_event
from ryu.lib.mac import BROADCAST_STR
from ryu.lib.packet.lldp import LLDP_MAC_NEAREST_BRIDGE
from ryu.lib.packet.ether_types import ETH_TYPE_LLDP


##### GLOBAL VARIABLE ####
LOG = logging.getLogger(__name__)   # logger for module




### API ###

def get_links_metric(app, provider_name):
    req = EventMetricRequest(provider_name)
    rep = app.send_request(req)
    return rep.links_metric



### SYNC EVENTS ###

class EventMetricReply(app_event.EventReplyBase):
    
    def __init__(self, dst_app, links_metric):
        super(EventMetricReply, self).__init__(dst_app)
        self.links_metric = links_metric    # dict: link -> metric


class EventMetricRequest(app_event.EventRequestBase):
    
    def __init__(self, dst_app):
        super(EventMetricRequest, self).__init__()
        self.dst = dst_app



### BASE PROVIDER CLASS ###

class MetricProviderBase(app_manager.RyuApp):
    """Abstract class representing a metric provider. """
    
    
    def __init__(self, name, default_link_weight, *args, **kwargs):
        
        super(MetricProviderBase, self).__init__(*args, **kwargs)
        self.name = name
        self.default_link_weight = default_link_weight
        self.links_metric = {}      # link -> metric
        
        
    @set_ev_cls(event.EventLinkAdd)
    def new_link_event_handler(self, ev):
        
        #LOG.info('METRIC_PROVIDER: New link detected %s -> %s', ev.link.src.dpid, ev.link.dst.dpid)
        link = ev.link
        self.links_metric[link] = self.default_link_weight
        

    @set_ev_cls(EventMetricRequest)
    def metric_request_handler(self, request):
        
        #print 'Received metric request from ', request.src
        self.compute_metric()
        reply = EventMetricReply(request.src, self.links_metric)
        self.reply_to_request(request, reply)
        #print 'sent metric reply to:', request.src
    
    #abstractmethod
    def compute_metric(self):
        raise NotImplementedError('Subclasses must override compute_metric()')


        


class MetricDb():
    __metaclass__ = Singleton
    
    #TODO fix the relative paths
    DB_SCHEMA_SQL_PATH = 'ofp_table_mod/ofp_table.sql'
    DB_PATH = "ofp_table_mod/flow_table_cache"
    #DB_PATH = ":memory:"                    
    
    
    class MetricDbError(Exception):
        pass
    
    
    def __init__(self, db_name = ":memory:"):
        self.db_name = MetricDb.DB_PATH
        self.conn = self.open_db()
        self.create_session()
        LOG.info("FLOW_CACHE: Database created succesfully: %s", self.db_name)
        
        
    def open_sql_script(self):
        f = open(MetricDb.DB_SCHEMA_SQL_PATH)
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
            raise MetricDb.MetricDbError(
                        "{} - {}".format(type(ex), ex) )
        except IOError as ex:
            raise MetricDb.MetricDbError(
                        "{} - {}".format(type(ex), ex) )
        except Exception as ex:
            raise MetricDb.MetricDbError(
                        "{} - {}".format(type(ex), ex) )
        
        
    def create_session(self):
        
        today = datetime.date.today()
        now = datetime.datetime.now()
        record = (None, today, now)
        cur = self.conn.cursor()
        cur.execute("INSERT INTO session VALUES (?,?,?)", record)
        self.conn.commit()    
        
        
    def get_session_id(self):
        
        cur = self.conn.cursor()
        cur.execute("SELECT MAX(session_id) FROM session ")
        row = cur.fetchone()
        return int( row[0] )
            
            
    def insert_flow_entry(self, ofp_flow_mod):
        
        #print '***INSERT FLOW: ', ofp_flow_mod
        attributes = []
        session_id = self.get_session_id()
        
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
        attributes.append( session_id )
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
            raise MetricDb.MetricDbError(
                        "%s - %s" % (type(ex),ex) )
        
           

        
        