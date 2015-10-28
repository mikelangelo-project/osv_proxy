#!/usr/bin/env python

import sys
import os
# import subprocess32 as subprocess
import logging
import logging.config
import requests
import socket
import select
# from thread import start_new_thread
from time import sleep
from os import environ
from traceback import print_exc
from osv import VM, Env
import Queue


OSV_IP = '192.168.122.37'
OSV_IP_MASK = OSV_IP + '/24'
# OSV_NETMASK = '255.255.255.0'
OSV_GW = '192.168.122.1'
OSV_NS = '192.168.122.1'

SOCK_PORT_0 = 2300
SOCK_LISTEN_ADDR = '0.0.0.0'


'''
Copy all environment variables of current process to OSv container.
'''
def copy_all_env():
    log = logging.getLogger(__name__)
    url = 'http://%s:8000' % OSV_IP
    for name in environ.keys():
        value = str(environ.get(name))
        #print 'Env %s = %s' % (name, value)
        log.info('Env %s = %s', name, value)
        r = requests.post(url + '/env/' + name, data = {'val': value})


def get_orted_param():
    log = logging.getLogger(__name__)
    param = ''
    my_program_name_found = False
    for pp in sys.argv:
        # skip extra params added by ssh, up to the orted_proxy.py program name
        if my_program_name_found:
            param += '"%s" ' % (pp)
        else:
            log.debug('Skip param %s', pp)
            if pp.find('orted_lin_proxy.py') >= 0:
                my_program_name_found = True


def obj_name(obj):
    """
    obj can be socket.socket connection, or file object.
    Return descriptive name for socket or file.
    """
    if isinstance(obj, file):
        return obj.name
    elif isinstance(obj, socket.socket):
        return str(obj.getsockname())


def obj_write(obj, data):
    if isinstance(obj, file):
        obj.write(data)
        obj.flush()
    elif isinstance(obj, socket.socket):
        obj.send(data)


class Delay:
    def __init__(self, _min=0.0001, _max=0.1):
        # delay_max 0.1 - "0.0%" CPU usage, 0.01 - 0.3%, 0.001 - 2.3%, 0.0001 - 9.0%
        self.min = _min
        self.max = _max
        self.value = _min

    def inc(self):
        self.value *= 2
        self.value = max(self.value, self.min)
        self.value = min(self.value, self.max)

    def dec(self, new_delay=0.0001):
        self.value = new_delay
        # delay be 0, so there is no delay between read from fd0 and write to fd1
        # delay = max(delay, delay_min)
        self.value = min(self.value, self.max)

    def sleep(self):
        if self.value:
            sleep(self.value)


class ServerSocket(socket.socket):
    """
    A small utilty class to group common create/bind/listen/accpet socket sequence.
    For less code in proxy_loop()
    """
    # As self cannot be added to acceptd connection (it's socket.socket), save that info in the map_connection
    map_connection = {}

    @classmethod
    def remove_connection(cls, conn):
        parent_server = ServerSocket.map_connection.pop(conn)
        parent_server._connection = None

    def __init__(self, log_prefix='', fobj=None):
        super(ServerSocket, self).__init__(socket.AF_INET, socket.SOCK_STREAM)
        self._log_prefix = log_prefix
        self._fobj = fobj
        self._connection = None  # a single connection to/from fobj is allowed

    @property
    def fobj(self):
        return self._fobj

    @fobj.setter
    def fobj(self, val):
        self._fobj = val

    @property
    def connection(self):
        return self._connection

    @connection.setter
    def connection(self, val):
        self._connection = val

    def do_listen(self, addr, port0):
        """
        Listen at address addr, and next free port >= port0
        """
        log = logging.getLogger(__name__)
        port = port0
        while port < 2**16:
            try:
                self.setblocking(5)
                self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.bind((addr, port))
                self.listen(1)
                log.info('%s Listen on %s:%d - OK %s', self._log_prefix, addr, port, str(self))
                return True
            except socket.error:
                log.debug('%s Listen on %s:%d - failed', self._log_prefix, addr, port)
                # log.exception('asdf', ex)
                port += 1
                pass
        return False

    def accept(self):
        log = logging.getLogger(__name__)
        connection, client_address = super(ServerSocket, self).accept()
        if self._connection:
            log.error('%s Multiple connection not allowed, from %s to %s',
                      self._log_prefix, str(client_address), str(self.getsockname()))
            connection.close()
            return None, None
        self._connection = connection
        ServerSocket.map_connection[connection] = self
        return connection, client_address


