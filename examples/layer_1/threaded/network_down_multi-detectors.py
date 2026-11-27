# -*- coding: utf-8 -*-
"""
threaded.network_down_multi-detectors.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A fully-functional connection-observer using socket & threading.
Works on Python 3.10+

This example demonstrates multiple connection observers working
on multiple connections.
Shows following concepts:
- multiple observers may observe single connection
- each one is focused on different data (processing decomposition)
- client code may run observers on different connections
- client code may "start" observers in sequence
- external-IO-connection must be given Moler's connection for data forwarding
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

from network_toggle_observers import NetworkDownDetector, NetworkUpDetector


# ===================== Moler's connection-observer usage ======================


def ping_observing_task(address, ping_ip):
    logger = logging.getLogger('moler.user.app-code')
    net_addr = 'tcp://{}:{}'.format(*address)

    # Lowest layer of Moler's usage (you manually glue all elements):
    # 1. create observers
    net_down_detector = NetworkDownDetector(ping_ip)
    net_drop_found = False
    net_up_detector = NetworkUpDetector(ping_ip)
    moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"))
    # 2. virtually "start" observer by making it data-listener
    moler_conn.subscribe(net_down_detector.data_received)

    info = f'{ping_ip} on {net_addr} using {net_down_detector}'
    logger.debug(f"observe {info}")
    for _ in tcp_connection(address, moler_conn):
        # anytime new data comes it may change status of observer
        if not net_drop_found and net_down_detector.done():
            net_drop_found = True
            net_down_time = net_down_detector.result()
            timestamp = time.strftime("%H:%M:%S", time.localtime(net_down_time))
            logger.debug(f'Network {ping_ip} is down from {timestamp}')
            # 3. virtually "stop" that observer
            moler_conn.unsubscribe(net_down_detector.data_received)
            # 4. and start subsequent one (to know when net is back "up")
            info = f'{ping_ip} on {net_addr} using {net_up_detector}'
            logger.debug(f"observe {info}")
            moler_conn.subscribe(net_up_detector.data_received)
        if net_up_detector.done():
            net_up_time = net_up_detector.result()
            timestamp = time.strftime("%H:%M:%S", time.localtime(net_up_time))
            logger.debug(f'Network {ping_ip} is back "up" from {timestamp}')
            # 5. virtually "stop" that observer
            moler_conn.unsubscribe(net_up_detector.data_received)
            break


# ==============================================================================
def tcp_connection(address, moler_conn):
    """Forwarder reading from tcp network transport layer"""
    logger = logging.getLogger('threaded.tcp-connection({}:{})'.format(*address))
    logger.debug('... connecting to tcp://{}:{}'.format(*address))
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(address)

    with closing(client_socket):
        while True:
            data = client_socket.recv(128)
            if data:
                logger.debug(f'<<< {data!r}')
                # Forward received data into Moler's connection
                moler_conn.data_received(data)
                yield data
            else:
                logger.debug("... closed")
                break


def main(connections2observe4ip):
    # Starting the clients
    connections = []
    for address, ping_ip in connections2observe4ip:
        client_thread = threading.Thread(target=ping_observing_task,
                                         args=(address, ping_ip))
        client_thread.start()
        connections.append(client_thread)
    # await observers job to be done
    for client_thread in connections:
        client_thread.join()


# ==============================================================================
if __name__ == '__main__':
    from threaded_ping_server import start_ping_servers, stop_ping_servers

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s |%(name)-40s |%(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stderr,
    )
    connections2observe = [(('localhost', 5671), '10.0.2.15'),
                           (('localhost', 5672), '10.0.2.16')]
    servers = start_ping_servers(connections2observe)
    main(connections2observe)
    stop_ping_servers(servers)

'''
LOG OUTPUT

16:37:44 |threaded.ping.tcp-server(5671)           |Ping Sim started at tcp://localhost:5671
16:37:44 |threaded.ping.tcp-server(5672)           |Ping Sim started at tcp://localhost:5672
16:37:44 |moler.user.app-code                      |observe 10.0.2.15 on tcp://localhost:5671 using NetworkDownDetector(id:46109472)
16:37:44 |threaded.tcp-connection(localhost:5671)  |... connecting to tcp://localhost:5671
16:37:44 |moler.user.app-code                      |observe 10.0.2.16 on tcp://localhost:5672 using NetworkDownDetector(id:46184544)
16:37:44 |threaded.tcp-connection(localhost:5672)  |... connecting to tcp://localhost:5672
16:37:44 |threaded.ping.tcp-server(5671 -> 61044)  |connection accepted - client at tcp://127.0.0.1:61044
16:37:44 |threaded.tcp-connection(localhost:5671)  |<<< b'\n'
16:37:44 |threaded.ping.tcp-server(5672 -> 61045)  |connection accepted - client at tcp://127.0.0.1:61045
16:37:44 |threaded.tcp-connection(localhost:5672)  |<<< b'\n'
16:37:45 |threaded.tcp-connection(localhost:5671)  |<<< b'greg@debian:~$ ping 10.0.2.15\n'
16:37:45 |threaded.tcp-connection(localhost:5672)  |<<< b'greg@debian:~$ ping 10.0.2.16\n'
16:37:46 |threaded.tcp-connection(localhost:5671)  |<<< b'PING 10.0.2.15 (10.0.2.15) 56(84) bytes of data.\n'
16:37:46 |threaded.tcp-connection(localhost:5672)  |<<< b'PING 10.0.2.16 (10.0.2.16) 56(84) bytes of data.\n'
16:37:47 |threaded.tcp-connection(localhost:5671)  |<<< b'64 bytes from 10.0.2.15: icmp_req=1 ttl=64 time=0.080 ms\n'
16:37:47 |threaded.tcp-connection(localhost:5672)  |<<< b'64 bytes from 10.0.2.16: icmp_req=1 ttl=64 time=0.080 ms\n'
16:37:48 |threaded.tcp-connection(localhost:5671)  |<<< b'64 bytes from 10.0.2.15: icmp_req=2 ttl=64 time=0.037 ms\n'
16:37:48 |threaded.tcp-connection(localhost:5672)  |<<< b'64 bytes from 10.0.2.16: icmp_req=2 ttl=64 time=0.037 ms\n'
16:37:49 |threaded.tcp-connection(localhost:5671)  |<<< b'64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms\n'
16:37:49 |threaded.tcp-connection(localhost:5672)  |<<< b'64 bytes from 10.0.2.16: icmp_req=3 ttl=64 time=0.045 ms\n'
16:37:50 |threaded.tcp-connection(localhost:5671)  |<<< b'ping: sendmsg: Network is unreachable\n'
16:37:50 |moler.NetworkDownDetector(id:46109472)   |Network 10.0.2.15 is down!
16:37:50 |moler.user.app-code                      |Network 10.0.2.15 is down from 16:37:50
16:37:50 |moler.user.app-code                      |observe 10.0.2.15 on tcp://localhost:5671 using NetworkUpDetector(id:46110368)
16:37:50 |threaded.tcp-connection(localhost:5672)  |<<< b'ping: sendmsg: Network is unreachable\n'
16:37:50 |moler.NetworkDownDetector(id:46184544)   |Network 10.0.2.16 is down!
16:37:50 |moler.user.app-code                      |Network 10.0.2.16 is down from 16:37:50
16:37:50 |moler.user.app-code                      |observe 10.0.2.16 on tcp://localhost:5672 using NetworkUpDetector(id:46184488)
16:37:51 |threaded.tcp-connection(localhost:5671)  |<<< b'ping: sendmsg: Network is unreachable\n'
16:37:51 |threaded.tcp-connection(localhost:5672)  |<<< b'ping: sendmsg: Network is unreachable\n'
16:37:52 |threaded.tcp-connection(localhost:5671)  |<<< b'ping: sendmsg: Network is unreachable\n'
16:37:52 |threaded.tcp-connection(localhost:5672)  |<<< b'ping: sendmsg: Network is unreachable\n'
16:37:53 |threaded.tcp-connection(localhost:5671)  |<<< b'64 bytes from 10.0.2.15: icmp_req=7 ttl=64 time=0.123 ms\n'
16:37:53 |moler.NetworkUpDetector(id:46110368)     |Network 10.0.2.15 is up!
16:37:53 |moler.user.app-code                      |Network 10.0.2.15 is back "up" from 16:37:53
16:37:53 |threaded.tcp-connection(localhost:5672)  |<<< b'64 bytes from 10.0.2.16: icmp_req=7 ttl=64 time=0.123 ms\n'
16:37:53 |moler.NetworkUpDetector(id:46184488)     |Network 10.0.2.16 is up!
16:37:53 |moler.user.app-code                      |Network 10.0.2.16 is back "up" from 16:37:53
16:37:53 |threaded.ping.tcp-server(5671)           |Ping Sim: ... bye
16:37:53 |threaded.ping.tcp-server(5672)           |Ping Sim: ... bye
16:37:55 |threaded.ping.tcp-server(5671 -> 61044)  |Connection closed
16:37:55 |threaded.ping.tcp-server(5672 -> 61045)  |Connection closed
'''
