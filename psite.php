<?php

ob_start ();

$app_root = @$_SERVER['APP_ROOT'];

$cfg = json_decode (file_get_contents ($app_root . "/cfg.json"), TRUE);
$options = json_decode (file_get_contents ($app_root . "/options.json"), TRUE);

function make_db_connection ($db, $dbparams, $create) {
	global $default_dbparams, $cfg, $options;

    if (@$options['db'] == "")
        fatal ("no db configured");

	if ($dbparams == NULL) {
		if (! isset ($default_dbparams)) {
            $default_dbparams = array ();

            $pw = posix_getpwuid (posix_geteuid ());
            if ($options['db'] == "postgres") {
                $default_dbparams['dbtype'] = "pgsql";
                if ($cfg['conf_key'] == "aws") {
                    $lsconf=json_decode(file_get_contents(
                        "/etc/lsconf-dbinfo"), TRUE);
                    $default_dbparams['host'] = $lsconf['host'];
                    $default_dbparams['user'] = $lsconf['user'];
                    $default_dbparams['password'] = $lsconf['password'];
                } else {
                    $default_dbparams['host'] = '';
                    $default_dbparams['user'] = $pw['name'];
                    $default_dbparams['password'] = '';
                }
            } else if ($options['db'] == "mysql") {
                $default_dbparams['dbtype'] = "mysql";
                $default_dbparams['host'] = '';
                $default_dbparams['user'] = $pw['name'];
                $default_dbparams['password'] = '';
            } else if ($options['db'] == "sqlite3") {
                $default_dbparams['dbtype'] = "sqlite3";
            }
		}
		$dbparams = $default_dbparams;
	}
		
	try {
        if ($dbparams['dbtype'] == "pgsql") {
            $attrs = array ();
            $attrs[] = sprintf ("dbname=%s", $db->dbname);
            $attrs[] = sprintf ("user=%s", $dbparams['user']);

            if ($dbparams['host'])
                $attrs[] = sprintf ("host=%s", $dbparams['host']);
            
            if ($dbparams['password'])
                $attrs[] = sprintf ("password=%s", $dbparams['password']);

            $dsn = sprintf ("pgsql:%s", implode (";", $attrs));

            $db->pdo = new PDO ($dsn);
        } else if ($dbparams['dbtype'] == "mysql") {
            $dsn = sprintf ("mysql:host=%s;charset:utf8",
                            $dbparams['host']);
            $db->pdo = new PDO ($dsn,
                                $dbparams['user'], $dbparams['password']);
            $db->pdo->exec ("set character set utf8");
            $db->pdo->exec ("set session time_zone = '+00:00'");
            $db->pdo->exec (sprintf ("use `%s`", $db->dbname));
        } else if ($dbparams['dbtype'] == "sqlite3") {
            $name = sprintf ("%s/%s.db", $cfg['aux_dir'], $cfg['siteid']);
            if (! file_exists ($name)) {
                printf ("%s does not exist", $name);
                exit();
            }
            $dsn = sprintf ("sqlite:%s/%s.db", $cfg['aux_dir'], $cfg['siteid']);
            $db->pdo = new PDO ($dsn);
        } else {
            fatal ("invalid db configured");
        }
	} catch (Exception $e) {
		printf ("db connect error %s\n", $e->getMessage ());
		return (NULL);
	}
}

$db_connections = array ();
$default_db = NULL;

function get_db ($dbname = "", $dbparams = NULL, $create = 0) {
	global $cfg, $db_connections, $default_db;

	if ($dbname == "") {
		if (! isset ($cfg['siteid'])) {
			printf ("get_db: no siteid"
				." to identify default database\n");
			exit (1);
		}
		$dbname = $cfg['siteid'];
	}

	if (($db = @$db_connections[$dbname]) != NULL)
		return ($db);

	$db = (object)NULL;
	$db->dbname = $dbname;
	make_db_connection ($db, $dbparams, $create);

	$db->in_transaction = 0;
	
	$db_connections[$dbname] = $db;

	if ($dbparams == NULL)
		$default_db = $db;

	return ($db);
}

function quote_for_db ($db = NULL, $str = "") {
	global $default_db;
	if ($db == NULL)
		$db = $default_db;
	return ($db->pdo->quote ($str));
}

