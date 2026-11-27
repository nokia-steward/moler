# -*- coding: utf-8 -*-
"""
twisted.network_down_detector.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A fully-functional connection-observer using twisted.
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
import sys
import os
import time
from functools import partial

from moler.threaded_moler_connection import ThreadedMolerConnection
from twisted.internet import reactor, task
from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol, ClientFactory

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # allow finding modules in examples/

from network_toggle_observers import NetworkDownDetector

# ===================== Moler's connection-observer usage ======================


def ping_observing_task(address):
    logger = logging.getLogger('moler.user.app-code')
    observer_done = Deferred()

    # Lowest layer of Moler's usage (you manually glue all elements):
    # 1. create observer
    net_down_detector = NetworkDownDetector('10.0.2.15')
    # 2. ThreadedMolerConnection is a proxy-glue between observer (speaks str)
    #                                   and twisted-connection (speaks bytes)
    moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"))
    # 3a. glue from proxy to observer
    moler_conn.subscribe(net_down_detector.data_received)

    logger.debug('waiting for data to observe')

    def feed_moler(connection_data):
        # 3b. glue to proxy from external-IO (twisted tcp client connection)
        #    (client has to pass it's received data into Moler's connection)
        moler_conn.data_received(connection_data)
        # 4. Moler's client code must manually check status of observer ...
        if net_down_detector.done():
            # 5. ... to know when it can ask for result
            net_down_time = net_down_detector.result()
            timestamp = time.strftime("%H:%M:%S",
                                      time.localtime(net_down_time))
            logger.debug(f'Network is down from {timestamp}')
            observer_done.callback(None)  # break tcp client and server

    start_tcp_connection(address, feed_moler)
    return observer_done


# ==============================================================================
class TcpConnection(Protocol):
    def __init__(self, forward_data):
        self.forward_data = forward_data
        self.logger = logging.getLogger('twisted.tcp-connection')

    def connectionMade(self):
        conn_info = 'tcp://{}:{}'.format(*self.transport.realAddress)
        self.logger.debug(f"... connected to {conn_info}")

    def connectionLost(self, reason):
        self.logger.debug("... closed")

    def dataReceived(self, data):
        self.logger.debug(f'<<< {data!r}')
        self.forward_data(data)


def start_tcp_connection(address, forward_data):
    host, port = address
    factory = ClientFactory()
    factory.protocol=partial(TcpConnection, forward_data)
    reactor.connectTCP(host, port, factory)


def main(reactor, address):
    # Starting the client
    processing_done_deferred = ping_observing_task(address)
    return processing_done_deferred


# ==============================================================================
if __name__ == '__main__':
    from threaded_ping_server import start_ping_servers, stop_ping_servers

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s |%(name)40s |%(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stderr,
    )
    address = ('localhost', 5670)
    servers = start_ping_servers([(address, '10.0.2.15')])
    try:
        task.react(main, argv=[address])
    finally:
        stop_ping_servers(servers)

'''
LOG OUTPUT

10:53:39 |         threaded.ping.tcp-server(5670) |Ping Sim started at tcp://localhost:5670
10:53:39 |               moler.runner.thread-pool |created
10:53:39 |               moler.runner.thread-pool |created own executor <concurrent.futures.thread.ThreadPoolExecutor object at 0x7fde953e93c8>
10:53:39 |                    moler.user.app-code |waiting for data to observe
10:53:39 |                 twisted.tcp-connection |... connected to tcp://127.0.0.1:5670
10:53:39 |threaded.ping.tcp-server(5670 -> 35996) |connection accepted - client at tcp://127.0.0.1:35996
10:53:39 |                 twisted.tcp-connection |<<< b'\n'
10:53:39 |                     moler.7fde953e95c0 |
10:53:40 |                 twisted.tcp-connection |<<< b'greg@debian:~$ ping 10.0.2.15\n'
10:53:40 |                     moler.7fde953e95c0 |greg@debian:~$ ping 10.0.2.15
10:53:41 |                 twisted.tcp-connection |<<< b'PING 10.0.2.15 (10.0.2.15) 56(84) bytes of data.\n'
10:53:41 |                     moler.7fde953e95c0 |PING 10.0.2.15 (10.0.2.15) 56(84) bytes of data.
10:53:42 |                 twisted.tcp-connection |<<< b'64 bytes from 10.0.2.15: icmp_req=1 ttl=64 time=0.080 ms\n'
10:53:42 |                     moler.7fde953e95c0 |64 bytes from 10.0.2.15: icmp_req=1 ttl=64 time=0.080 ms
10:53:43 |                 twisted.tcp-connection |<<< b'64 bytes from 10.0.2.15: icmp_req=2 ttl=64 time=0.037 ms\n'
10:53:43 |                     moler.7fde953e95c0 |64 bytes from 10.0.2.15: icmp_req=2 ttl=64 time=0.037 ms
10:53:44 |                 twisted.tcp-connection |<<< b'64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms\n'
10:53:44 |                     moler.7fde953e95c0 |64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms
10:53:45 |                 twisted.tcp-connection |<<< b'ping: sendmsg: Network is unreachable\n'
10:53:45 |                     moler.7fde953e95c0 |ping: sendmsg: Network is unreachable
10:53:45 |                moler.net-down-detector |Network is down!
10:53:45 |                    moler.user.app-code |Network is down from 10:53:45
10:53:45 |                 twisted.tcp-connection |... closed
10:53:45 |         threaded.ping.tcp-server(5670) |Ping Sim: ... bye
10:53:47 |threaded.ping.tcp-server(5670 -> 35996) |Connection closed
10:53:47 |               moler.runner.thread-pool |shutting down
'''
