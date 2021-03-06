__author__ = 'justin_cinkelj'

import unittest
from osv import VM, VMParam
from osv import EnvAll, Env, App
from osv.api import env_var_split, ApiResponseError

from osv.settings import OSV_BRIDGE, OSV_CLI_APP, OSV_SRC
from time import sleep
import os
import os.path


class TestInternal(unittest.TestCase):
    def test_env_split(self):
        ss = 'asdf=ttrt'
        kk, vv = env_var_split(ss)
        self.assertEqual('asdf', kk)
        self.assertEqual('ttrt', vv)


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        net_mac='rand'
        cls.vm = VM(debug=True, use_image_copy=True, net_mac=net_mac)
        cls.vm.run(wait_up=True)

    @classmethod
    def tearDownClass(cls):
        cls.vm.terminate()
        cls.vm = None

    def test_env_all(self):
        env = EnvAll(self.vm)
        ret = env.get()
        self.assertTrue('OSV_VERSION' in ret.keys())

    def test_env_var(self):
        # set string
        var1 = Env(self.vm, 'var1')
        var1.set('asdf')
        ret = var1.get()
        self.assertEquals('asdf', ret)
        #
        # int auto-converted to string
        var2 = Env(self.vm, 'var2')
        var2.set(123)
        ret = var2.get()
        self.assertEquals('123', ret)
        #
        # special char
        var1.set('sss"ttrt')
        ret = var1.get()
        self.assertEquals('sss"ttrt', ret)
        #
        var1.delete()
        try:
            ret = var1.get()
            self.assertTrue(False)
        except ApiResponseError as ex:
            self.assertEquals(ex.response.status_code, 400)

    def test_app(self):
        # app_cli = App(self.vm, '/bin/cli.so')  # vm.terminate cannot send 'exit' any more
        # app_cli.run()
        app_http = App(self.vm, '/libhttpserver.so')
        app_http.run()
        #
        app_xx = App(self.vm, '/asdf/qwer.so')
        try:
            app_xx.run()
            self.assertTrue(False)
        except ApiResponseError as ex:
            self.assertEquals(ex.response.status_code, 500)

    # But syntax without additional api instance seems nicer.
    def test_via_vm_app(self):
        vm = self.vm
        vm.app('/libhttpserver.so').run()

    def test_via_vm_env(self):
        vm = self.vm
        vm.env('var_bla').set('bla_value')
        val = vm.env('var_bla').get()
        self.assertEqual('bla_value', val)

    def test_via_vm_env_all(self):
        vm = self.vm
        # env() with no name means 'all'
        val = vm.env().get()
        self.assertTrue('OSV_VERSION' in val)

##
