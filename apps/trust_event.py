'''
Created on Dec 7, 2015

The module describes events concerning trust in the network:

 - Switch trust level change 


@version: 1.0
@author: root
'''


import logging

from ryu.controller import handler
from ryu.controller import event


LOG = logging.getLogger(__name__)



class EventSwitchTrustChange(event.EventBase):
    """ Define a change in the trust level of the switch """
    
    def __init__(self, dpid, sw_trust):
        
        super(EventSwitchTrustChange, self).__init__()
        self.dpid = dpid
        self.trust = sw_trust
        
class EventLinkTrustChange(event.EventBase):
    """ Define a change on the trust level of a link between switches"""
    
    def __init__(self, link, link_trust):
        
        super(EventLinkTrustChange, self).__init__()
        self.link = link
        self.link_trust = link_trust
        
    def __str__(self):
        return '%s<%s>' % (self.__class__.__name__, self.trust)
        

# register the app that raise the above events
#handler.register_service('trust_evaluator')
