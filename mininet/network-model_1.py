#!usr/bin/python

'''
Network model used to test trusted routing path:
    - 5 switches
    - 1 host
    - 2 servers
    
'''

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.clean import Cleanup as cleaner
from mininet.link import TCLink
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.node import OVSSwitch



class OVSBridgeSTP(OVSSwitch):
	""" Bridge with STP enabled """
	
	prio = 1000
	def start(self, *args, **kwargs):
		
		OVSSwitch.start(self, *args, **kwargs)
		OVSBridgeSTP.prio += 1
		self.cmd( 'ovs-vsctl set-fail-mode', self, 'standalone' )
		self.cmd( 'ovs-vsctl set-controller', self )
		self.cmd( 'ovs-vsctl set Bridge', self,
				'stp_enable = true',
				'other_config:stp-priority=%d' %OVSBridgeSTP.prio)
		
switches = {'ovs-stp': OVSBridgeSTP}


class NetModel_1_topo(Topo):
	"""
	Lab17 configuration
	- 3 switches
	- 3 hosts
	- tree-like topology
	"""
	def __init__(self):
		
		Topo.__init__(self)
		
		
		# switches
		s1 = self.addSwitch( name = 's1' )
		s2 = self.addSwitch( name = 's2' )
		s3 = self.addSwitch( name = 's3' )		
		s4 = self.addSwitch( name = 's4' )
		s5 = self.addSwitch( name = 's5' )
        
		# hosts

		h1 = self.addHost( 'h1' )
		h2 = self.addHost( 'h2' )
		attacker = self.addHost('attacker')
        
        # server
		srv1 = self.addHost( 'srv1' )
		srv2 = self.addHost( 'srv2' )
        
		linkopts_2_4 = dict(bw=10, delay='0.1ms', loss=30, max_queue_size=1000, use_htb=True)
		linkopts_3_4 = dict(bw=10, delay='0.1ms', loss=20, max_queue_size=1000, use_htb=True)
        
		self.addLink( s1, h1 )
		self.addLink( s1, h2 )
		self.addLink( s1, s2 )
		self.addLink( s1, s3 )
		self.addLink( s2, s4, **linkopts_2_4)
		self.addLink( s2, s5 )
		self.addLink( s3, s4 )
		self.addLink( s3, s5 )
		self.addLink( s4, srv1 )
		#self.addLink( s3, srv2 )
		#self.addLink( s4, srv1 )
		self.addLink( s5, srv2 )
		#self.addLink( s4, s5 )
		self.addLink( s2, attacker)
		
topos = { 'NetModel_1' : ( lambda: NetModel_1_topo() ) }
		
		
def run_net_model_1():
	topo = NetModel_1_topo()
	netopts = dict( topo = topo, controller = RemoteController, link = TCLink, autoSetMacs = True, autoStaticArp = True, cleanup = True)
	
	print "***Starting NetModel_1 configuration..."
	net = Mininet (**netopts)
	net.start()
	
	srv1 = net.getNodeByName("srv1")
	srv2 = net.getNodeByName("srv2")    
	
	print "***Starting UDP Server..."
	srv1.cmd('iperf --single_udp -s -u &')
	srv2.cmd('iperf --single_udp -s -u &')
    
	srv1_udp_pid = srv1.cmd('echo $!')
	srv2_udp_pid = srv2.cmd('echo $!')
	print "UDP Server started on srv1 with PID ", srv1_udp_pid
	print "UDP Server started on srv2 with PID ", srv2_udp_pid
    
	print "***Starting TCP Server..."
	srv1.cmd('iperf -s  &')
	srv2.cmd('iperf -s  &')
	srv1_tcp_pid = srv1.cmd('echo $!')
	srv2_tcp_pid = srv2.cmd('echo $!')
	print "TCP Server started on srv1 with PID ", srv1_tcp_pid
	print "TCP Server started on srv2 with PID ", srv2_tcp_pid
    
	print "Running CLI..."
	CLI(net)
	
	print "Killing mininet..."
	cleaner.cleanup()
	
if __name__ == '__main__':
	setLogLevel( 'info' )
	run_net_model_1()
		
		
