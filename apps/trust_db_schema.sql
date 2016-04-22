CREATE TABLE session(
	session_id 		INTEGER NOT	NULL,
	DATE			DATE,
	TIME 			TIMESTAMP,
	PRIMARY KEY(session_id)
);

CREATE TABLE links(
	id 				INTEGER NOT NULL,
	src				INTEGER NOT NULL,
	dst				INTEGER NOT NULL,
	session_id		INTEGER NOT NULL,
	PRIMARY KEY(id),
	FOREIGN KEY(session_id) REFERENCES session(session_id)
);
	
CREATE TABLE trust_logs(
	id					INTEGER NOT NULL,
	link_id				INTEGER NOT NULL,
	time 				TIMESTAMP,
	drop_trust_rate		REAL,
	fabr_trust_rate		REAL,
	drop_rate			REAL,
	fabr_rate			REAL,
	trust_value			REAL,
	PRIMARY KEY(id),
	FOREIGN KEY(link_id) REFERENCES links(id)	
);
