import os
import sys
import re
import getpass
import random

import psite

def get_free_port():
   cfg = psite.get_cfg()
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
   cfg = psite.get_cfg()
   names = make_cert_filenames(dns_name)
   if os.path.exists(names['crt']) and os.path.exists(names['key']):
      cfg['crt_file'] = names['crt']
      cfg['key_file'] = names['key']
      if os.path.exists(names['chain']):
         cfg['chain_file'] = names['chain']
      return True
   return False

def find_certs():
   cfg = psite.get_cfg()

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
   cfg = psite.get_cfg()
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
   cfg = psite.get_cfg()

   conf = ""
   conf += "  RewriteEngine on\n"

   # static files for lets encrypt
   conf += "  RewriteCond %{REQUEST_URI} /.well-known/.*\n"
   conf += "  RewriteRule ^(.*) /var/www/html/$1 [L]\n"
   conf += "\n"

   if cfg['ssl_enabled'] and not ssl_flag:
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
   cfg = psite.get_cfg()
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
   cfg = psite.get_cfg()
   conf = ""
   conf += "<Directory {}>\n".format(cfg['src_dir'])
   conf += "  Options Indexes FollowSymLinks Includes ExecCGI\n"
   conf += "  Require all granted\n"
   conf += "  Allow from all\n"
   conf += "</Directory>\n"

   conf += make_virtual_host(False, cfg['plain_port'])
   if cfg['ssl_enabled']:
      conf += make_virtual_host(True, cfg['ssl_port'])

   return conf

def setup_apache():
   cfg = psite.get_cfg()

   conf = make_apache_conf()
   with open("TMP.conf", "w") as outf:
      outf.write(conf)

   av_name = "/etc/apache2/sites-available/{}.conf".format(cfg['siteid'])
   old = psite.slurp_file(av_name)
   if old != conf:
      print("sudo sh -c 'cp TMP.conf {}; apache2ctl graceful'"
            .format(av_name))

   en_name = "/etc/apache2/sites-enabled/{}.conf".format(cfg['siteid'])
   if not os.path.exists(en_name):
      print("sudo a2ensite {}".format(cfg['siteid']))

def setup_siteid(site_name_arg, conf_key_arg):
   cfg = psite.get_cfg()

   if not 'site_name' in cfg:
      if site_name_arg is None:
         print("must specify site_name for first call to install-site")
         sys.exit(1)
      else:
         cfg['site_name'] = site_name_arg

   if conf_key_arg is None:
      cfg['conf_key'] = getpass.getuser()
   else:
      cfg['conf_key'] = conf_key_arg

   cfg['siteid'] = "{}-{}".format(cfg['site_name'], cfg['conf_key'])

def setup_dirs():
   cfg = psite.get_cfg()
   cfg['src_dir'] = os.getcwd()
   cfg['static_dir'] = "{}/static".format(cfg['src_dir'])
   cfg['www_dir'] = "/var/www/{}".format(cfg['siteid'])
   cfg['aux_dir'] = "/var/{}".format(cfg['siteid'])
   if not os.path.exists(cfg['www_dir']):
      print("sudo ln -sf {} {}".format(cfg['static_dir'], cfg['www_dir']))
   if not os.path.exists(cfg['aux_dir']):
      print("sudo sh -c 'mkdir -pm775 {0}; chown www-data.www-data {0}"
            .format(cfg['aux_dir']))

def setup_name_and_ports():
   cfg = psite.get_cfg()

   nat_info = re.split("\s+", psite.slurp_file ("/etc/apache2/NAT_INFO"))
   if len(nat_info) >= 2:
      cfg['nat_name'] = nat_info[0]
      cfg['port_base'] = int(nat_info[1])
   else:
      cfg['nat_name'] = "localhost"
      cfg['port_base'] = 8000

   val = psite.get_option("external_name")
   if val == None:
      cfg['external_name'] = cfg['nat_name']
      if 'plain_port' not in cfg:
         cfg['plain_port'] = get_free_port()
   else:
      cfg['external_name'] = val
      cfg['plain_port'] = 80
      cfg['ssl_port'] = 443

def setup_urls():
   cfg = psite.get_cfg()
   
   cfg['plain_url'] = make_url("http", cfg['external_name'], cfg['plain_port'])

   if cfg['ssl_enabled']:
       cfg['ssl_url'] = make_url("https", cfg['external_name'], cfg['ssl_port'])
       cfg['main_url'] = cfg['ssl_url']
   else:
       cfg['ssl_url'] = ""
       cfg['main_url'] = cfg['plain_url']

def copy_psite_php():
    if True:
       src = "{}/psite.php".format(os.path.dirname(__file__))
       try:
          os.remove("psite.php")
       except(FileNotFoundError):
          pass
       os.symlink (src, "psite.php");
    else:
       text = psite.slurp_file(name)
       with open("psite.php", "w") as outf:
          outf.write(text)

def setup_ssl():
    cfg = psite.get_cfg()

    if psite.get_option("ssl", "") == "no":
        cfg['ssl_enabled'] = False
        return

    if not find_certs():
        cfg['ssl_enabled'] = False
        return

    cfg['ssl_enabled'] = True
    if cfg.get('ssl_port', 0) == 0:
        cfg['ssl_port'] = get_free_port()

def install(site_name_arg=None, conf_key_arg=None):
   cfg = psite.get_cfg()
   setup_siteid(site_name_arg, conf_key_arg)

   cfg['db'] = psite.get_option("db", "")

   setup_name_and_ports()
   setup_ssl()

   setup_dirs()
   setup_urls()
   setup_apache()

   copy_psite_php()
   
   print(cfg['plain_url'])
   if cfg.get('ssl_url', None) != None:
      print(cfg['ssl_url'])

   psite.write_json("cfg.json", cfg)
   