function ckerr ($q, $stmt = "") {
    if ($q == NULL || $q->q == FALSE) {
        $dbmsg = "";
    } else {
        $err = @$q->q->errorInfo ();
        if ($err[0] == "00000")
            return;
        $dbmsg = $err[2];
    }

	$msg1 = sprintf ("DBERR %s %s\n%s\n",
                     strftime ("%Y-%m-%d %H:%M:%S\n"),
                     $dbmsg, $stmt);
	$msg2 = "";
	foreach (debug_backtrace () as $frame) {
		if (isset ($frame['file']) && isset ($frame['line'])) {
			$msg2 .= sprintf ("%s:%d\n",
					  $frame['file'], $frame['line']);
		}
	}

	$msg = "<pre>";
	$msg .= htmlentities (wordwrap ($msg1, 120));
	$msg .= htmlentities ($msg2);
	$msg .= "</pre>\n";

	echo ($msg);
    session_abort();

	exit ();
}

function query_db ($db, $stmt, $arr = NULL) {
	if (is_string ($db)) {
		echo ("wrong type argument query_db");
		exit ();
	}

	if ($db == NULL) {
		if (($db = get_db ()) == NULL) {
			printf ("can't make db connection\n");
			exit ();
		}
	}

	preg_match ("/^[ \t\r\n(]*([a-zA-Z]*)/", $stmt, $parts);
	$op = strtolower (@$parts[1]);

	$q = (object)NULL;

	global $csrf_safe, $csrf_skip;
	if (($op == "insert" || $op == "delete" || $op == "update")
	    && isset ($csrf_safe)
	    && $csrf_safe == 0
	    && @$csrf_skip == 0) {
		trigger_error ("internal error: database update attempted"
			       ." before calling csrf_safe()");
		exit (1);
	}

    if ($op != "commit") {
		if ($db->in_transaction == 0) {
			if (($q->q = $db->pdo->beginTransaction()) == FALSE)
                ckerr ($q, "begin transaction");
			$db->in_transaction = 1;
		}

        if ($arr === NULL) {
            if (($q->q = $db->pdo->prepare ($stmt)) == FALSE)
                ckerr ($q, "prepare ".$stmt);
            if (! $q->q->execute (NULL))
                ckerr ($q, $stmt);
        } else {
            if (! is_array ($arr))
                $arr = array ($arr);
            foreach ($arr as $key => $val) {
                if (is_string ($val) && $val == "")
                    $arr[$key] = NULL;
            }
            if (($q->q = $db->pdo->prepare ($stmt)) == FALSE)
                ckerr ($q, "prepare ".$stmt);
            if (! $q->q->execute ($arr))
                ckerr ($q, $stmt);
            $q->row_count = $q->q->rowCount ();
        }
    } else {
        if (($q->q = $db->pdo->commit()) == FALSE)
            ckerr ($q, "commit");
		$db->in_transaction = 0;
    }

	return ($q);
}

function query ($stmt, $arr = NULL) {
	return (query_db (NULL, $stmt, $arr));
}

function fetch ($q) {
	return ($q->q->fetch (PDO::FETCH_OBJ));
}

function do_commits () {
	global $db_connections;

	foreach ($db_connections as $db) {
		if ($db->in_transaction)
			query_db ($db, "commit");
	}
}

function psite_session_open () { return (TRUE); }
function psite_session_close () { return (TRUE); }

function psite_session_read ($session_id) {
	$q = query ("select session"
		    ." from sessions"
		    ." where session_id = ?",
		    $session_id);
	if (($r = fetch ($q)) == NULL)
		return ("");
	return ($r->session);
}

function psite_session_write ($session_id, $session) {
    global $csrf_skip;
    $csrf_skip = 1;

    if (trim ($session) == "") {
        query ("delete from sessions where session_id = ?", $session_id);
    } else {
        $q = query ("select 0"
        ." from sessions"
        ." where session_id = ?",
        $session_id);
        $ts = strftime ("%Y-%m-%d %H:%M:%S");
        if (fetch ($q) == NULL) {
            query ("insert into sessions (session_id, updated, session)"
            ." values (?,?,?)",
            array ($session_id, $ts, $session));
        } else {
            query ("update sessions set updated = ?, session = ?"
            ." where session_id = ?",
            array ($ts, $session, $session_id));
        }
    }
	$csrf_skip = 0;
	do_commits ();
    return (TRUE);
}

function psite_session_destroy ($session_id) {
	query ("delete from session where session_id = ?", $session_id);
	do_commits ();
    return (TRUE);
}

