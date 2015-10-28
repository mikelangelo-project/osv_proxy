#!/usr/bin/env python

__author__ = 'justin_cinkelj'

import logging
import logging.config
import select
import socket
import sys
import Queue
import time

# https://pymotw.com/2/select/


class ServerSocket(socket.socket):
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
            except socket.error as ex:
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


def example():
    log = logging.getLogger(__name__)

    open('/tmp/stdin', 'w').close()  # touch file
    # buffering 0 = unbuffered, 1 = line buffered, more - approx buffer size in B
    fobj = open('/tmp/stdin', 'r', buffering=0)
    # fobj = sys.__stdin__
    server_in = ServerSocket('STDIN', fobj)
    server_in.do_listen('localhost', 2300)
    #
    fobj = open('/tmp/stdout', 'w')
    server_out = ServerSocket('STDOUT', fobj)
    server_out.do_listen('localhost', 2300)
    #
    fobj = open('/tmp/stderr', 'w')
    server_err = ServerSocket('STDERR', fobj)
    server_err.do_listen('localhost', 2300)

    # Sockets from which we expect to read
    inputs = [server_in, server_in._fobj, server_out, server_err]
    # include  server_in._fobj in inputs now, but read and forward data only once we also have client connection
    # on server_in listen socket

    # Sockets to which we expect to write
    outputs = []

    # Outgoing message queues (socket:Queue)
    message_queues = {}

    while inputs:

        # Wait for at least one of the sockets to be ready for processing
        log.debug('waiting for the next event')
        readable, writable, exceptional = select.select(inputs, outputs, inputs)

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
                    assert(s._fobj not in message_queues)
                    message_queues[s._fobj] = Queue.Queue()
                elif connection and s in [server_in]:
                    # we will only write to that connection
                    log.info('new "reverse" connection from %s', client_address)
                    connection.setblocking(0)
                    assert(connection not in message_queues)
                    message_queues[connection] = Queue.Queue()
            elif s in [server_out._connection, server_err._connection]:
                # opened client-server connection
                conn = s
                data = conn.recv(1024)
                if data:
                    # A readable client socket has data
                    log.debug('received "%s" from %s', data.encode('string_escape'), conn.getpeername())
                    fobj = ServerSocket.map_connection[conn]._fobj
                    message_queues[fobj].put(data)
                    # Add output channel for response
                    if fobj not in outputs:
                        outputs.append(fobj)
                else:
                    # Interpret empty result as closed connection
                    log.info('closing %s after reading no data', conn.getpeername())
                    # Stop listening for input on the connection
                    if conn in outputs:
                        outputs.remove(conn)
                    inputs.remove(conn)
                    conn.close()
                    fobj = ServerSocket.map_connection[conn]._fobj
                    ServerSocket.remove_connection(conn)

                    # Remove message queue
                    del message_queues[fobj]
            elif s in [server_in._fobj]:
                fobj = s
                conn = server_in._connection
                if conn:
                    data = fobj.read()
                    if data:
                        log.info('Read data from %s', fobj.name)
                        message_queues[conn].put(data)
                        if conn not in outputs:
                            outputs.append(conn)
            else:
                log.info('Unexpected readable %s', str(s))
                time.sleep(1)

        # Handle outputs
        for wr in writable:
            try:
                next_msg = message_queues[wr].get_nowait()
            except Queue.Empty:
                # No messages waiting so stop checking for writability.
                log.debug('output queue for %s is empty', obj_name(wr))
                outputs.remove(wr)
            else:
                if wr in [server_in._connection, server_out._fobj, server_err._fobj]:
                    log.debug('sending "%s" to %s', next_msg.encode('string_escape'), obj_name(wr))
                    obj_write(wr, next_msg)
                # elif fobj in [server_in._connection]:
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


def setup_logging():
    # level = logging.INFO
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
    example()
    # main2()
    logger.info('Done /*--------------------------------*/')
