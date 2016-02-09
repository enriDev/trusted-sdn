'''
Created on Feb 9, 2016

@author: root
@version: 1.0
'''


from ryu.topology import event
from ryu.topology.api import get_switch
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.lib import hub


from trust_proprieties_monitor import TrustMonitorBase, EventTrustUpdate
from apps.ofp_table_mod.of_tbl_mod_provider import OFTblModProvider


LOG = logging.getLogger(__name__)



class MaliciousFlTblMod(TrustMonitorBase):
    
    FLOW_TBL_REQUEST_INTERVAL = 10
    
    def __init__(self):
        
        super(MaliciousFlTblMod, self).__init__('malicious_fl_tbl_mod')
        self.switch_list = {}   # dpid -> datapath
        self.flow_tbl_cache = OFTblModProvider().flow_table_cache
        self.threads.append( hub.spawn_after(self.LOAD_TIME, self.flow_tbl_monitoring_loop) )
        
    
    @set_ev_cls(event.EventSwitchEnter, MAIN_DISPATCHER)
    def switchEnterEvent_handler(self, ev):
        
        datapath = ev.switch.dp
        self.switch_list[datapath.id] = datapath
        
    
    def flow_tbl_monitoring_loop(self):
        
        LOG.info("TRUST_EVAL: Starting flow table monitoring...")
        while True:
            for datapath in self.switch_list.values():
                self.flow_tbl_status_request(datapath)
            hub.sleep(self.FLOW_TBL_REQUEST_INTERVAL)



    def flow_tbl_status_request(self, datapath):
        
        LOG.info('Flow table status request: dp %016x', datapath.id)
        
        ofproto = datapath.ofproto
        of_parser = datapath.ofproto_parser
        
        # request all flow table entries
        match = of_parser.OFPMatch()
        request = of_parser.OFPFlowStatsRequest(datapath = datapath, match = match) 
        datapath.send_msg(request)
        
        
        
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def fl_tbl_status_reply_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        body = msg.body
        
        flow_entries = []
        for stat in body:
            flow_entries.append(
                                'dp=%s -- '
                                'table_id=%s -- '
                                'priority=%s -- '
                                'idle_timeout=%s -- '
                                'match=%s -- '
                                'instruction=%s -- ' %
                                (datapath.id,
                                 stat.table_id,
                                 stat.priority,
                                 stat.idle_timeout,
                                 stat.match,
                                 stat.instructions,
                                 ))
            
        LOG.info('\nFlow table status: \n%s', flow_entries)
