__author__ = 'justin_cinkelj'

import logging
import subprocess
import os
import math
from uuid import uuid4
from settings import OSV_BRIDGE, OSV_CLI_APP, OSV_SRC
from subprocess import Popen, PIPE
from time import sleep


# for '192.168.1.2/24' return '192.168.1.2' and '255.255.255.0'
def cidr_to_ip_mask(cidr):
    ip, bits = cidr.split('/')
    n1 = int(bits)
    n0 = 32 - n1
    ss = '1' * n1 + '0' * n0
    nm = [ss[-32:-24], ss[-24:-16], ss[-16:-8], ss[-8:]]  # reversed order, nm[0] is highest byte
    nm2 = [int(nm_tmp, 2) for nm_tmp in nm]
    netmask = '%d.%d.%d.%d' % (nm2[0], nm2[1], nm2[2], nm2[3])
    return ip, netmask


class VMParam:
    NET_STATIC = 'static'
    NET_DHCP = 'dhcp'
    NET_NONE = 'net-none'

    def __init__(self,
                 command='',
                 image='',
                 cpus=0,
                 memory=512,

                 networking=True,
                 net_ip='',
                 net_gw='',
                 net_dns='',

                 vnc=False,
                 vnc_port=0,
                 gdb=False,
                 gdb_port=0,
                 verbose=False,
                 debug=False,
                 extra=[]
                 ):
        self._extra = extra  # args to blindly pass-trough to run.py
        self._command = command
        self._cpus = cpus
        self._memory = memory
        self._debug = debug
        self._verbose = verbose
        # image relative to OSV_SRC, or abs path
        if image:
            self._image = image
        else:
            mode = 'debug' if self._debug else 'release'
            self._image = 'build/%s/usr.img' % mode
        self._vnc_port = vnc_port
        self._vnc = True if self._vnc_port else vnc
        self._gdb_port = gdb_port
        self._gdb = True if self._gdb_port else gdb

        self._net_ip = net_ip
        self._net_gw = net_gw
        self._net_dns = net_dns
        if net_ip:
            self._net_mode = VMParam.NET_STATIC
        elif networking:
            self._net_mode = VMParam.NET_DHCP
        else:
            self._net_mode = VMParam.NET_NONE

    def _build_run_command(self):
        arg = ['./scripts/run.py']
        if self._image:
            arg.extend(['--image', self._image])
        if self._cpus:
            arg.extend(['--vcpus', str(self._cpus)])
        if self._memory:
            arg.extend(['--memsize', str(self._memory)])
        if self._verbose:
            arg.append('--verbose')
        if self._debug:
            arg.append('--debug')

        if self._vnc:
            if self._vnc_port:
                arg.extend(['--vnc', str(self._vnc_port)])
            else:
                # vnc enabled by default
                pass
        else:
            arg.append('--novnc')

        if self._gdb:
            if self._gdb_port:
                arg.extend(['--gdb', str(self._gdb_port)])
            else:
                # gdb enabled by default
                pass
        else:
            arg.append('--nogdb')

        cmd_net = ''
        if self._net_mode == VMParam.NET_NONE:
            # net disabled by default
            pass
        elif self._net_mode == VMParam.NET_DHCP:
            # -v for KVM vhost networking, requires root/sudo rights
            arg.extend(['-n', '-v'])
        elif self._net_mode == VMParam.NET_STATIC:
            # static network config is pushed in command param
            # ./scripts/run.py -n -e "--ip=eth0,10.0.0.2,255.255.255.0 \
            #  --defaultgw=10.0.0.1 --nameserver=10.0.0.1 `cat build/release/cmdline`"
            arg.extend(['-n', '-v'])
            ip, netmask = cidr_to_ip_mask(self._net_ip)
            cmd_net += '--ip=eth0,%s,%s' % (ip, netmask)
            if self._net_gw:
                cmd_net += ' --defaultgw=%s' % self._net_gw
            if self._net_dns:
                cmd_net += ' --nameserver=%s' % self._net_dns

        full_command = ''
        if cmd_net:
            # net_cmd for static ip must be passed as part of command (with default cli.so or with user-defined app)
            if self._command:
                full_command = '%s %s' % (cmd_net, self._command)
            else:
                full_command = '%s %s' % (cmd_net, OSV_CLI_APP)
        elif self._command:
            full_command = self._command
        if full_command:
            arg.extend(['-e', full_command])

        arg.extend(self._extra)

        return arg


