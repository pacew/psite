import os
import sys
import re
import grp
import time


import psite


def make_writable_for_server(filename):
    stat = os.stat(filename)
    try:
        group = grp.getgrgid(stat.st_gid).gr_name
    except(KeyError):
        group = None

    if group != "www-data":
        print("sudo chgrp www-data {}".format(filename))

    if stat.st_mode & int("020", 8) == 0:
        print("sudo chmod g+w {}".format(filename))


db = None


def get_db():
    global db
    if db is not None:
        return db

    cfg = psite.get_cfg()
    db = dict(db=cfg["db"])

    if cfg["db"] == "sqlite3":
        import sqlite3
        filename = "{}/{}.db".format(cfg['aux_dir'], cfg['dbname'])
        db['conn'] = sqlite3.connect(filename)
        make_writable_for_server(filename)
        db['cursor'] = db['conn'].cursor()
        db['table_exists'] = sqlite3_table_exists
        db['column_exists'] = sqlite3_column_exists
        db['commit'] = sqlite3_commit
        return db
    elif cfg["db"] == "postgres":
        # apt-get install python3-psycopg2
        import psycopg2
        dsn = "postgresql://apache@/{}".format(cfg['dbname'])
        try:
            db['conn'] = psycopg2.connect(dsn)
        except(psycopg2.OperationalError):
            print("can't connect to database, maybe do:")
            print("createdb -O apache {}".format(cfg['dbname']))
            raise
            sys.exit(1)
        db['cursor'] = db['conn'].cursor()
        db['table_exists'] = postgres_table_exists
        db['column_exists'] = postgres_column_exists
        db['commit'] = postgres_commit
        return db
    elif cfg["db"] == "mysql":
        # apt-get install python3-mysqldb
        import MySQLdb

        try:
            params = {}
            params['db'] = cfg['dbname']
            params['db'] = 'apply-pace'

            if psite.get_option("db_host") is not None:
                params['host'] = psite.get_option("db_host")
                params['user'] = psite.get_option("db_user")
                pw = psite.slurp_file(".psite_db_passwd").strip()
                params['password'] = pw
            else:
                # get unix_socket name: mysqladmin variables | grep sock
                params['unix_socket'] = '/var/run/mysqld/mysqld.sock'

            db['conn'] = MySQLdb.connect(**params)
        except(MySQLdb.OperationalError):
            print("")
            print("*******")
            print("can't connect to database, maybe do:")
            print("mysql -Nrse 'create database `{}`'".format(cfg['dbname']))
            print("*******")
            print("")
            print("")
            raise
            sys.exit(1)

        db['cursor'] = db['conn'].cursor()
        db['table_exists'] = mysql_table_exists
        db['column_exists'] = mysql_column_exists
        db['commit'] = mysql_commit
        return db
    else:
        print("get_db failed")
        sys.exit(1)


def sqlite3_table_exists(table):
    db = get_db()
    cur = db['cursor']
    cur.execute("select 1 from sqlite_master"
                " where type = 'table'"
                "   and name = ?",
                (table,))
    return cur.fetchone() is not None


def sqlite3_column_exists(table, column):
    db = get_db()
    cur = db['cursor']
    stmt = "pragma table_info({})".format(table)
    cur.execute(stmt)
    for row in cur:
        if row[1] == column:
            return True
    return False


def sqlite3_commit():
    db['conn'].commit()


def postgres_table_exists(table):
    db = get_db()
    cur = db['cursor']

    cur.execute("select 0"
                " from information_schema.tables"
                " where table_schema = 'public'"
                "   and table_name = %s",
                (table,))
    return fetch() is not None


def postgres_column_exists(table, column):
    db = get_db()
    cur = db['cursor']

    cur.execute("select 0"
                " from information_schema.columns"
                " where table_schema = 'public'"
                "   and table_name = %s"
                "   and column_name = %s",
                (table, column))
    return fetch() is not None


def postgres_commit():
    query("commit")


def mysql_table_exists(table):
    cfg = psite.get_cfg()
    db = get_db()
    cur = db['cursor']

    cur.execute("select 0"
                " from information_schema.tables"
                " where table_schema = %s"
                "   and table_name = %s",
                (cfg['dbname'], table))
    return fetch() is not None


