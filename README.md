# trusted-sdn
New added features new features:

	- base classes to allow extension of system:
		- MetricProvider: 
			Base class to provide metric value
		- TrustCollectorBase:
			represent app that monitora single trust proprieties

	- subclasses to implement trust metric according to the trust model:
		- TrustMetricProvider: 
			compute trust metric according the trust model and 
			using single trust prorieties measurements from the
			following collectors
		- DropFabrCollector: monitors the proprieties:
			-Switch/Link drop rate
			-Switch fabrication rate
		- MaliciousFlTblMod:
			monitors malicious flow table modification
			
Next features to be added:

	- apps for monitoring the link congestion
	- edit TrustMetricProvier integrating the new trust propriety in 
	  the metric

