'''
Created on Apr 21, 2016

@author: root
'''
import os
import logging
import datetime
from os.path import isfile

from ryu.base import app_manager
from ryu.controller.handler import set_ev_cls
from ryu.topology import event
from ryu.lib import hub
from __builtin__ import True

import sqlite3 as lite
from ofp_table_mod.singleton import Singleton
  

LOG = logging.getLogger(__name__)       # module logger
MODULE_PATH = os.path.dirname( os.path.abspath(__file__) ) 


class TrusterLogger(app_manager.RyuApp):
    
    STARTUP_TIME = 4        # ytime before start logging
    REFRESH_TIME = 0.9        # ytime interval between successive logs
    
    def __init__(self, *args, **kwargs):
        
        super(TrusterLogger, self).__init__(*args, **kwargs)
        self.name = "truster_logger"
        self.trust_db = TrustDB(new_session=True)
        
    def start(self):
        app_manager.RyuApp.start(self) #TODO check the override method
        hub.spawn_after(self.STARTUP_TIME, self.log_trust_data)
        
    @set_ev_cls(event.EventLinkAdd)
    def insert_link_to_trust_db(self, ev):
        
        link = ev.link
        self.trust_db.insert_link(link)
    
    
    def log_trust_data(self):
        
        print 'Starting log trust data...'
        start_time = datetime.datetime.now()
        
        while True:
            trust_metric_prov_ref = app_manager.lookup_service_brick('trust_metric_provider')
            #trust_frw_ref = app_manager.lookup_service_brick('trusted_based_forwarder')
            self.link_features = trust_metric_prov_ref.link_features
            #link_metric = trust_metric_prov_ref.links_metric
            
            delta = datetime.datetime.now() - start_time
            timestamp = delta.seconds 
                        
            for link in self.link_features.keys():
                
                self.trust_db.insert_trust_log(link, timestamp, self.link_features[link])
            
            hub.sleep(self.REFRESH_TIME)
            
     

class TrustDB():
    
    __metaclass__ = Singleton
    
    DB_SCHEMA_SQL_PATH = MODULE_PATH + '/trust_db_schema.sql'
    DB_PATH = MODULE_PATH + "/trust_db.db"
    #DB_PATH = ":memory:"     
    
    class TrustDBError(Exception):
        pass
    
    class EmptySelect(Exception): 
        pass
    
    def __init__(self, db_name = ":memory:", new_session = False):
        self.db_name = TrustDB.DB_PATH
        self.conn = self.open_db()
        if new_session: 
            self.session_id = self.create_session()
        else:
            self.session_id = self.get_session_id()
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
        
    
    def insert_trust_log(self, link, ytime, trust_values):
        """
        link[IN]: link
        ytime[IN]: datetime.now
        trust_values[IN]: value_name -> value
        """
        
        attributes = []
        
        try:
            
            link_id = self.get_link_id(link.src.dpid, link.dst.dpid)       
            
            attributes.append( None )
            attributes.append( link_id )
            attributes.append( ytime )
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
        
    