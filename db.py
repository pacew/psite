import re

# apt-get install python3-psycopg2
import psycopg2
import sqlite3


import psite

db = None

def get_db():
   global db
   if db is not None:
      return db

   cfg = psite.get_cfg()
   db = dict(db=cfg["db"])

   if cfg["db"] == "sqlite3":
      filename = "{0}.db".format(cfg['site_name'])
      db['conn'] = sqlite3.connect(filename)
      db['cursor'] = db['conn'].cursor()
      db['table_exists'] = sqlite3_table_exists
      db['column_exists'] = sqlite3_column_exists
      db['commit'] = sqlite3_commit
      return db
   elif cfg["db"] == "postgres":
      dsn = "postgresql:///{0}".format(cfg['siteid'])
      try:
         db['conn'] = psycopg2.connect (dsn)
      except(psycopg2.OperationalError):
         print("can't connect to database, maybe do:")
         print("createdb -O www-data {}".format(cfg['siteid']))
         sys.exit(1)
      db['cursor'] = db['conn'].cursor()
      db['table_exists'] = postgres_table_exists
      db['column_exists'] = postgres_column_exists
      db['commit'] = postgres_commit
      return db
   else:
      print("get_db failed")
      sys.exit(1)

def sqlite3_table_exists(table):
   db = get_db()
   cur = db['cursor']
   cur.execute("select 1 from sqlite_master"+
               " where type = 'table'"+
               "   and name = ?",
               (table,))
   return cur.fetchone() != None

def sqlite3_column_exists(table, column):
   db = get_db()
   cur = db['cursor']
   stmt = "pragma table_info({0})".format(table)
   cur.execute(stmt)
   for row in cur:
      if row[1] == column:
         return True
   return False

def sqlite3_commit():
   pass

def postgres_table_exists(table):
   db = get_db ();
   cur = db['cursor'];

   cur.execute("select 0"
               " from information_schema.tables"
               " where table_schema = 'public'"
               "   and table_name = %s",
               (table,))
   return fetch() != None

def postgres_column_exists(table, column):
   db = get_db ();
   cur = db['cursor'];

   cur.execute("select 0"
               " from information_schema.columns"
               " where table_schema = 'public'"
               "   and table_name = %s"
               "   and column_name = %s",
               (table, column))
   return fetch() != None

def postgres_commit():
   query("commit")

def query(stmt, args=None):
   db = get_db()
   if db["db"] == "postgres":
      stmt = re.sub("[?]", "%s", stmt)
   return (db['cursor'].execute(stmt, args))

def fetch():
   db = get_db()
   return db['cursor'].fetchone()

def commit():
   db = get_db()
   return db['commit']()

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
   if result == None:
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
            words = re.split("\s+", line)
            if len(words) == 0:
                continue
            if words[0] == "table":
                if len(words) != 2:
                    raise ValueError("{}:{}: wrong number of args"
                                     .format(filename,linenum))
                table = words[1]
            elif words[0] == "col":
                if len(words) != 3:
                    raise ValueError("{}:{}: wrong number of args"
                                     .format(filename,linenum))
                column = words[1]
                typename = words[2]
                make_column (table, column, typename)
                commit()