class Proxy:
    def __init__(self):
        # sockets to get IO from mpi_program.so in OSv, and put data to our parent orted.
        self.server_in = None
        self.server_out = None
        self.server_err = None

    def redirect_stdio(self):
        log = logging.getLogger(__name__)

        fobj = sys.__stdin__
        sys.__stdin__ = None
        sys.stdin = sys.__stdin__
        server_in = ServerSocket('STDIN', fobj)
        server_in.do_listen('localhost', 2300)
        self.server_in = server_in
        #
        fobj = sys.__stdout__
        sys.__stdout__ = open('/tmp/stdout', 'w')
        sys.stdout = sys.__stdout__
        server_out = ServerSocket('STDOUT', fobj)
        server_out.do_listen('localhost', 2300)
        self.server_out = server_out
        #
        fobj = sys.__stderr__
        sys.__stderr__ = open('/tmp/stderr', 'w')
        sys.stderr = sys.__stderr__
        server_err = ServerSocket('STDERR', fobj)
        server_err.do_listen('localhost', 2300)
        self.server_err = server_err

    def proxy_loop(self):
        """
        proxy_loop sits between usual linux orted and mpi_program.so.
        proxy_loop is run by orted (fork+execve).
        proxy_loop spins up a new OSv container, in OSv container runs a osv_prosy.so, and osv_proxy.so will run
        mpi_program.so.

        orted expects mpi_program to:
          use MPI_* env variables.
          mpi_program stdin/out/err are captured by orted, as orted already redirects them to new file descriptors before
           exec.

        proxy_loop will replace its stdin/out/err with sockets, then it runs osv_proxy.so,
        with environmnet variables set so that osv_proxy knows where are magic sockets.
        Osv_proxy then replaces its stdin/out/err with connections to sockets, and then it starts mpi_program.so (as a
        thread).
        """
        log = logging.getLogger(__name__)
        delay = Delay()
        server_in = self.server_in
        server_out = self.server_out
        server_err = self.server_err

        # Sockets from which we expect to read
        inputs = [server_in, server_in.fobj, server_out, server_err]
        # include  server_in.fobj in inputs now, but read and forward data only once we also have client connection
        # on server_in listen socket

        # Sockets to which we expect to write
        outputs = []

        # Outgoing message queues (socket:Queue)
        message_queues = {}

        while inputs:

            # Wait for at least one of the sockets to be ready for processing
            log.debug('waiting for the next event')
            readable, writable, exceptional = select.select(inputs, outputs, inputs)
            # print 'print in python prog'  # should go to file, not to screen/pty

            # Handle inputs
            for s in readable:

                if s in [server_in, server_out, server_err]:
                    # A "readable" server socket is ready to accept a connection
                    connection, client_address = s.accept()
                    #
                    # Trigger 'TypeError: not all arguments converted during string formatting' to stdout/err
                    # log.info('DO TRIGGER ERROR', 11, 22, 33)
                    #
                    if connection and s in [server_out, server_err]:
                        log.info('new connection from %s', client_address)
                        connection.setblocking(0)
                        assert(connection not in inputs)
                        inputs.append(connection)
                        # Give the connection a queue for data we want to send
                        assert(s.fobj not in message_queues)
                        message_queues[s.fobj] = Queue.Queue()
                        delay.dec(0)
                    elif connection and s in [server_in]:
                        # we will only write to that connection
                        log.info('new "reverse" connection from %s', client_address)
                        connection.setblocking(0)
                        assert(connection not in message_queues)
                        message_queues[connection] = Queue.Queue()
                        # only to detect that connection was closed by peer
                        assert(connection not in inputs)
                        inputs.append(connection)
                        delay.dec(0)
                elif s in [server_out.connection, server_err.connection]:
                    # opened client-server connection
                    conn = s
                    data = conn.recv(1024)
                    if data:
                        # A readable client socket has data
                        log.debug('received "%s" from %s', data.encode('string_escape'), conn.getpeername())
                        fobj = ServerSocket.map_connection[conn].fobj
                        message_queues[fobj].put(data)
                        # Add output channel for response
                        if fobj not in outputs:
                            outputs.append(fobj)
                        delay.dec(0)
                    else:
                        # Interpret empty result as closed connection
                        log.info('closing %s after reading no data', conn.getpeername())
                        # Stop listening for input on the connection
                        if conn in outputs:
                            outputs.remove(conn)
                        inputs.remove(conn)
                        conn.close()
                        fobj = ServerSocket.map_connection[conn].fobj
                        ServerSocket.remove_connection(conn)
                        # Remove message queue
                        del message_queues[fobj]
                        delay.dec(0)
                elif s in [server_in.connection]:
                    # only to detect that peer closed connection
                    conn = s
                    data = conn.recv(1024)
                    if data:
                        log.warning('data recv in stdin output sock %s, ignore', conn.getpeername())
                    else:
                        # Interpret empty result as closed connection
                        log.info('closing stdin output sock %s', conn.getpeername())
                        inputs.remove(conn)
                        conn.close()
                        ServerSocket.remove_connection(conn)
                        del message_queues[conn]
                        delay.dec(0)
                elif s in [server_in.fobj]:
                    fobj = s
                    conn = server_in.connection
                    if conn:
                        data = fobj.readline()  # stdin.readline() returns at ENTER, while read() at Ctrl+D
                        if data:
                            log.info('Read data from %s', fobj.name)
                            message_queues[conn].put(data)
                            if conn not in outputs:
                                outputs.append(conn)
                            delay.dec(0)
                else:
                    log.info('Unexpected readable %s', str(s))
                    sleep(1)

            # Handle outputs
            for wr in writable:
                try:
                    next_msg = message_queues[wr].get_nowait()
                except Queue.Empty:
                    # No messages waiting so stop checking for writability.
                    log.debug('output queue for %s is empty', obj_name(wr))
                    outputs.remove(wr)
                else:
                    if wr in [server_in.connection, server_out.fobj, server_err.fobj]:
                        log.debug('sending "%s" to %s', next_msg.encode('string_escape'), obj_name(wr))
                        obj_write(wr, next_msg)
                    # elif fobj in [server_in.connection]:
            # Handle "exceptional conditions"
            for s in exceptional:
                # TODO ...
                log.info('handling exceptional condition for %s', s.getpeername())
                # Stop listening for input on the connection
                inputs.remove(s)
                if s in outputs:
                    outputs.remove(s)
                s.close()

                # Remove message queue
                del message_queues[s]

            delay.sleep()
            delay.inc()


def main():
    log = logging.getLogger(__name__)
    proxy = Proxy()
    #
    # run new VM
    # unsafe-cache for NFS mount
    vm = VM(debug=True, extra='--unsafe-cache')
    vm.run()

    proxy.redirect_stdio()
    # TCP sockets are listening now, vm can run the osv_proxy.so and mpi_program.so.

    # vm.env().set()
    vm.app('libhttpserver.so').run()
    # mpi_program = '/usr/lib/mpi_hello.so'
    # vm.app('/usr/lib/osv_proxy.so ' + mpi_program).run()

    # start forwarding socket <-> std IO data
    proxy.proxy_loop()


def setup_logging():
    level = logging.DEBUG
    logfile = '/tmp/orted_lin_proxy.log'
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
                'filename': logfile,
            },
        },
        'loggers': {
            '': {
                'handlers': ['file'],
                'propagate': False,
                'level': level,
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