def mysql_column_exists(table, column):
    cfg = psite.get_cfg()
    db = get_db()
    cur = db['cursor']

    cur.execute("select 0"
                " from information_schema.columns"
                " where table_schema = %s"
                "   and table_name = %s"
                "   and column_name = %s",
                (cfg['dbname'], table, column))
    return fetch() is not None


def mysql_commit():
    query("commit")


def query(stmt, args=()):
    db = get_db()
    if db["db"] == "postgres" or db["db"] == "mysql":
        stmt = re.sub("[?]", "%s", stmt)
    return (db['cursor'].execute(stmt, args))


def fetch():
    db = get_db()
    return db['cursor'].fetchone()


def commit():
    db = get_db()
    return db['commit']()


def getvar(name):
    query("select val from vars where var = ?", (name,))
    r = fetch()
    if r is None:
        return ""
    return r[0]


def setvar(name, val):
    query("select val from vars where name = ?", (name,))
    if fetch() is None:
        query("insert into vars (name, val) values (?, ?)", (name, val))
    else:
        query("update vars set val = ? where name = ?", (val, name))


def table_exists(table):
    db = get_db()
    return db['table_exists'](table)


def column_exists(table, column):
    db = get_db()
    return db['column_exists'](table, column)


def make_column(table, column, coltype):
    db = get_db()
    if not table_exists(table):
        stmt = "create table {} ({} {})".format(table, column, coltype)
        print(stmt)
        db['cursor'].execute(stmt)
    elif not column_exists(table, column):
        stmt = "alter table {} add {} {}".format(table, column, coltype)
        print(stmt)
        db['cursor'].execute(stmt)


def get_seq():
    query("select lastval from seq")
    result = fetch()
    if result is None:
        curval = 100
        query("insert into seq (lastval) values (?)", (curval,))
        commit()
    else:
        curval = result[0] + 1
        query("update seq set lastval = ?", (curval,))
        commit()
        return curval


def mkschema():
    filename = "schema"
    with open(filename) as f:
        table = None
        linenum = 0
        for line in f:
            linenum = linenum + 1
            line = re.sub(re.compile("#.*"), "", line).strip()
            words = re.split("\\s+", line)
            if len(words) == 0:
                continue
            if words[0] == "table":
                if len(words) != 2:
                    raise ValueError("{}:{}: wrong number of args"
                                     .format(filename, linenum))
                table = words[1]
            elif words[0] == "col":
                if len(words) != 3:
                    raise ValueError("{}:{}: wrong number of args"
                                     .format(filename, linenum))
                column = words[1]
                typename = words[2]
                make_column(table, column, typename)
                commit()


def daily_backup():
    cfg = psite.get_cfg()

    backups_dir = "{}/backups".format(cfg['aux_dir'])
    if not os.path.exists(backups_dir):
        os.mkdir(backups_dir, 0o775)

    ts = time.strftime("%Y%m%dT%H%M%S")
    basename = "{}-{}.sql".format(cfg['siteid'], ts)
    gzname = "{}.gz".format(basename)

    if cfg["db"] == "mysql":
        cmd = ("mysqldump --single-transaction --result-file {}/{} {}"
               .format(backups_dir, basename, cfg['dbname']))
        if os.system(cmd) != 0:
            print("db dump error")
            sys.exit(1)

        cmd = "gzip --force {}/{}".format(backups_dir, basename)
        if os.system(cmd) != 0:
            print("db dump error during compression")
            sys.exit(1)
    elif cfg["db"] == "postgres":
        cmd = ("pg_dump"
               " --dbname={}"
               " --file={}/{}"
               " --no-owner"
               " --no-acl"
               " --compress=6"
               " --lock-wait-timeout=60000").format(
                   cfg['dbname'],
                   backups_dir,
                   gzname)
        if os.system(cmd) != 0:
            print("db dump error")
            sys.exit(1)

    latest = "{}/latest.gz".format(backups_dir)
    if os.path.exists(latest):
        os.remove(latest)

    os.symlink(gzname, latest)


def restore():
    cfg = psite.get_cfg()

    print("restore")
    if len(sys.argv) < 3:
        print("usage: psite restore filename")
        sys.exit(1)
    filename = sys.argv[2]

    cmd = "mysql -Nrse 'drop database `{}`'".format(cfg['dbname'])
    print(cmd)

    cmd = "mysql -Nrse 'create database `{}`'".format(cfg['dbname'])
    print(cmd)

    cmd = "gunzip < {} | mysql {}".format(filename, cfg['dbname'])
    print(cmd)
