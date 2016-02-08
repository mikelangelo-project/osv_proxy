#!/usr/bin/env python

import sys
import os
import logging
import logging.config
from time import sleep
from os import environ
from osv import VM, Env, VMParam
from random import randint
import argparse
from copy import deepcopy
import psutil
import shlex

import conf.settings as settings


'''
mac_addr is string like '11:22:33:44:55:F0'.
offset is int, and sum of both is returned.
  '11:22:33:44:55:F0' +  8 = '11:22:33:44:55:F8'
  '11:22:33:44:55:F0' + 18 = '11:22:33:44:56:02'
'''
def mac_address_add(mac_addr, offset):
    # convert hex string to large int
    mac_part_str = mac_addr.split(':')
    mac_part_int = [int(st, 16) for st in mac_part_str]
    mac_int = 0
    for ii in range(6):
        exp = 256**ii
        mac_int += mac_part_int[6-1-ii] * exp
    # add offset
    mac_int += offset
    # convert large int back to hex string
    mac2_part_str = []
    for ii in range(6, 0, -1):
        exp = 256**(ii-1)
        num = mac_int / exp
        mac_int -= num * exp
        mac2_part_str.append('%02X' % num)
    mac2 = ':'.join(mac2_part_str)
    return mac2


'''
ip_addr_mask is string like '11.22.33.240/24'.
offset is int, and sum of both is returned.
  '11.22.33.240/24' +  8 = '11.22.33.248/24'
  '11.22.33.240/24' + 18 = '11.22.34.2/24'
No special check is made for subnet overflow.
'''
def ip_address_add(ip_addr_mask, offset):
    ip_addr, ip_mask = ip_addr_mask.split('/')
    ip_part_str = ip_addr.split('.')
    ip_part_int = [int(st) for st in ip_part_str]
    ip_int = 0
    for ii in range(4):
        exp = 256**ii
        ip_int += ip_part_int[4-1-ii] * exp
    # add offset
    ip_int += offset
    # convert large int back to hex string
    ip2_part_str = []
    for ii in range(4, 0, -1):
        exp = 256**(ii-1)
        num = ip_int / exp
        ip_int -= num * exp
        ip2_part_str.append('%d' % num)
    ip2 = '.'.join(ip2_part_str)
    ip2 += '/' + ip_mask
    return ip2


