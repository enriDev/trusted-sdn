'''
Created on Feb 18, 2016

Contains all trust related events collected by subclasses
of trust_collector_base

@author: root
'''

from ryu.controller import event



class EventTrustUpdate(event.EventBase):
    
    def __init__(self):       
        super(EventTrustUpdate, self).__init__()
        


class EventMaliciousFlowTblMod(EventTrustUpdate):
    
    def __init__(self, dpid):
        super(EventMaliciousFlowTblMod, self).__init__()
        self.dpid = dpid
        

class EventDropFabrRate(EventTrustUpdate):
    
    def __init__(self, link, link_trust):
        
        super(EventDropFabrRate, self).__init__()
        self.link = link
        self.link_trust = link_trust
        
    def __str__(self):
        return '%s<%s>' % (self.__class__.__name__, self.trust)
