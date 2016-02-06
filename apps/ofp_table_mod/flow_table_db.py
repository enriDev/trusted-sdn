'''
Created on Feb 5, 2016

@author: root

'''

import logging
from os.path import isfile, getsize
import sqlite3 as lite
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.lib.dpid import dpid_to_str



LOG = logging.getLogger(__name__)



class FlowTableDb():
    
    DB_SCHEMA_SQL_PATH = 'ofp_table_mod/ofp_table.sql'
    DB_PATH = "ofp_table_mod/flow_table_cache"                    
    
    
    class FlowTableDbError(Exception):
        pass
    
    
    def __init__(self, db_name = ":memory:"):
        self.db_name = FlowTableDb.DB_PATH
        self.conn = self.open_db()
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
        record = tuple(attributes)
        try:
            flow_entry_attr = [attributes]
            cursor = self.conn.cursor()
            cursor.executemany( 'INSERT INTO flowtable VALUES (?,?,?,?,?,?,?)', flow_entry_attr)
            self.conn.commit()
            LOG.info("FLOW_CACHE: insert flow: %s", ofp_flow_mod)
            
        except lite.IntegrityError as ex:
            LOG.info(ex)
        except lite.Error as ex:
            raise FlowTableDb.FlowTableDbError(
                        "%s - %s" % (type(ex),ex) )
        
        
    def insert_dp(self, dpid, status = MAIN_DISPATCHER):
        
        #print "***INSERT DP: ", dpid, status
        attributes = []
        attributes.append( dpid ) 
        attributes.append( status )
        record = tuple(attributes)
        records = [record]
        try:
            cursor = self.conn.cursor()
            cursor.executemany( 'INSERT INTO datapath VALUES (?,?)', records)
            self.conn.commit()
            LOG.info("FLOW_CACHE: insert dp: %s %s", dpid, status)
        except lite.IntegrityError as ex:
            LOG.info(ex)
        except lite.Error as ex:
            raise FlowTableDb.FlowTableDbError(
                        "%s - %s" % (type(ex), ex) )
    
    
            
            
            
            
            
            
            