# trusted-sdn
Project moved to github.

Start controller command:
 $ ryu-manager --observe-links trust_based_forwarder service_manager

SDN apps features:
	- Topology discovery/storing
	- Routing
	- Static services registration with security class
	- Monitoring switches "trust":
		-pkts drop
		-pkts fabrication
	- Monitoring link "trust":
		-pkts drop
	- Trust Metric computation
	- Routing methods:
		-ECMP-like
		-based on Trust Metric
	

