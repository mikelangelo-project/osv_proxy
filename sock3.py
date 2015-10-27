#!/usr/bin/env python

__author__ = 'justin_cinkelj'

import logging
import logging.config
import select
import socket
import sys
import Queue

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
        '''
        Listen at address addr, and next free port >= port0
        '''
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
            log.error('Multiple connection not allowed, from %s to %s', str(client_address), str(self.getsockname()))
            connection.close()
            return None, None
        self._connection = connection
        ServerSocket.map_connection[connection] = self
        return connection, client_address


def example():
    log = logging.getLogger(__name__)

    fobj = open('/tmp/stdout', 'w')
    rw_map = {}

    # Create a TCP/IP socket
    fobj = open('/tmp/stdout', 'w')
    server_out = ServerSocket('STDOUT', fobj)
    server_out.do_listen('localhost', 2300)

    # Sockets from which we expect to read
    inputs = [ server_out ]

    # Sockets to which we expect to write
    outputs = [ ]

    # Outgoing message queues (socket:Queue)
    message_queues = {}

    while inputs:

        # Wait for at least one of the sockets to be ready for processing
        log.debug('waiting for the next event')
        readable, writable, exceptional = select.select(inputs, outputs, inputs)

        # Handle inputs
        for s in readable:

            if s in [server_out]:
                # A "readable" server socket is ready to accept a connection
                connection, client_address = s.accept()
                #
                # Trigger 'TypeError: not all arguments converted during string formatting' to stdout/err
                # log.info('DO TRIGGER ERROR', 11, 22, 33)
                #
                if connection:
                    log.info('new connection from %s', client_address)
                    connection.setblocking(0)
                    inputs.append(connection)

                    # Give the connection a queue for data we want to send
                    message_queues[s._fobj] = Queue.Queue()
            elif s in [server_out._connection]:
                # opened client-server connection
                data = s.recv(1024)
                if data:
                    # A readable client socket has data
                    log.debug('received "%s" from %s', data.encode('string_escape'), s.getpeername())
                    fobj = ServerSocket.map_connection[s]._fobj
                    message_queues[fobj].put(data)
                    # Add output channel for response
                    if fobj not in outputs:
                        outputs.append(fobj)
                else:
                    # Interpret empty result as closed connection
                    log.info('closing %s after reading no data', client_address)
                    # Stop listening for input on the connection
                    if s in outputs:
                        outputs.remove(s)
                    inputs.remove(s)
                    s.close()
                    fobj = ServerSocket.map_connection[s]._fobj
                    ServerSocket.remove_connection(s)

                    # Remove message queue
                    del message_queues[fobj]
            # elif s in [server_in._fobj]:
        # Handle outputs
        for fobj in writable:
            try:
                next_msg = message_queues[fobj].get_nowait()
            except Queue.Empty:
                # No messages waiting so stop checking for writability.
                log.debug('output queue for %s is empty', fobj.name)
                outputs.remove(fobj)
            else:
                if fobj in [server_out._fobj]:
                    log.debug('sending "%s" to %s', next_msg.encode('string_escape'), fobj.name)
                    # s.send(next_msg)
                    fobj.write(next_msg)
                    fobj.flush()
                # elif fobj in [server_in._connection]:
        # Handle "exceptional conditions"
        for s in exceptional:
            log.info('handling exceptional condition for %s', s.getpeername())
            # Stop listening for input on the connection
            inputs.remove(s)
            if s in outputs:
                outputs.remove(s)
            s.close()

            # Remove message queue
            del message_queues[s]


def setup_logging():
    level = logging.INFO
    level = logging.DEBUG
    file = '/tmp/orted_lin_proxy.log'
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'verbose': {
#                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
                'format': '%(levelname) 8s %(asctime)s %(module)s %(thread)d %(message)s'
            },
            'simple': {
                'format': '%(levelname) 8s %(message)s'
            },
        },
        'handlers': {
            'console':{
                'level':'DEBUG',
                'class':'logging.NullHandler',
                'formatter': 'simple'
            },
            'file': {
                'level': 'DEBUG',
                'class': 'logging.FileHandler',
                'formatter': 'verbose',
                'filename': file,
            },
        },
        'loggers': {
            '': {
                'handlers':['file'],
                'propagate': False,
                'level':level,
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