def parse_args():
    log = logging.getLogger(__name__)
    class Args:
        pass
    args = Args()

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('-i', '--image', default='',
                       help='Path to OSv image. Absolute or relative to OSC_SRC dir.')
    parser.add_argument('-m', '--memory', default=512,
                       help='VM memory in MB')
    parser.add_argument('-c', '--cpus', default=psutil.cpu_count(),
                       help='Number of CPUs')
    parser.add_argument('--nfs', default=[], metavar='NFS mount', action='append',
                       help='Additional NFS mountpoints. Example: --nfs "nfs://192.168.122.1/ggg/?uid=0 /fff"')
    #
    parser.add_argument('-b', '--bridge', default=settings.OSV_BRIDGE,
                       help='Ethernet bridge to use.')
    parser.add_argument('--net-mode', default=VMParam.NET_DHCP, choices=[VMParam.NET_DHCP, VMParam.NET_STATIC],
                       help='Static or DHCP network mode.')
    parser.add_argument('--net-mac', default='rand',
                       help='MAC address (52:54:00:xx:xx:xx), default is random. '
                            'Offset (orte_ess_vpid-1) will be added to user-supplied MAC to ensure multiple VMs don\'t use same address.')
    parser.add_argument('--net-ip', default='',
                       help='IP address in CIDR format (say 192.168.122.10/24). '
                            'Implies static IP configuration. '
                            'Offset (orte_ess_vpid-1) will be added to user-supplied IP to ensure multiple VMs don\'t use same address.')
    parser.add_argument('--net-gw', default=settings.OSV_GW,
                       help='Network default gateway.')
    parser.add_argument('--net-dns', default=settings.OSV_NS,
                       help='DNS server.')
    #
    parser.add_argument('-u', '--unsafe-cache', action='store_true',
                       help='Set cache to unsafe.')
    parser.add_argument('-g', '--gdb', action='store_true',
                       help='Enable gdb at port 1234.')
    parser.add_argument('--gdb-port', default=0, metavar='PORT',
                       help='Enable gdb at port PORT')

    '''
    In command
    mpirun -n 2 -H 127.0.0.2 --launch-agent "/lin_proxy.sh -c4 -m1024 --bb='cc dd' " -wd / /usr/lib/mpi_hello.so
    mpirun calls lin_proxy.py as
    /lin_proxy.py -c4 -m1024 --bb='cc dd' -mca ess env -mca orte_ess_jobid 1899888640 -mca orte_ess_vpid 1 -mca orte_ess_num_procs 2 ...
        --tree-spawn -mca orte_launch_agent "/lin_proxy.sh -c4 -m1024 --bb='cc dd' " --tree-spawn
    In above, argparse would like to interpret -mca as memory settings. So we parse string STR from '-mca orte_launch_agent STR'.

    But if script is called without mpirun (say simple -h switch), then all params are for us.
    '''
    if 'orte_launch_agent' in sys.argv:
        ii = sys.argv.index('orte_launch_agent')
        assert(sys.argv[ii-1] == '-mca')
        our_argv_str = sys.argv[ii+1]
        # our_argv_str is now "/lin_proxy.sh -c4 -m1024 --bb='cc dd' "
        our_argv = shlex.split(our_argv_str)
    else:
        # we were not called via mpirun
        our_argv = sys.argv
    log.debug('our_argv %s' % str(our_argv))
    args = parser.parse_args(our_argv[1:])

    if args.gdb and args.gdb_port == 0:
        args.gdb_port = 1234  # randint(10000, 20000)
    log.info('Cmdline args: %s' % str(args))

    # Finalize networking params.
    if args.net_ip:
        # static IP explicitly requested, force static mode
        args.net_mode = VMParam.NET_STATIC
    # Adjust mac and IP address if supplied
    orte_ess_vpid = 1  # mpirun starts incrementing orte_ess_vpid from 1
    if 'orte_ess_vpid' in sys.argv:
        ii = sys.argv.index('orte_ess_vpid')
        assert(sys.argv[ii-1] == '-mca')
        orte_ess_vpid = int(sys.argv[ii+1])
    if args.net_mac != 'rand':
        args.net_mac = mac_address_add(args.net_mac, orte_ess_vpid-1)
    if args.net_ip:
        args.net_ip = ip_address_add(args.net_ip, orte_ess_vpid-1)
    # if static IP should be used, and there is no explicit IP supplied, use random IP address
    if args.net_mode == VMParam.NET_STATIC and args.net_ip == '':
        args.net_ip = get_rand_ip_address(settings.OSV_IP_SUBNET, settings.OSV_IP_PREFIX, settings.OSV_IP_MIN, settings.OSV_IP_MAX)
    log.info('VM MAC %s, IP %s, GW %s, DNS %s', args.net_mac, args.net_ip, args.net_gw, args.net_dns)

    # All unknown params are passed to orted.so
    args.osv_command = deepcopy(sys.argv)
    assert(args.osv_command[0].endswith('/lin_proxy.py'))
    args.osv_command[0] = '/usr/lib/orted.so'
    # Check and remove all our params
    for ii in range(1, len(our_argv)):
        argv1 = args.osv_command[ii]
        argv2 = our_argv[ii]
        assert(argv1 == argv2)
    log.debug('Removing our_argv: %s' % str(args.osv_command[1: len(our_argv)]))
    del args.osv_command[1: len(our_argv)]
    # remove args "-mca orte_launch_agent /home/justin_cinkelj/devel/mikelangelo/osv_proxy/lin_proxy.py"
    for ii in range(2, len(args.osv_command)):
        arg0 = args.osv_command[ii-2]
        arg1 = args.osv_command[ii-1]
        arg2 = args.osv_command[ii]
        #log.debug('ii=%d arg0_1_2 %s %s %s', ii, arg0, arg1, arg2)
        # arg2 will be "/lin_proxy.sh -c4 -m104 --bb='cc dd'"
        arg2_program = arg2.split(' ')[0]
        if arg0 == '-mca' and arg1 == 'orte_launch_agent' and \
                (arg2_program.endswith('/lin_proxy.sh') or arg2_program.endswith('/lin_proxy.py')):
            log.info('args.osv_command remove: %s' % str(args.osv_command[ii-2: ii+1]))
            del args.osv_command[ii-2: ii+1]
            break  # ii is invalid now
    # escape ';' in orte_hnp_uri
    for ii in range(2, len(args.osv_command)):
        arg0 = args.osv_command[ii-2]
        arg1 = args.osv_command[ii-1]
        arg2 = args.osv_command[ii]
        #log.debug('ii=%d arg0_1_2 %s %s %s', ii, arg0, arg1, arg2)
        if arg0 == '-mca' and arg1 == 'orte_hnp_uri' and (';tcp' in arg2):
            log.info('args.osv_command orte_hnp_uri add quote to %s' % str(args.osv_command[ii-2: ii+1]))
            args.osv_command[ii] = '"' + arg2 + '"'
    log.info('final args.osv_command: %s' % str(args.osv_command))

    return args

