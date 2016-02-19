'''
Created on Feb 18, 2016

Contains all trust related events collected by subclasses
of trust_collector_base

@author: root
'''

from ryu.controller import event
from ryu.lib.dpid import DPID_PATTERN



class EventTrustUpdate(event.EventBase):
    
    def __init__(self):       
        super(EventTrustUpdate, self).__init__()
        


class EventMaliciousFlowTblMod(EventTrustUpdate):
    
    def __init__(self, dpid):
        super(EventMaliciousFlowTblMod, self).__init__()
        self.dpid = dpid
        
        
class EventLinkDropRateUpdate(EventTrustUpdate):
    
    def __init__(self, link, drop_rate):    
        super(EventLinkDropRateUpdate, self).__init__()
        self.link = link
        self.drop_rate = drop_rate


class EventFabrRateUpdate(EventTrustUpdate):
    
    def __init__(self, dpid, fabr_rate):
        super(EventFabrRateUpdate, self).__init__()
        self.dpid = dpid
        self.fabr_rate = fabr_rate
        
        
        
        
        