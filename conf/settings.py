__author__ = 'justin_cinkelj'

import logging
import os

"""
IP in subnet 'OSV_IP_SUBNET/OSV_IP_MASK' will be used.
Within subnet, only IPs in range OSV_IP_SUBNET+[OSV_IP_MIN, OSV_IP_MAX] will are used.
"""
OSV_IP_SUBNET = '192.168.122.0'
OSV_IP_MIN = 200
OSV_IP_MAX = 250
OSV_IP_MASK = 24
OSV_GW = '192.168.122.1'
OSV_NS = '192.168.122.1'

OSV_VM_REDIRECT_STDIO = True

# Where is source code (./scripts/run.py)
OSV_SRC = '/opt/osv/'
# /tmp/** and /var/tmp/** might be forbidded in default libvirtd apparmor profile, so don't use them.
## OSV_WORK_DIR = '/tmp/osv-work'  # apparmor problem
## OSV_WORK_DIR = '/osv-work'  # requires sudo mkdir /osv-work; sudo chmod 777 /osv-work;
OSV_WORK_DIR = os.environ['HOME'] + '/osv-work'  # can be auto-generated

# logging
LOG_FILE = '/tmp/orted_lin_proxy.log'
LOG_LEVEL = logging.DEBUG

# update values
from local_settings import *

# osv.settings.OSV_SRC is separate var, update the value.
# Ugly and bad?
import osv.settings
osv.settings.OSV_SRC = OSV_SRC
osv.settings.OSV_WORK_DIR = OSV_WORK_DIR