function psite_session_gc ($lifetime) {
	$ts = strftime ("%Y-%m-%d %H:%M:%S", time () - $lifetime);
	query ("delete from sessions where updated < ?", $ts);
	do_commits ();
    return (TRUE);
}

function psite_session () {
    if (get_db () == NULL)
        fatal ("no db for session handler");

	session_set_save_handler ("psite_session_open",
				  "psite_session_close",
				  "psite_session_read",
				  "psite_session_write",
				  "psite_session_destroy",
				  "psite_session_gc");
	session_start ();
}

function getsess ($name) {
    global $cfg;
	$key = sprintf ("svar%d_%s", $cfg['ssl_port'], $name);
	if (isset ($_SESSION[$key]))
		return ($_SESSION[$key]);
	return (NULL);
}

function putsess ($name, $val) {
    global $cfg;
	$key = sprintf ("svar%d_%s", $cfg['ssl_port'], $name);
	$_SESSION[$key] = $val;
}

function clrsess () {
    global $cfg;
	$prefix = sprintf ("svar%d_", $cfg['ssl_port']);
	$prefix_len = strlen ($prefix);
	$del_keys = array ();
	foreach ($_SESSION as $key => $val) {
		if (strncmp ($key, $prefix, $prefix_len) == 0)
			$del_keys[] = $key;
	}
	foreach ($del_keys as $key) {
		unset ($_SESSION[$key]);
	}
}

function get_seq ($db = NULL) {
	$q = query_db ($db,
		       "select lastval"
		       ." from seq"
		       ." limit 1");
	if (($r = fetch ($q)) == NULL) {
		$newval = 100;
		query_db ($db, "insert into seq (lastval) values (?)",
			  $newval);
	} else {
		$newval = 1 + intval ($r->lastval);
		query_db ($db, "update seq set lastval = ?",
			  $newval);
	}
	return ($newval);
}

function json_finish ($val) {
    do_commits ();
	if (ob_list_handlers ())
		ob_clean ();
    header ("Content-Type: application/json");
    echo (json_encode ($val));
    exit ();
}

$urandom_chars = "0123456789abcdefghijklmnopqrstuvwxyz";

function generate_urandom_string ($len, $charset = "") {
	global $urandom_chars;
	$ret = "";

	if ($charset == "")
		$charset = $urandom_chars;
	$charset_len = strlen ($charset);

	$f = fopen ("/dev/urandom", "r");

	for ($i = 0; $i < $len; $i++) {
		$c = ord (fread ($f, 1)) % $charset_len;
		$ret .= $charset[$c];
	}
	return ($ret);
}

$cache_defeater = "";
function get_cache_defeater () {
	global $cache_defeater;

	if ($cache_defeater)
		return ($cache_defeater);
	if (! @$_SERVER['devel_mode'] 
	    && ($f = @fopen ("commit", "r")) != NULL) {
		if (($val = fgets ($f)) != "") {
			$cache_defeater = substr ($val, 7, 8);
		}
		fclose ($f);
		return ($cache_defeater);
	}

	$cache_defeater = generate_urandom_string (8);
	return ($cache_defeater);
}

function flash ($str) {
	if (session_id () == "")
		session_start ();
	$_SESSION['flash'] .= $str;
}

function make_absolute ($rel) {
	if (preg_match (':^http:', $rel))
		return ($rel);

	if (preg_match (':^/:', $rel)) {
		$abs = sprintf ("http%s://%s%s",
				@$_SERVER['HTTPS'] == "on" ? "s" : "",
				$_SERVER['HTTP_HOST'], // may include port
				$rel);
		return ($abs);
	}

	$abs = @$_SERVER['SCRIPT_URI'];
	$abs = preg_replace (':[^/]*$:', "", $abs);
	if (! preg_match (':/$:', $abs))
		$abs .= "/";
	$abs .= $rel;
	return ($abs);
}

function redirect ($target) {
	$target = make_absolute ($target);

	do_commits ();
	if (ob_list_handlers ())
		ob_clean ();
	header ("Location: $target");
	exit ();
}

function fatal ($str = "error") {
	echo ("fatal: " . htmlentities ($str));
	exit();
}

function insert_javascript ($script) {
    $ret = "<script>\n";
    $ret .= h($script);
    $ret .= "</script>\n";
    return ($ret);
}

function h($val) {
	return (htmlentities ($val, ENT_QUOTES, 'UTF-8'));
}

function fix_target ($path) {
	$path = preg_replace ('/\&/', "&amp;", $path);
	return ($path);
}

