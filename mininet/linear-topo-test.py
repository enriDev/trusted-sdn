#!usr/bin/python

'''
Thesis:
    - simple topology for testing statistics retrival
'''

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.node import OVSSwitch



class Linear_topo_test(Topo):
    """
    Linear configuration
    - 3 switches
    - 2 hosts
    - linear topology
    """
    def __init__(self):
        
        Topo.__init__(self)
        
        
        # switches
        s1 = self.addSwitch( name = 's1' )
        s2 = self.addSwitch( name = 's2' )
        s3 = self.addSwitch( name = 's3' )                    
        
        # hosts
        h1 = self.addHost( 'h1' )        
        h2 = self.addHost( 'h2' )

        
        # links
        linkopts = dict(bw=10, delay='0.5ms', loss=10, max_queue_size=1000, use_htb=True)
        
        self.addLink( s1, h1 )
        self.addLink( s1, s2 )
        self.addLink( s2, s3, **linkopts )
        self.addLink( s3, h2 )
        
        
topos = { 'linear-test' : ( lambda: Linear_topo_test() ) }
        
        
def run_linear_topo_test()    :
    
    topo = Linear_topo_test()
    print "*****Starting lab 17 configuration..."
    net = Mininet (topo = topo, controller = RemoteController)
    net.start()
    print "Running CLI"
    CLI(net)
    
if __name__ == '__main__':
    setLogLevel( 'info' )
    run_linear_topo_test()()
        
        
