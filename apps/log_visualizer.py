'''
Created on Apr 22, 2016

@author: root
'''

import os
import logging
import optparse
import datetime
from os.path import isfile
import sqlite3 as lite
import matplotlib.pyplot as plt
import numpy as np
from truster_sdn_logger import TrustDB


LOG = logging.getLogger(__name__)       # module logger


class TrustDBReader():
    
    def __init__(self):
        self.trust_db = TrustDB(new_session=False)
        self.conn = self.trust_db.conn
        self.session_id = self.trust_db.session_id
        
    def get_log_date(self, src, dst, session_id):
        '''
        query trust_logs record for a link
        
        @param src:   link.src
        @param dst:   link.dst
        
        @rtype:    dict
        @return:   attribute -> value     
        '''
        
        try:
            cur = self.conn.cursor()
            
            query_param = [(session_id), (src), (dst)]
            cur.execute("SELECT time,drop_rate,fabr_rate,trust_value "
                        "FROM trust_logs JOIN links "
                        "ON trust_logs.link_id=links.id " 
                        "WHERE links.session_id=? AND links.src=? AND links.dst=?", query_param)
            query_result = cur.fetchall()
            time = []
            drop_rate = []
            fabr_rate = []
            trust_value = []
            for record in query_result:
                time.append(record[0])
                drop_rate.append(record[1])
                fabr_rate.append(record[2])
                trust_value.append(record[3])
            
            return {'time':time, 'drop_rate':drop_rate, 'fabr_rate':fabr_rate, 'trust_value':trust_value}
            
        except lite.Error as ex:
            LOG.info(ex)
        
        
        
class Graph():
    
    def __init__(self, ydata):
        self.ax = plt.plot()
        self.ax.grid()
        self.ydata = ydata
        self.ax.set_ylim(0.0, 1.0)
        self.ax.set_xlim(0, ydata[-1])
        
    def plot_line(self, xdata):
        self.line, = self.ax.plot(xdata, self.ydata, lw=2)


        
if __name__ == '__main__':
    
    parser = optparse.OptionParser()
    parser.add_option('-s', "--src", action='store', dest='src')
    parser.add_option('-d', '--dst', action='store', dest='dst')
    parser.add_option('--session', action='store', dest='session')
    parser.add_option('-i', '--interpolation', action='store_true', dest='interpolation')
    options, args = parser.parse_args()
     
    print "Starting visualizer..."
    
    db_reader = TrustDBReader()
    session = db_reader.session_id
    if options.session: session = options.session
    log_data = db_reader.get_log_date(options.src, options.dst, session) 
    ytime = log_data["time"]
        
    # graph
    plt.xlabel("time(sec)")
    plt.title("Trust rating")
    plt.grid(True)
    plt.xlim(0, ytime[-1])
    plt.xticks(np.arange(0, ytime[-1], 2))
    plt.yticks(np.arange(0.0, 1.0, 0.05))
        
    plt.plot(ytime, log_data['drop_rate'], label='drop rate')
    plt.plot(ytime, log_data['trust_value'], label='trust value')
    plt.legend(loc=7)
    
    if options.interpolation:
        x = np.linspace(0, ytime[-1], 1000)
        poly_deg = 10
        coef = np.polyfit(ytime, log_data['trust_value'], poly_deg)
        y_poly = np.polyval(coef, x)
        plt.plot(x, y_poly)
                
    plt.show()   
            
       
        
        
