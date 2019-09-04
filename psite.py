import json
import os
import socket
from html.parser import HTMLParser

from install import install  # noqa: F401
from db import (mkschema, query, fetch, get_seq, commit,  # noqa: F401
                getvar, setvar, do_backup, restore, cmd_sql)

from aws import (s3_setup, s3_sync)  # noqa: F401


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


class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()
