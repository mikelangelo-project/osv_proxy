__author__ = 'justin_cinkelj'

import unittest
from osv import VM, VMParam
from osv.vm import cidr_to_ip_mask

from osv.settings import OSV_BRIDGE, OSV_CLI_APP, OSV_SRC
from time import sleep
import os
import os.path


class TestSettings(unittest.TestCase):
    def test_settings(self):
        self.assertTrue(os.path.isdir(OSV_SRC))
        # self.assertTrue(os.path.exists(OSV_SRC + '/build/release/usr.img'))
        self.assertTrue(os.path.exists(OSV_SRC + '/build/debug/usr.img'))
        # TODO check OSV_BRIDGE


class TestInternal(unittest.TestCase):
    def test_cidr(self):
        cidr = '192.168.122.34/24'
        ip, netmask = cidr_to_ip_mask(cidr)
        self.assertEqual(ip, '192.168.122.34')
        self.assertEqual(netmask, '255.255.255.0')
        #
        cidr = '192.168.122.34/16'
        ip, netmask = cidr_to_ip_mask(cidr)
        self.assertEqual(ip, '192.168.122.34')
        self.assertEqual(netmask, '255.255.0.0')
        #
        cidr = '192.168.122.34/8'
        ip, netmask = cidr_to_ip_mask(cidr)
        self.assertEqual(ip, '192.168.122.34')
        self.assertEqual(netmask, '255.0.0.0')
        #
        cidr = '192.168.122.34/28'
        ip, netmask = cidr_to_ip_mask(cidr)
        self.assertEqual(ip, '192.168.122.34')
        self.assertEqual(netmask, '255.255.255.240')
        #
        cidr = '192.168.122.34/20'
        ip, netmask = cidr_to_ip_mask(cidr)
        self.assertEqual(ip, '192.168.122.34')
        self.assertEqual(netmask, '255.255.240.0')
        #
        cidr = '192.168.122.34/30'
        ip, netmask = cidr_to_ip_mask(cidr)
        self.assertEqual(ip, '192.168.122.34')
        self.assertEqual(netmask, '255.255.255.252')


class TestVMParam(unittest.TestCase):
    def test_vm_param(self):
        vmp = VMParam()
        arg = vmp._build_run_command()
        result = "['./scripts/run.py', '--image', 'build/release/usr.img', '--memsize', '512', '--novnc', '--nogdb', '-n', '-v']"
        self.assertEqual(str(arg), result)
        #
        vmp = VMParam(networking=False)
        arg = vmp._build_run_command()
        result = "['./scripts/run.py', '--image', 'build/release/usr.img', '--memsize', '512', '--novnc', '--nogdb']"
        self.assertEqual(str(arg), result)
        #
        vmp = VMParam(cpus=3, memory=777, gdb=True, vnc=True)
        arg = vmp._build_run_command()
        result = "['./scripts/run.py', '--image', 'build/release/usr.img', '--vcpus', '3', '--memsize', '777', '-n', '-v']"
        self.assertEqual(str(arg), result)
        #
        vmp = VMParam(command='/my/test.so 12 34')
        arg = vmp._build_run_command()
        result = "['./scripts/run.py', '--image', 'build/release/usr.img', '--memsize', '512', '--novnc', '--nogdb', '-n', '-v', '-e', '/my/test.so 12 34']"
        self.assertEqual(str(arg), result)
        #
        vmp = VMParam(command='/my/test.so 12 34', gdb=True, vnc=True, net_ip='1.2.3.4/8', net_gw='4.3.2.1', net_dns='8.8.8.8')
        arg = vmp._build_run_command()
        result = "['./scripts/run.py', '--image', 'build/release/usr.img', '--memsize', '512', '-n', '-v', '-e', '--ip=eth0,1.2.3.4,255.0.0.0 --defaultgw=4.3.2.1 --nameserver=8.8.8.8 /my/test.so 12 34']"
        self.assertEqual(str(arg), result)
        #
        vmp = VMParam(gdb=True, vnc=True, net_ip='1.2.3.4/8', net_gw='4.3.2.1', net_dns='8.8.8.8')
        arg = vmp._build_run_command()
        result = "['./scripts/run.py', '--image', 'build/release/usr.img', '--memsize', '512', '-n', '-v', '-e', '--ip=eth0,1.2.3.4,255.0.0.0 --defaultgw=4.3.2.1 --nameserver=8.8.8.8 /cli/cli.so']"
        self.assertEqual(str(arg), result)

## /etc/init.d/libvirt-bin restart - to reset DHCP server
class TestVM(unittest.TestCase):
    def test_run(self, td=1):
        vm = VM(debug=True)
        vm.run()
        vm.wait_up()
        self.assertTrue(vm._ip)
        self.assertEquals(0, vm._ip.find('192.168.122.'))  # default virbr0 subnet
        self.assertTrue(vm._child_cmdline_up)
        vm.terminate()

