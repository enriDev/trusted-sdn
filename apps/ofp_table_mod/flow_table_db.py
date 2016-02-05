'''
Created on Feb 5, 2016

@author: root

'''

import logging
import sqlite3 as lite
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER


LOG = logging.getLogger(__name__)


class FlowTableDb():
    
    DB_SCHEMA_SQL = 'ofp_table.sql'
    
    
    class FlowTableDbError(Exception):
        message = "%(msg)s"
    
    
    def __init__(self, db_name = ':memory:'):
        self.create_db()
        self.db_name = db_name
        self.conn = self.create_db()
        
        
    def open_sql_script(self):
        f = open(FlowTableDb.DB_SCHEMA_SQL)
        sql = f.read()
        return sql
            
            
    def create_db(self):
        try:
            sql = self.open_sql_script()
            conn = lite.connect(self.dp_name)
            conn.execute(sql)
            return conn
        except lite.Error as ex:
            raise FlowTableDb.FlowTableDbError(
                        msg = "%s" % ex)
        except Exception as ex:
            raise FlowTableDb.FlowTableDbError(
                        msg = '%s - %s' % type(ex), ex)
            
    def insert_flow_entry(self, ofp_flow_mod):
        
        record = () 
        # the following object are stored as string (sqlite TEXT) 
        match_str = str(ofp_flow_mod.match)
        instr_str = str(ofp_flow_mod.instructions)
        
        record.add( ofp_flow_mod.datapth.id )
        record.add( ofp_flow_mod.table_id )
        record.add( ofp_flow_mod.priority )
        record.add( ofp_flow_mod.idle_timeout )
        record.add( match_str )
        record.add( instr_str )
             
        try:
            flow_entry_attr = [record]
            cursor = self.conn.cursor()
            cursor.executemany( 'INSERT INTO flowtable VALUES (?,?,?,?,?,?)', flow_entry_attr)
            self.conn.commit()
        except lite.Error as ex:
            raise FlowTableDb.FlowTableDbError(
                        msg = "%s - %s" % type(ex), ex)
        
        
    def insert_dp(self, dp):
        
        record = ()
        record.add( dp ) 
        record.add( MAIN_DISPATCHER )
        records = [record]
        try:
            cursor = self.conn.cursor()
            cursor.executemany( 'INSERT INTO datapath VALUES (?,?)', records)
            self.conn.commit()
        except lite.Error as ex:
            raise FlowTableDb.FlowTableDbError(
                        msg = "%s - %s" % type(ex), ex)
    
    
            
            
            
            
            
            
            