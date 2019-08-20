import psite
import hashlib
import subprocess


def s3_backup_bucket_name():
    cfg = psite.get_cfg()

    key = "psite-backup-" + cfg['siteid']
    h = hashlib.sha256(key.encode('utf-8')).hexdigest()

    return cfg['siteid'] + "-" + h[0:5]


def s3_setup():
    cfg = psite.get_cfg()

    bucket_name = s3_backup_bucket_name()
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
    bucket_name = s3_backup_bucket_name()

    cmd = []
    cmd.append("aws")
    cmd.append("--profile")
    cmd.append(cfg['siteid'])
    cmd.append("s3")
    cmd.append("sync")
    cmd.append(local_dir)
    cmd.append("s3://"+bucket_name)
    print(" ".join(cmd))
    subprocess.call(cmd)
