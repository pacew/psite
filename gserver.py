#! /usr/bin/env python3

import sys
import os
import configparser
import time
import pwd
import subprocess
import random

import googleapiclient.discovery

from pprint import PrettyPrinter
def pprint(val):
    PrettyPrinter().pprint(val)


zone = "us-east4-c"

gcloud_dir = os.path.join(os.getenv('HOME'), ".config/gcloud")
gcloud_default = os.path.join(gcloud_dir, "configurations/config_default")
config = configparser.ConfigParser()
with open(gcloud_default) as inf:
  config.read_file(inf)
acct_email = config["core"]["account"]
project_id = config["core"]["project"]

adc_file = os.path.join(gcloud_dir, "legacy_credentials", acct_email, "adc.json")
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = adc_file

compute = googleapiclient.discovery.build('compute', 'v1')

def make_script():
    p = pwd.getpwuid(os.getuid())
    gboot_user = p.pw_name

    s = list()
    s.append("#! /bin/bash")

    keyfile = os.path.join(os.getenv('HOME'), ".ssh/id_rsa.pub")
    key = open(keyfile).read().strip()
    
    s.append(f"GBOOT_USER='{gboot_user}'")
    s.append(f"GBOOT_PUBKEY='{key}'")

    script = "\n".join(s)+"\n\n"

    with open("gboot") as f:
        script += f.read()
    
    with open("TMP.script", "w") as outf:
        outf.write(script)

    return script
    
def gserver_down(hostname):
    machine_name = hostname.split('.')[0]

    del_resp = compute.instances().delete(project=project_id, 
                                          zone=zone, 
                                          instance=machine_name).execute()

    print(del_resp)



def gserver_up(hostname):
    ipaddr = subprocess.check_output(f"dig +short {hostname}",
                                     shell=True,
                                     encoding='utf8').strip()

    machine_name = hostname.split('.')[0]

    img = compute.images().getFromFamily(
        project='ubuntu-os-cloud', family='ubuntu-2004-lts').execute()

    source_disk_image = img['selfLink']

    machine_type = f"zones/{zone}/machineTypes/n1-standard-1"
    script = make_script ()

    disks = list()
    disks.append({
        'boot': True,
        'autoDelete': True,
        'initializeParams': {
            'sourceImage': source_disk_image,
        }
    })

    net = [{
        'network': 'global/networks/default',
        'accessConfigs': [
            {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT', 'natIP': ipaddr }
        ]
    }]

    metadata = {
        'items': [{
            'key': 'startup-script',
            'value': script
        }]
    }

    config = dict()
    config['name'] = machine_name
    config['machineType'] = machine_type
    config['disks'] = disks
    config['networkInterfaces'] = net
    config['metadata'] = metadata

    resp = compute.instances().insert(
        project=project_id,
        zone=zone,
        body=config).execute()
    print(resp)

    print()
    print((f"for h in {ipaddr} {hostname} {machine_name};"
           " do ssh-keygen -R $h > /dev/null 2>&1; done"))
    print()


def get_status(hostname):
    resp = compute.instances().get(project=project_id, zone=zone, instance=hostname).execute()
    iface = resp['networkInterfaces'][0]
    cfg = iface['accessConfigs'][0]
    ipaddr = cfg['natIP']
    print(ipaddr)

def usage():
    print("usage: gserver hostname [Down]")
    sys.exit (1)

def main():
    if len(sys.argv) < 2:
        usage()
        
    hostname = sys.argv[1]

    if len(sys.argv) > 2:
        if sys.argv[2] == "Down":
            gserver_down(hostname)
            sys.exit(0)

        if sys.argv[2] == "up":
            gserver_up(hostname)
            sys.exit(0)

        if sys.argv[2] == "status":
            get_status(hostname)
            sys.exit(0)

if __name__ == "__main__":
    main()
