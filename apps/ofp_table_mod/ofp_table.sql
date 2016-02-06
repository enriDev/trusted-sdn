CREATE TABLE datapath(
	dpid 			INTEGER NOT	NULL,
	status 			CHAR (20),
	PRIMARY KEY(dpid)
);
CREATE TABLE flowtable(
	id 				INTEGER,
	dpid 			INTEGER NOT NULL,
	priority 		INTEGER NOT NULL,
	tbl_id 			INTEGER NOT NULL,
	idle_timeout	INTEGER NOT NULL,
	match 			TEXT NOT NULL,
	instruction		TEXT NOT NULL,
	PRIMARY KEY(dpid, match),
	FOREIGN KEY(dpid) REFERENCES datapath(dpid)
);
