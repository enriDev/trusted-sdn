'''
Created on Feb 9, 2016

@author: root
@version: 1.0
'''


import logging

from ryu.base import app_manager
from ryu.controller import handler
from ryu.controller import event
from ryu.controller.handler import MAIN_DISPATCHER


LOG = logging.getLogger(__name__)



### EVENTS ###

class EventTrustUpdate(event.EventBase):
    
    def __init__(self):       
        super(EventTrustUpdate, self).__init__()
        



### TRUST MONITOR BASE CLASS ###

class TrustCollectorBase(app_manager.RyuApp):
    """ Abstract class representing an app that monitor a specific 
        trust propriety of the network.
        It must raise an EventTrustUpdate at the maximum monitor rate.
    """
    
    # TODO manage start stop monitoring with synchronous request
    LOAD_TIME = 3   # time interval before start monitoring
    
    
    def __init_(self, app_name):
        super(TrustCollectorBase, self).__init__()
        self.name = app_name

    
    def publish_trust_update(self, trust_update):
        
        assert(trust_update is EventTrustUpdate)
        self.send_event_to_observers(trust_update, MAIN_DISPATCHER)


    def compute_trust(self):
        raise NotImplementedError('Subclasses must override compute_trust()')
        


