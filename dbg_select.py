#!/usr/bin/env python

__author__ = 'justin_cinkelj'

import logging
import logging.config
import select
import socket
import sys
import Queue
import time


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

delay = 3
delay_min = 3
# delay_max 0.1 - "0.0%" CPU usage, 0.01 - 0.3%, 0.001 - 2.3%, 0.0001 - 9.0%
delay_max = 3

def delay_inc():
    global delay
    delay *= 2
    delay = max(delay, delay_min)
    delay = min(delay, delay_max)

def delay_dec(new_delay = delay_min):
    global delay
    delay = new_delay
    # delay be 0, so there is no delay between read from fd0 and write to fd1
    # delay = max(delay, delay_min)
    delay = min(delay, delay_max)

def main():
    log = logging.getLogger(__name__)
    if 0:
        open('/tmp/stdin', 'w').close()
        fd0 = open('/tmp/stdin', 'r')
    else:
        fd0 = sys.__stdin__
        open('/tmp/stdin', 'w').close()  # remove old content
        fd_in = open('/tmp/stdin', 'r')
        sys.__stdin__ = None  # so that python doesn't use fd==0 as input
        sys.stdin = sys.__stdin__
        log.info('sys.stdin     %s', str(sys.stdin))
        log.info('sys.__stdin__ %s', str(sys.__stdin__))
    fd1 = open('/tmp/stdout', 'w')

    while 0:
        line = input()  # problem at file EOF
        print('LINE ' + line)
        if line == 'e':
            break
    while 0:
        line = fd0.read()  # works, but requires Ctrl+d at and of input, Enter is not enough
        print('LINE ' + line)
        if line in ['e', 'e\n']:
            break
    while 1:
        line = fd0.readline()  # works, flush is at enter
        print('LINE ' + line)
        if not line:
            # no input
            time.sleep(0.010)
        if line in ['e', 'e\n']:
            break

    inputs = [fd0]
    outputs = []
    message_queues = {}

    assert(fd1 not in message_queues)
    message_queues[fd1] = Queue.Queue()

    while inputs:
        # Wait for at least one of the sockets to be ready for processing
        # The file fd are 'ready' also on EOF - is that reason the file in descriptor is always ready?
        log.debug('waiting for the next event')
        readable, writable, exceptional = select.select(inputs, outputs, inputs)
        for s in readable:
            if s in [fd0]:
                log.info('data in %s', s.name)
                # assert(fd1 not in message_queues)
                # message_queues[fd1] = Queue.Queue()
                ## data = fd0.read() # blocks on stdin
                data = fd0.readline() # blocks on stdin
                log.info('data from %s (len=%d)', fd0.name, len(data))
                if data:
                    delay_dec(0)
                    log.info('copy data from %s to %s (len=%d)', fd0.name, fd1.name, len(data))
                    message_queues[fd1].put(data)
                    if fd1 not in outputs:
                        outputs.append(fd1)
                    # data is actualy written after one additional select(), in next while loop iteration
                # inputs.remove(fd0)  # otherwise select just returns there is something to read...
        for wr in writable:
            try:
                next_msg = message_queues[wr].get_nowait()
            except Queue.Empty:
                # No messages waiting so stop checking for writability.
                log.debug('output queue for %s is empty', obj_name(wr))
                outputs.remove(wr)
            else:
                if wr in [fd1]:
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

        #if writable:
        #    # fd1 might not be ready for a long time, and delay might be stuck at low value
        #    delay_dec()

        if delay:
            time.sleep(delay)
        delay_inc()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
