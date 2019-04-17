import json
import os
import sys
import sqlite3
import re
import getpass
import socket
import random


# apt-get install python3-psycopg2
import psycopg2

def read_json(name, default=None):
   try:
      with open(name) as f:
         val = json.load (f)
   except(OSError, ValueError):
      if default is not None:
         return default
      print ("Can't parse", name)
      sys.exit(1)
   return val

def write_json(name, val):
   with open("TMP.json", "w") as f:
      f.write(json.dumps(val, sort_keys=True, indent=2))
      f.write("\n")
   os.rename("TMP.json", name)
      
def slurp_file(name):
   try:
      with open(name) as f:
         val = f.read()
   except(OSError):
      val = ""
   return val

cfg = None
def get_cfg():
   global cfg
   if cfg is None:
      cfg = read_json("cfg.json", {})
   return cfg

options = None
def get_options():
   global options
   if options is None:
      options = read_json("options.json", {})
   return options

db = None

def get_db():
   global db
   if db is not None:
      return db

   cfg = get_cfg()
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

def table_exist(table):
   db = get_db()
   return db['table_exists'](table)

def column_exist(table):
   db = get_db()
   return db['column_exists'](table)

def make_column(table, column, coltype):
   db = get_db()
   if not table_exists(table):
      stmt = "create table {} ({} {})".format(table, column, typename)
      print(stmt)
      db['cursor'].execute(stmt)
   elif not column_exists(table, column):
      stmt = "alter table {} add {} {}".format(table, column, typename)
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

def get_free_port():
   cfg = get_cfg()
   port_base = cfg['port_base']
   return random.randrange(port_base, port_base + 1000)

def make_url(scheme, host, port):
   url = "{}://{}".format(scheme, host)
   if port != 80 and port != 443:
      url += ":{}".format(port)
   url += "/"
   return url

def make_cert_filenames(dns_name):
   cert_dir = "/etc/apache2"
   return dict(crt="{}/{}.crt".format(cert_dir, dns_name),
               key="{}/{}.key".format(cert_dir, dns_name),
               chain="{}/{}.chain.pem".format(cert_dir, dns_name))

def try_cert(dns_name):
   cfg = get_cfg()
   names = make_cert_filenames(dns_name)
   if os.path.exists(names['crt']) and os.path.exists(names['key']):
      cfg['crt_file'] = names['crt']
      cfg['key_file'] = names['key']
      if os.path.exists(names['chain']):
         cfg['chain_file'] = names['chain']
      return True
   return False

def find_certs():
   cfg = get_cfg()

   cfg.pop("crt_file", None)
   cfg.pop("key_file", None)
   cfg.pop("chain_file", None)

   if try_cert(cfg['external_name']):
      return True

   wname = re.sub("^[^.]", "wildcard", cfg['external_name'])
   if try_cert(wname):
      return True

   return False

def add_ssl_engine():
   cfg = get_cfg()
   conf = ""
   conf += "  SSLEngine on\n";
   conf += "  SSLCertificateFile {}\n".format(cfg['crt_file'])
   conf += "  SSLCertificateKeyFile {}\n".format(cfg['key_file'])
   if 'chain_file' in cfg:
      conf += "  SSLCertificateChainFile {}\n".format(cfg['chain_file'])
   return conf

def add_valhtml():
   conf = ""
   conf += "    <IfModule valhtml_module>\n"
   conf += "      AddOutputFilterByType VALHTML text/html\n"
   conf += "      SetEnv no-gzip 1\n"
   conf += "    </IfModule>\n"
   return conf

def add_nocache():
   conf = ""
   conf += "    <FilesMatch '\.(html|css)'>\n"
   conf += "      Header set Cache-Control 'no-cache,no-store,must-revalidate'\n"
   conf += "      Header set Expires 0\n"
   conf += "    </FilesMatch>\n"
   return conf

def add_rewrites(ssl_flag):
   cfg = get_cfg()

   conf = ""
   conf += "  RewriteEngine on\n"

   # static files for lets encrypt
   conf += "  RewriteCond %{REQUEST_URI} /.well-known/.*\n"
   conf += "  RewriteRule ^(.*) /var/www/html/$1 [L]\n"
   conf += "\n"

   if cfg['ssl_port'] != 0 and not ssl_flag:
      # this is the http version of an ssl site ... redirect to https
      conf += "  RewriteRule ^/(.*) {}$1 [R]\n".format(cfg['main_url'])
      conf += "\n"
      return conf
   
   # send www.example.com to example.comf
   conf += "  RewriteCond %{{HTTP_HOST}} www.{}\n".format(cfg['external_name'])
   conf += "  RewriteRule ^/(.*) {}$1 [R]\n".format(cfg['main_url'])
   conf += "\n"
   
   # send all non-static files to index.php
   conf += "  RewriteCond {}%{{REQUEST_FILENAME}} !-f\n".format(cfg['www_dir'])
   conf += "  RewriteRule .* {}/index.php\n".format(cfg['src_dir'])

   return conf

