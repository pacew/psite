#! /usr/bin/env python3

import sys
import os
import configparser

import googleapiclient.discovery

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

def gserver_down(hostname):
    del_resp = compute.instances().delete(project=project_id, 
                                          zone=zone, 
                                          instance=hostname).execute()

    print(del_resp)

def gserver_up(hostname):
    img = compute.images().getFromFamily(
        project='ubuntu-os-cloud', family='ubuntu-2004-lts').execute()

    source_disk_image = img['selfLink']

    machine_type = f"zones/{zone}/machineTypes/n1-standard-1"

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
            {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
        ]
    }]

    metadata = {
        'items': [{
            'key': 'startup-script',
            'value': open("gboot").read()
        }]
    }

    config = dict()
    config['name'] = hostname
    config['machineType'] = machine_type
    config['disks'] = disks
    config['networkInterfaces'] = net
    config['metadata'] = metadata

    resp = compute.instances().insert(
        project=project_id,
        zone=zone,
        body=config).execute()
    print(resp)
    print(f"gcloud compute ssh {hostname}")

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
            sys.exit (0)
        usage()

    
    gserver_up(hostname)

if __name__ == "__main__":
    main()
