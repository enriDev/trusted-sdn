CREATE TABLE session(
	session_id 		INTEGER NOT	NULL,
	DATE			DATE,
	TIME 			TIMESTAMP,
	PRIMARY KEY(session_id)
);
CREATE TABLE flowtable(
    id 				INTEGER NOT NULL,
	dpid 			INTEGER NOT NULL,
	tbl_id 			INTEGER NOT NULL,
	priority 		INTEGER NOT NULL,
	idle_timeout	INTEGER NOT NULL,
	match 			TEXT NOT NULL,
	instruction		TEXT NOT NULL,
	session_id		INTEGER NOT NULL,
	PRIMARY KEY(id),
	FOREIGN KEY(session_id) REFERENCES session(session_id)
);
