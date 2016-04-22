'''
Created on Feb 5, 2016

@todo: 
        -edit exception handling
        -edit real or ram db parameter

@author: root

'''

import os
import logging
import inspect
import datetime
from os.path import isfile, getsize
import sqlite3 as lite
from singleton import Singleton
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.lib.dpid import dpid_to_str
  


LOG = logging.getLogger(__name__)

MODULE_PATH = os.path.dirname( os.path.abspath(__file__) ) 



class FlowTableDb():
    
    __metaclass__ = Singleton
    
    DB_SCHEMA_SQL_PATH = MODULE_PATH + '/ofp_table.sql'
    DB_PATH = MODULE_PATH + "/flow_table_cache"
    #DB_PATH = ":memory:"                    
    
    class FlowTableDbError(Exception):
        pass
    
    
    def __init__(self, db_name = ":memory:"):
        self.db_name = FlowTableDb.DB_PATH
        self.conn = self.open_db()
        self.session_id = self.create_session()
        LOG.info("FLOW_CACHE: Database created succesfully: %s", self.db_name)
        
        
    def open_sql_script(self):
        f = open(FlowTableDb.DB_SCHEMA_SQL_PATH)
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
            raise FlowTableDb.FlowTableDbError(
                        "{} - {}".format(type(ex), ex) )
        except IOError as ex:
            raise FlowTableDb.FlowTableDbError(
                        "{} - {}".format(type(ex), ex) )
        except Exception as ex:
            raise FlowTableDb.FlowTableDbError(
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
            raise FlowTableDb.FlowTableDbError(
                        "{} - {}".format( type(ex),ex ) )
        
        
    def flow_table_query(self, dpid):
        ''' 
        query flow table entry
         
        @param dpid:   datapath id
        @return:       list of tuple that represent flow entries
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
            raise FlowTableDb.FlowTableDbError(
                        "{} - {}".format(type(ex), ex) )
    
    
            
            
            
            
            
            
            
