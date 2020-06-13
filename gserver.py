#! /usr/bin/env python3

import sys
import os
import json
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

def read_json(name, default=None):
    try:
        with open(name) as f:
            return json.load(f)
    except(OSError):
        if default is not None:
            return default
        raise

def write_json(name, val):
    with open("TMP.json", "w") as f:
        f.write(json.dumps(val, sort_keys=True, indent=2))
        f.write("\n")
    os.rename("TMP.json", name)

gcfg = read_json("gcfg.json", dict())

compute = googleapiclient.discovery.build('compute', 'v1')
print(compute)

if gcfg.get("img") is None:
    print("refetching")
    img = compute.images().getFromFamily(
        project='ubuntu-os-cloud', family='ubuntu-2004-lts').execute()
    gcfg['img'] = img

img = gcfg['img']
source_disk_image = img['selfLink']

print(source_disk_image)

machine_type = f"zones/{zone}/machineTypes/n1-standard-1"
print("machine_type", machine_type)

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

config = dict()
config['name'] = "test1"
config['machineType'] = machine_type
config['disks'] = disks
config['networkInterfaces'] = net

resp = compute.instances().insert(
    project=project_id,
    zone=zone,
    body=config).execute()

print(resp)
gcfg['resp'] = resp

write_json ("gcfg.json", gcfg)



