__author__ = 'justin_cinkelj'
'''
REST api to access OSv container.
'''

from osv import VM
from settings import OSV_API_PORT
import requests
import ast
from urllib import urlencode


class ApiError(Exception):
    pass


class ApiResponseError(ApiError):
    def __init__(self, message, response):
        super(ApiError, self).__init__(message)
        self.response = response


class BaseApi:
    def __init__(self, vm):
        assert(isinstance(vm, VM))
        self.vm = vm
        self.base_path = ''

    def wait_up(self):
        if not self.vm._api_up:
            self.vm.wait_ip()
            # dummy request, just to wait on service up
            uri = 'http://%s:%d' % (self.vm._ip, OSV_API_PORT)
            resp = requests.get(uri + '/os/uptime')
            self.vm._api_up = True

    def uri(self):
        return 'http://%s:%d' % (self.vm._ip, OSV_API_PORT) + self.base_path

    def http_get(self, path_extra=''):
        self.wait_up()
        resp = requests.get(self.uri() + path_extra)
        if resp.status_code != 200:
            raise ApiResponseError('HTTP call failed', resp)
        return resp.content

    # OSv uses data encoded in URL manytimes (more often than POST data).
    def http_post(self, params, data=None, path_extra=''):
        self.wait_up()
        url_all = self.uri() + path_extra + '?' + urlencode(params)
        resp = requests.post(url_all, data)
        if resp.status_code != 200:
            raise ApiResponseError('HTTP call failed', resp)
        return resp.content

    def http_put(self, params, data=None, path_extra=''):
        self.wait_up()
        url_all = self.uri() + path_extra + '?' + urlencode(params)
        resp = requests.put(url_all, data)
        if resp.status_code != 200:
            raise ApiResponseError('HTTP call failed', resp)
        return resp.content

    def http_delete(self, path_extra=''):
        self.wait_up()
        resp = requests.delete(self.uri() + path_extra)
        if resp.status_code != 200:
            raise ApiResponseError('HTTP call failed', resp)
        return resp.content


# line = 'key=value', returns key, value
def env_var_split(line):
    ii = line.find('=')
    kk = line[:ii]
    vv = line[ii+1:]
    return kk, vv


class EnvAll(BaseApi):
    def __init__(self, vm):
        BaseApi.__init__(self, vm)
        self.base_path = '/env'

    # get all env vars
    def get(self):
        content = self.http_get('/')
        arr1 = ast.literal_eval(content)
        arr2 = {}
        for aa in arr1:
            kk, vv = env_var_split(aa)
            arr2[kk] = vv
        return arr2


class Env(BaseApi):
    def __init__(self, vm, name):
        BaseApi.__init__(self, vm)
        self.base_path = '/env/' + name
        self._name = name

    def get(self):
        content = self.http_get()
        # value only, enclosed in ""
        value = content.strip('"')
        return value

    def set(self, value):
        params = {'val': value}
        self.http_post(params)

    # delete return HTTP 200 even if no such var is set
    def delete(self):
        self.http_delete()


class App(BaseApi):
    # name - path to .so to run.
    def __init__(self, vm, name):
        BaseApi.__init__(self, vm)
        self.base_path = '/app/'
        self._name = name

    def run(self):
        assert(self._name)
        params = {'command': self._name}
        self.http_put(params)


##
