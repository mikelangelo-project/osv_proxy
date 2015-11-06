#!/usr/bin/env python

import sys
import os
import logging
import logging.config
from time import sleep
from os import environ
from osv import VM, Env
from random import randint
import argparse

import conf.settings as settings

def copy_env(vm):
    """
    Copy all environment variables of current process to OSv container.
    """
    log = logging.getLogger(__name__)
    for name in environ.keys():
        value = str(environ.get(name))
        log.info('Env %s = %s', name, value)
        vm.env(name).set(value)


def parse_args():
    log = logging.getLogger(__name__)
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('-i', '--image', default='',
                       help='path to OSv image')
    parser.add_argument('-m', '--memory', default=512,
                       help='VM memory in MB')
    parser.add_argument('--env', default=[], metavar='NAME=VALUE', action='append',
                       help='additional environ variables for OSv')
    parser.add_argument('--extra', default='',
                       help='additional params to pass to OSv scripts/run.py')
    parser.add_argument('osv_command', nargs=argparse.REMAINDER,
                   help='Application to start in VM (path and arguments)')
    args = parser.parse_args()
    log.info('Cmdline args: %s' % str(args))
    return args

def get_network_param():
    log = logging.getLogger(__name__)
    net_mac = 'rand'

    ## net_ip = settings.'192.168.122.%d/24' % randint(200, 250)
    ip0 = settings.OSV_IP_SUBNET
    ipmin = settings.OSV_IP_MIN
    ipmax = settings.OSV_IP_MAX

    # validate ipmin/max vs mask
    ip_range_from_mask = 2**(32-settings.OSV_IP_MASK)
    # for x.x.x.0/24, .1 is first valid IP, .254 is last valid IP
    assert(ipmin <= ipmax)
    assert(1 <= ipmin)
    assert(ipmin <= (ip_range_from_mask-2))
    assert(1 <= ipmax)
    assert(ipmax <= (ip_range_from_mask-2))

    ip0_bytes = [int(bb) for bb in ip0.split('.')]
    ip0_i32 = ip0_bytes[0] * 256**3 + ip0_bytes[1] * 256**2 + ip0_bytes[2] * 256**1 + ip0_bytes[3]
    assert(ip0_i32 % ip_range_from_mask == 0), 'subnet start IP is not aligned with mask'
    ip_i32 = ip0_i32 + randint(ipmin, ipmax)
    # split to individual bytes
    ip_i32_cumsum = 0
    ip_bytes = [0, 0, 0, 0]
    for ii in range(4):
        ip_bytes[ii] = (ip_i32 - ip_i32_cumsum) / 256**(3-ii)
        ip_i32_cumsum += ip_bytes[ii] * 256**(3-ii)
    net_ip = '%d.%d.%d.%d/%d' % (ip_bytes[0], ip_bytes[1], ip_bytes[2], ip_bytes[3], settings.OSV_IP_MASK)

    net_gw = settings.OSV_GW
    net_dns = settings.OSV_NS
    log.info('VM MAC %s, IP %s, GW %s, DNS %s', net_mac, net_ip, net_gw, net_dns)
    return net_mac, net_ip, net_gw, net_dns

def main():
    log = logging.getLogger(__name__)
    args = parse_args()
    #
    # run new VM
    # unsafe-cache for NFS mount

    net_mac, net_ip, net_gw, net_dns = get_network_param()
    gdb_port = 0  # disable gdb
    # gdb_port = randint(10000, 20000) # enable gdb at rand port

    osv_command = ' '.join(args.osv_command)

    vm = VM(debug=True,
            image=args.image,
            command='',
            memory=args.memory,
            use_image_copy=True,
            net_mac=net_mac, net_ip=net_ip, net_gw=net_gw, net_dns=net_dns,
            gdb_port=gdb_port,
            extra=args.extra)
    vm.run(wait_up=True, redirect_stdio=settings.OSV_VM_REDIRECT_STDIO)

    # Setup environ. orted already setup our env - copy it to VM. Then add additional env vars added by user.
    copy_env(vm)
    for env_var in args.env:
        name, value = env_var.split('=', 1)
        vm.env(name).set(value)

    # osv_command = '/usr/lib/mpi_hello.so 192.168.122.1 8080'
    log.info('Run program %s', osv_command)
    if osv_command:
        vm.app(osv_command).run()

    # shutdown
    # TODO Exit when osv_command finishes. Can that be detected via api?
    magic_file = '/tmp/lin_proxy-%d' % os.getpid()
    if os.path.exists(magic_file):
        os.remove(magic_file)
    ii = 0
    while ii >= 0:
        if ii%100 == 0:
            log.info('lin_proxy wait on   touch %s  ', magic_file)
        if os.path.exists(magic_file):
            break
        if not vm.is_up():
            break
        ii += 1
        sleep(0.1)
    log.info('lin_proxy DONE %s', magic_file)
    vm.terminate()
    sleep(1)


def setup_logging():
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'verbose': {
                # 'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
                'format': '%(levelname) 8s %(asctime)s %(module)s %(thread)d %(message)s'
            },
            'simple': {
                'format': '%(levelname) 8s %(message)s'
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.NullHandler',
                'formatter': 'simple'
            },
            'file': {
                'level': 'DEBUG',
                'class': 'logging.FileHandler',
                'formatter': 'verbose',
                'filename': settings.LOG_FILE,
            },
        },
        'loggers': {
            '': {
                'handlers': ['file'],
                'propagate': False,
                'level': settings.LOG_LEVEL,
            },
        }
    }
    logging.config.dictConfig(LOGGING)


if __name__ == '__main__':
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info('Start /*--------------------------------*/')
    ii = 0
    for arg in sys.argv:
        logger.info('  argv[%d] = %s', ii, arg)
        ii += 1
    main()
    logger.info('Done /*--------------------------------*/')

##
