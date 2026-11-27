# -*- coding: utf-8 -*-
"""
threaded.network_down_detector.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A fully-functional connection-observer using socket & threading.
Works on Python 3.10+

This example demonstrates basic concept of connection observer - entity
that is fully responsible for:
- observing data coming from connection till it catches what it is waiting for
- parsing that data to have "caught event" stored in expected form
- storing that result internally for later retrieval

Please note that this example is LAYER-1 usage which means:
- observer can't run by its own, must be fed with data (passive observer)
- observer can't be awaited, must be queried for status before asking for data
Another words - low level manual combining of all the pieces.
"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import logging
import socket
import sys
import os
import threading
import time
from contextlib import closing

from moler.threaded_moler_connection import ThreadedMolerConnection

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # allow finding modules in examples/

from network_toggle_observers import NetworkDownDetector


# ===================== Moler's connection-observer usage ======================


def ping_observing_task(address):
    logger = logging.getLogger('moler.user.app-code')

    # Lowest layer of Moler's usage (you manually glue all elements):
    # 1. create observer
    net_down_detector = NetworkDownDetector('10.0.2.15')
    # 2. ThreadedMolerConnection is a proxy-glue between observer (speaks str)
    #                                   and threaded-connection (speaks bytes)
    moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"))
    # 3a. glue from proxy to observer
    moler_conn.subscribe(net_down_detector.data_received)

    logger.debug('waiting for data to observe')
    for connection_data in tcp_connection(address):
        # 3b. glue to proxy from external-IO (threaded tcp client connection)
        #   (client code has to pass it's received data into Moler's connection)
        moler_conn.data_received(connection_data)
        # 4. Moler's client code must manually check status of observer ...
        if net_down_detector.done():
            # 5. ... to know when it can ask for result
            net_down_time = net_down_detector.result()
            timestamp = time.strftime("%H:%M:%S", time.localtime(net_down_time))
            logger.debug(f'Network is down from {timestamp}')
            break


# ==============================================================================
def tcp_connection(address):
    """Generator reading from tcp network transport layer"""
    logger = logging.getLogger('threaded.tcp-connection')
    logger.debug('... connecting to tcp://{}:{}'.format(*address))
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(address)

    with closing(client_socket):
        while True:
            data = client_socket.recv(128)
            if data:
                logger.debug(f'<<< {data!r}')
                yield data
            else:
                logger.debug("... closed")
                break


def main(address):
    # Starting the client
    client_thread = threading.Thread(target=ping_observing_task, args=(address,))
    client_thread.start()
    client_thread.join()


# ==============================================================================
if __name__ == '__main__':
    from threaded_ping_server import start_ping_servers, stop_ping_servers

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s |%(name)25s |%(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stderr,
    )
    local_address = ('localhost', 5670)
    servers = start_ping_servers([(local_address, '10.0.2.15')])
    main(local_address)
    stop_ping_servers(servers)

'''
LOG OUTPUT

16:58:04 | threaded.ping.tcp-server |Ping Sim started at tcp://localhost:5670
16:58:04 | threaded.ping.tcp-server |WARNING - I'll be tired too much just after first client!
16:58:04 |      moler.user.app-code |waiting for data to observe
16:58:04 |  threaded.tcp-connection |... connecting to tcp://localhost:5670
16:58:04 | threaded.ping.tcp-server |connection accepted - client at tcp://127.0.0.1:56582
16:58:04 |  threaded.tcp-connection |<<< b'\n'
16:58:05 |  threaded.tcp-connection |<<< b'greg@debian:~$ ping 10.0.2.15\n'
16:58:06 |  threaded.tcp-connection |<<< b'PING 10.0.2.15 (10.0.2.15) 56(84) bytes of data.\n'
16:58:07 |  threaded.tcp-connection |<<< b'64 bytes from 10.0.2.15: icmp_req=1 ttl=64 time=0.080 ms\n'
16:58:08 |  threaded.tcp-connection |<<< b'64 bytes from 10.0.2.15: icmp_req=2 ttl=64 time=0.037 ms\n'
16:58:09 |  threaded.tcp-connection |<<< b'64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms\n'
16:58:10 |  threaded.tcp-connection |<<< b'ping: sendmsg: Network is unreachable\n'
16:58:10 |  moler.net-down-detector |Network is down!
16:58:10 |      moler.user.app-code |Network is down from 16:58:10
16:58:10 | threaded.ping.tcp-server |Ping Sim: I'm tired after this client ... bye
16:58:12 | threaded.ping.tcp-server |Connection closed
'''