'''
Generate random static IP from subnet ip0 with netmask.
Random value is in range [ip0 + ipmin, ip0 + ipmax].
For params ('192.168.122.0', 24, 200, 250) is returned
'192.168.122.xx/24', with 200 <= xx <= 250
'''
def get_rand_ip_address(ip0, net_prefix, ipmin, ipmax):
    log = logging.getLogger(__name__)

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
    net_ip = '%d.%d.%d.%d/%d' % (ip_bytes[0], ip_bytes[1], ip_bytes[2], ip_bytes[3], net_prefix)
    return net_ip


def main():
    log = logging.getLogger(__name__)
    # OSV_WORK_DIR - where to put VM image files and console log.
    # /tmp/** and /var/tmp/** might be forbidded in default libvirtd apparmor profile, so don't use them.
    ## OSV_WORK_DIR = '/tmp/osv-work'  # apparmor problem
    ## OSV_WORK_DIR = '/osv-work'  # requires sudo mkdir /osv-work; sudo chmod 777 /osv-work;
    ## OSV_WORK_DIR = os.environ['HOME'] + '/osv-work'  # can be auto-generated, no root rights required
    if not os.path.isdir(settings.OSV_WORK_DIR):
        os.mkdir(settings.OSV_WORK_DIR)
        # others need write perm (libvirt, kvm)
        os.chmod(settings.OSV_WORK_DIR, 0777)
    args = parse_args()


    # run new VM
    vm = VM(debug=True,
            image=args.image,
            command='',
            cpus=args.cpus,
            memory=args.memory,
            use_image_copy=True,
            net_mac=args.net_mac,
            net_ip=args.net_ip,
            net_gw=args.net_gw,
            net_dns=args.net_dns,
            bridge=args.bridge,
            gdb_port=args.gdb_port)
    stdout_data = vm.run(wait_up=True)
    sys.stdout.write(stdout_data)
    sys.stdout.flush()

    for nfs_mount in args.nfs:
        mount_cmd = '/tools/mount-nfs.so %s' % nfs_mount
        log.info('Run mount_cmd %s', mount_cmd)
        vm.app_api(mount_cmd).run()
    # Does http call return before mount is finished ? Then osv_commnad might try to use NFS before its mounted.
    # osv_command = '/usr/lib/mpi_hello.so 192.168.122.1 8080'
    osv_command = ' '.join(args.osv_command)
    log.info('Run program %s', osv_command)
    if osv_command:
        vm.app_api(osv_command).run()

    # shutdown
    # TODO Exit when osv_command finishes. Can that be detected via api?
    ii = 0
    while ii >= 0:
        if ii%100 == 0:
            log.info('lin_proxy wait on vm terminate')
        if not vm.is_up():
            log.info('lin_proxy VM not up')
            break
        stdout_data = vm.read_std()
        sys.stdout.write(stdout_data)
        sys.stdout.flush()
        ii += 1
        sleep(0.1)
    log.info('lin_proxy DONE')
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
        logger.debug('  argv[%d] = %s', ii, arg)
        ii += 1
    logger.info('  argv = %s', ' '.join(sys.argv))
    main()
    logger.info('Done /*--------------------------------*/')

##