def make_virtual_host(ssl_flag, port):
   cfg = get_cfg()
   conf = ""
   if port != 80 and port != 443:
      conf += "Listen {}\n".format(port)
   conf += "<VirtualHost *:{}>\n".format(port)
   conf += "  ServerName {}\n".format(cfg['external_name'])
   conf += "  ServerAlias www.{}\n".format(cfg['external_name'])
   if (ssl_flag):
      conf += add_ssl_engine()
   conf += "  php_flag display_errors on\n"
   conf += "  DocumentRoot {}\n".format(cfg['www_dir'])
   conf += "  SetEnv APP_ROOT {}\n".format(cfg['src_dir'])
   conf += "  <Directory {}>\n".format(cfg['www_dir'])
   conf +=      add_valhtml()
   conf +=      add_nocache()
   conf += "  </Directory>\n"
   conf += "  DirectoryIndex index.php\n"
   conf +=    add_rewrites(ssl_flag)
   conf += "</VirtualHost>\n"
   return conf

def make_apache_conf():
   cfg = get_cfg()
   conf = ""
   conf += "<Directory {}>\n".format(cfg['src_dir'])
   conf += "  Options Indexes FollowSymLinks Includes ExecCGI\n"
   conf += "  Require all granted\n"
   conf += "  Allow from all\n"
   conf += "</Directory>\n"

   conf += make_virtual_host(False, cfg['plain_port'])
   if cfg['ssl_port']:
      conf += make_virtual_host(True, cfg['ssl_port'])

   return conf

def setup_apache():
   cfg = get_cfg()

   conf = make_apache_conf()
   with open("TMP.conf", "w") as outf:
      outf.write(conf)

   av_name = "/etc/apache2/sites-available/{}.conf".format(cfg['siteid'])
   old = slurp_file(av_name)
   if old != conf:
      print("sudo sh -c 'cp TMP.conf {}; apache2ctl graceful'"
            .format(av_name))

   en_name = "/etc/apache2/sites-enabled/{}.conf".format(cfg['siteid'])
   if not os.path.exists(en_name):
      print("sudo a2ensite {}".format(cfg['siteid']))

def get_option(name, default=None):
   cfg = get_cfg()
   options = get_options()

   server_name = socket.gethostname()
   options_server = options.get(server_name, {})
   options_site = options_server.get(cfg['siteid'], {})

   if name in options_site:
      return options_site[name]
   elif name in options_server:
      return options_server[name]
   elif name in options:
      return options[name]
   else:
      return default

def setup_siteid(site_name_arg, conf_key_arg):
   cfg = get_cfg()

   if not 'site_name' in cfg:
      if site_name_arg is None:
         print("must specify site_name for install call to install-site")
         sys.exit(1)
      else:
         cfg['site_name'] = site_name_arg

   if conf_key_arg is None:
      cfg['conf_key'] = getpass.getuser()
   else:
      cfg['conf_key'] = conf_key_arg

   cfg['siteid'] = "{}-{}".format(cfg['site_name'], cfg['conf_key'])

def setup_dirs():
   cfg = get_cfg()
   cfg['src_dir'] = os.getcwd()
   cfg['static_dir'] = "{}/static".format(cfg['src_dir'])
   cfg['www_dir'] = "/var/www/{}".format(cfg['siteid'])
   if not os.path.exists(cfg['www_dir']):
      print("sudo ln -sf {} {}".format(cfg['static_dir'], cfg['www_dir']))

def setup_ports():
   cfg = get_cfg()

   nat_info = re.split("\s+", slurp_file ("/etc/apache2/NAT_INFO"))
   if len(nat_info) >= 2:
      cfg['nat_name'] = nat_info[0]
      cfg['port_base'] = int(nat_info[1])
   else:
      cfg['nat_name'] = "localhost"
      cfg['port_base'] = 8000

   val = get_option("external_name")
   if val == None:
      cfg['external_name'] = cfg['nat_name']
      if 'plain_port' not in cfg:
         cfg['plain_port'] = get_free_port()
   else:
      cfg['external_name'] = val
      cfg['plain_port'] = 80
      cfg['ssl_port'] = 443

def setup_urls():
   cfg = get_cfg()
   
   cfg['plain_url'] = make_url("http", cfg['external_name'], cfg['plain_port'])
   cfg['main_url'] = cfg['plain_url']

   if find_certs():
      if cfg.get("ssl_port", 0) == 0:
         cfg['ssl_port'] = get_free_port()
      cfg['ssl_url'] = make_url("https", cfg['external_name'], cfg['ssl_port'])
      cfg['main_url'] = cfg['ssl_url']
   else:
      cfg['ssl_port'] = 0
      cfg['ssl_url'] = ""

def install(site_name_arg=None, conf_key_arg=None):
   cfg = get_cfg()

   setup_siteid(site_name_arg, conf_key_arg)
   setup_dirs()
   setup_ports()
   setup_urls()

   cfg['db'] = get_option("db", "")

   setup_apache()

   print(cfg['plain_url'])
   if cfg.get('ssl_url', None) != None:
      print(cfg['ssl_url'])

   write_json("cfg.json", cfg)


