__author__ = 'justin_cinkelj'
'''
A few global settings
'''
import os

# where is OSv source code (scripts/run.py and friends)
OSV_SRC = '/opt/osv-src'
OSV_BRIDGE = 'virbr0'
OSV_CLI_APP = '/cli/cli.so'  # path to cli app inside OSv containers
OSV_API_PORT = 8000

# Where to put VM image files and console log.
# /tmp/** and /var/tmp/** might be forbidded in default libvirtd apparmor profile, so don't use them.
## OSV_WORK_DIR = '/tmp/osv-work'  # apparmor problem
## OSV_WORK_DIR = '/osv-work'  # requires sudo mkdir /osv-work; sudo chmod 777 /osv-work;
OSV_WORK_DIR = os.environ['HOME'] + '/osv-work'  # can be auto-generated