class VM:
    """
    Create new container.
    net_ip is in CIDR notation 'ip/bits'
    """
    def __init__(self, **kwargs):
        self._param = VMParam(**kwargs)

        # other vars
        self._child = None
        self._child_cmdline_up = False
        self._child_stdout = None
        self._child_stderr = None
        self._ip = ''
        self._api_up = False  # set by first API call

    def run(self, wait_up=False):
        log = logging.getLogger(__name__)
        pid = os.getpid()
        id = str(uuid4())[:8]
        tmpl = '/tmp/osv-%d-%s' % (pid, id)
        fin = PIPE
        fout = open(tmpl + '-stdout.log', 'w', buffering=1)
        ferr = open(tmpl + '-stderr.log', 'w', buffering=1)
        log.info('OSv output redirected to %s-[stdout,stderr}.log', tmpl)
        fout.write('Running command:\n')
        fout.write(' '.join(self._param._build_run_command()) + '\n')
        fout.write(str(self._param._build_run_command())+ '\n')
        fout.write('\n')
        self._child_stdout = open(tmpl + '-stdout.log')
        self._child_stderr = open(tmpl + '-stderr.log')

        # self._child = Popen(self._param._build_run_command(), stdin=fin, stdout=fout, stderr=ferr, close_fds=True, cwd=OSV_SRC)
        #
        arg = ['sudo ']
        arg.extend(self._param._build_run_command())
        arg_str = ' '.join(arg)
        os.chdir(OSV_SRC)
        self._child = Popen(arg_str, shell=True, stdin=fin, stdout=fout, stderr=ferr, close_fds=True, cwd=OSV_SRC)

        self._child_cmdline_up = False
        log.info('Running child pid=%d', self._child.pid)
        if self._param._net_mode == VMParam.NET_STATIC:
            self._ip = self._param._net_ip.split('/')[0]
        if wait_up:
            self.wait_up()

    def terminate(self):
        # shutdown via rest api ?
        log = logging.getLogger(__name__)
        if self._child:
            log.info('Terminating child pid=%d', self._child.pid)
            poll_ret = self._child.poll()
            if poll_ret or poll_ret == 0:
                # Invalid param, run.py reported error.
                # Or normal termintaino of app started via command.
                log.info('Child pid=%d already terminated, exit code %d', self._child.pid, poll_ret)
            else:
                # self._child.terminate()  # kills run.py, but not qemu-system-x86_64
                # communicate will deadlock if Vm is not fully up yet ('exit' will be lost)
                self.wait_cmd_prompt()
                log.debug('child pid=%d typing exit', self._child.pid)
                self._child.communicate('\nexit\n')  # type exit in VM
            self._child = None
            self._child_cmdline_up = False
            self._child_stdout.close()
            self._child_stderr.close()

    # read stdout, stderr
    # update child_cmdline_up when cmd prompt found
    def read_std(self):
        log = logging.getLogger(__name__)
        out = self._child_stdout.read()
        err = self._child_stderr.read()
        if not self._child_cmdline_up or not self._ip:
            for cur_line in out.split('\r\n'):
                if not self._child_cmdline_up:
                    '''
                    ideal line == '/# '
                    but 'random: device unblocked.' might be there too.
                    or 'random' garbage can be prepend ('ESC[6n/# ')
                    '''
                    if cur_line[:3] =='/# ' or cur_line[-3:] == '/# ':
                        log.info('child pid=%d cmd_prompt is up', self._child.pid)
                        self._child_cmdline_up = True
                if not self._ip:
                    # Is IP assigned ? Search for 'eth0: $IP'
                    # only in verbose mode - [I/246 dhcp]: Configuring eth0: ip 192.168.122.37 subnet mask 255.255.255.0 gateway 192.168.122.1 MTU 1500
                    # there is also: 'eth0: ethernet address: 52:54:00:12:34:56'
                    ss = 'eth0: '
                    ss_ignore = 'eth0: ethernet address:'
                    if 0 == cur_line.find(ss_ignore):
                        log.debug('child pid=%d eth0 ignore line, %s', self._child.pid, cur_line)
                        pass
                    elif 0 == cur_line.find(ss):
                        log.debug('child pid=%d eth0 IP found, %s', self._child.pid, cur_line)
                        self._ip = cur_line.split(' ')[1]
                        log.info('child pid=%d IP via DHCP, %s', self._child.pid, self._ip)
        return [out, err]

    # will eat stdout/err
    # File pos could be reset to orig value.
    # Meaningful only for default cli.so app.
    def wait_cmd_prompt(self, Td = 5, Td2 = 0.1):
        log = logging.getLogger(__name__)
        if self._param._command and self._param._command.find(OSV_CLI_APP) == -1:
            log.debug('child pid=%d cmd_prompt shows up only with cli.so app', self._child.pid)
            return False
        if self._child_cmdline_up:  # and self._ip:
            return True
        iimax = math.ceil(float(Td) / Td2)
        ii = 0
        while ii < iimax:
            [aa, bb] = self.read_std()
            if self._child_cmdline_up:
                return True
            log.debug('child pid=%d cmd_prompt not up yet', self._child.pid)
            sleep(Td2)
            ii += 1
        return False

    def wait_ip(self, Td = 5, Td2 = 0.1):
        log = logging.getLogger(__name__)
        if self._ip:
            return True
        iimax = math.ceil(float(Td) / Td2)
        ii = 0
        while ii < iimax:
            [aa, bb] = self.read_std()
            if self._ip:
                return True
            log.debug('child pid=%d ip not up yet', self._child.pid)
            sleep(Td2)
            ii += 1
        return False

    def wait_up(self, Td = 5, Td2 = 0.1):
        self.wait_ip(Td, Td2)
        self.wait_cmd_prompt(Td, Td2)

logging.basicConfig(level=logging.DEBUG)

##