function mklink ($text, $target) {
	if (trim ($text) == "")
		return ("");
	if (trim ($target) == "")
		return (h($text));
	return (sprintf ("<a href='%s'>%s</a>",
			 fix_target ($target), h($text)));
}

function mklink_nw ($text, $target) {
	if (trim ($text) == "")
		return ("");
	if (trim ($target) == "")
		return (h($text));
	return (sprintf ("<a target='_blank' href='%s'>%s</a>",
			 fix_target ($target), h($text)));
}

function mklink_span ($text, $target, $span_class = "") {
	if (trim ($text) == "")
		return ("");
	if (trim ($target) == "")
		return (h($text));

	$str = sprintf ("<a href='%s'>", fix_target ($target));
	$str .= "<span";
	if ($span_class != "")
		$str .= sprintf (" class='%s'", $span_class);
	$str .= ">";
	$str .= h($text);
	$str .= "</span>";
	$str .= "</a>";
	return ($str);
}

function make_confirm ($question, $button, $args) {
	global $request_uri;
	$ret = "";
	$ret .= sprintf ("<form action='%s' method='post'>\n",
			 $request_uri['path']);
	foreach ($args as $name => $val) {
		$ret .= sprintf ("<input type='hidden'"
				 ." name='%s' value='%s' />\n",
				 h($name), h ($val));
	}
	$ret .= h($question);
	$ret .= sprintf (" <input type='submit' value='%s' />\n", h($button));
	$ret .= "</form>\n";
	return ($ret);
}

function mktable ($hdr, $rows) {
    if (count ($rows) == 0)
        return ("");
        
	$ncols = count ($hdr);
	foreach ($rows as $row) {
		$c = count ($row);
		if ($c > $ncols)
			$ncols = $c;
	}

	if ($ncols == 0)
		return ("");

	$ret = "";
	$ret .= "<table class='boxed'>\n";
	$ret .= "<thead>\n";

	if ($hdr) {
		$ret .= "<tr class='boxed_header'>\n";

		$colidx = 0;
		if ($ncols == 1)
			$class = "lrth";
		else
			$class = "lth";
		foreach ($hdr as $heading) {
			if (strncmp ($heading, "<t", 2) == 0) {
				$ret .= $heading;
			} else {
				$ret .= sprintf ("<th class='%s col_num_%s'>",
						 $class, $colidx);
				$ret .= $heading;
				$ret .= "</th>\n";
			}
			
			$colidx++;
			$class = "mth";
			if ($colidx + 1 >= $ncols)
				$class = "rth";
		}
		$ret .= "</tr>\n";
	}
	$ret .= "</thead>\n";


	$ret .= "<tbody>\n";

	$rownum = 0;
	foreach ($rows as $row) {
		$this_cols = count ($row);

		if ($this_cols == 0)
			continue;

		if (is_object ($row)) {
			switch ($row->type) {
			case 1:
				$c = "following_row ";
				$c .= $rownum & 1 ? "odd" : "even";
				$ret .= sprintf ("<tr class='%s'>\n", $c);
				$ret .= sprintf ("<td colspan='%d'>",
						 $ncols);
				$ret .= $row->val;
				$ret .= "</td></tr>\n";
				break;
			}
			continue;
		}


		$rownum++;
		$ret .= sprintf ("<tr class='%s'>\n",
				 $rownum & 1 ? "odd" : "even");

		for ($colidx = 0; $colidx < $ncols; $colidx++) {
			if ($ncols == 1) {
				$class = "lrtd";
			} else if ($colidx == 0) {
				$class = "ltd";
			} else if ($colidx < $ncols - 1) {
				$class = "mtd";
			} else {
				$class = "rtd";
			}

			$col = @$row[$colidx];

			if (is_array ($col)) {
				$c = $col[0];
				$v = $col[1];
				$ret .= sprintf ("<td class='%s %s'>%s</td>\n",
						 $class, $c, $v);
			} else if (strncmp ($col, "<t", 2) == 0) {
				$ret .= $col;
			} else {
				$c = "";
				$v = $col;
				$ret .= sprintf ("<td class='%s %s'>%s</td>\n",
						 $class, $c, $v);
			}
		}

		$ret .= "</tr>\n";
	}

	if (count ($rows) == 0)
		$ret .= "<tr><td>(empty)</td></tr>\n";

	$ret .= "</tbody>\n";
	$ret .= "</table>\n";

	return ($ret);
}

