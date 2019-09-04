import psite
import hashlib
import os
import sys


def s3_backup_bucket_name(for_siteid):
    key = "psite-backup-" + for_siteid
    h = hashlib.sha256(key.encode('utf-8')).hexdigest()

    return for_siteid + "-" + h[0:5]


def s3_setup():
    cfg = psite.get_cfg()

    bucket_name = s3_backup_bucket_name(cfg['siteid'])
    user_name = "backup-" + cfg['siteid']

    print("login at https://aws.amazon.com/console/")
    print("In S3: Create bucket named " + bucket_name)
    print("  In tags, set 'siteid' to '{}'".format(cfg['siteid']))
    print("In IAM: Create policy named " + user_name)
    print("  Service S3, Actions ListBucket and PutObject")
    print("in IAM: Create user named " + user_name)
    print("  check Programmatic access")
    print("  don't add to a group")
    print("  tag siteid to " + cfg['siteid'])
    print("  display the access key and store with")
    print("aws --profile {} configure set aws_access_key_id KEY_ID".format(
        cfg['siteid']))
    print("aws --profile {} configure set aws_secret_access_key SECRET".format(
        cfg['siteid']))

    print("  attach the policy named " + user_name)
    print("run psite backup, then psite s3-sync")
    print("don't be surprised if first attempt gets access error")


def s3_sync():
    cfg = psite.get_cfg()

    local_dir = "{}/backups".format(cfg['aux_dir'])
    bucket_name = s3_backup_bucket_name(cfg['siteid'])

    cmd = "aws --profile {} s3 sync {} s3://{}".format(
        cfg['siteid'], local_dir, bucket_name)
    print(cmd)
    if os.system(cmd) != 0:
        print("aws s3 sync error")
        sys.exit(1)


def s3_get_latest():
    if len(sys.argv) < 3:
        print("usage: psite get-latest siteid")
        sys.exit(1)
    for_siteid = sys.argv[2]


    cfg = psite.get_cfg()

    bucket_name = s3_backup_bucket_name(for_siteid)

    cmd = "aws s3 cp s3://{}/latest.gz .".format(bucket_name)
    print(cmd)
    if os.system(cmd) != 0:
        print("aws s3 cp error")
        sys.exit(1)
