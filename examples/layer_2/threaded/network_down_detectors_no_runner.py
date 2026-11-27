# -*- coding: utf-8 -*-
"""
threaded.network_down_detectors_no_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A fully-functional connection-observer using socket & threading.
Works on Python 3.10+

This is Layer_2 (half of it) example:
uses Moler provided external-IO TCP implementation (moler.io.raw.tcp.ThradedTcp)
that integrates with Moler's connection

This example demonstrates multiple connection observers working
on multiple connections.

Shows following concepts:
- multiple observers may observe single connection
- each one is focused on different data (processing decomposition)
- client code may run observers on different connections
- client code may "start" observers in sequence
"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import logging
import sys
import os
import threading
import time

from moler.threaded_moler_connection import ThreadedMolerConnection
from moler.io.raw import tcp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # allow finding modules in examples/

from network_toggle_observers import NetworkDownDetector, NetworkUpDetector


# ===================== Moler's connection-observer usage ======================


def ping_observing_task(ext_io_connection, ping_ip):
    """
    Here external-IO connection is abstract - we don't know its type.
    What we know is just that it has .moler_connection attribute.
    """
    logger = logging.getLogger('moler.user.app-code')
    conn_addr = str(ext_io_connection)

    # Layer 2 of Moler's usage (ext_io_connection):
    # 1. create observers
    net_down_detector = NetworkDownDetector(ping_ip)
    net_drop_found = False
    net_up_detector = NetworkUpDetector(ping_ip)
    moler_conn = ext_io_connection.moler_connection
    # 2. virtually "start" observer by making it data-listener
    moler_conn.subscribe(net_down_detector.data_received)

    info = f'{ping_ip} on {conn_addr} using {net_down_detector}'
    logger.debug(f"observe {info}")

    with ext_io_connection.open():
        observing_timeout = 10
        start_time = time.monotonic()
        while time.monotonic() < start_time + observing_timeout:
            # anytime new data comes it may change status of observer
            if not net_drop_found and net_down_detector.done():
                net_drop_found = True
                net_down_time = net_down_detector.result()
                timestamp = time.strftime("%H:%M:%S", time.localtime(net_down_time))
                logger.debug(f'Network {ping_ip} is down from {timestamp}')
                # 3. virtually "stop" that observer
                moler_conn.unsubscribe(net_down_detector.data_received)
                # 4. and start subsequent one (to know when net is back "up")
                info = f'{ping_ip} on {conn_addr} using {net_up_detector}'
                logger.debug(f"observe {info}")
                moler_conn.subscribe(net_up_detector.data_received)
            if net_up_detector.done():
                net_up_time = net_up_detector.result()
                timestamp = time.strftime("%H:%M:%S", time.localtime(net_up_time))
                logger.debug(f'Network {ping_ip} is back "up" from {timestamp}')
                # 5. virtually "stop" that observer
                moler_conn.unsubscribe(net_up_detector.data_received)
                break
            time.sleep(0.2)


# ==============================================================================
def main(connections2observe4ip):
    # Starting the clients
    connections = []
    for address, ping_ip in connections2observe4ip:
        host, port = address
        # 1. create Moler's connection that knows encoding
        decoder = lambda data: data.decode("utf-8")
        moler_conn = ThreadedMolerConnection(decoder=decoder)
        # 2. create external-IO connection gluing to Moler's connection
        conn_logger_name = 'threaded.tcp-connection({}:{})'.format(*address)
        conn_logger = logging.getLogger(conn_logger_name)
        tcp_connection = tcp.ThreadedTcp(moler_connection=moler_conn,
                                         port=port, host=host,
                                         logger=conn_logger)
        client_thread = threading.Thread(target=ping_observing_task,
                                         args=(tcp_connection, ping_ip))
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
    connections2observe4ip = [(('localhost', 5671), '10.0.2.15'),
                              (('localhost', 5672), '10.0.2.16')]
    servers = start_ping_servers(connections2observe4ip)
    main(connections2observe4ip)
    stop_ping_servers(servers)

'''
LOG OUTPUT

12:06:50 |threaded.ping.tcp-server(5671)           |Ping Sim started at tcp://localhost:5671
12:06:50 |threaded.ping.tcp-server(5672)           |Ping Sim started at tcp://localhost:5672
12:06:50 |moler.user.app-code                      |observe 10.0.2.15 on tcp://localhost:5671 using NetworkDownDetector(id:46425312)
12:06:50 |moler.user.app-code                      |observe 10.0.2.16 on tcp://localhost:5672 using NetworkDownDetector(id:46425704)
12:06:50 |threaded.tcp-connection(localhost:5671)  |connecting to tcp://localhost:5671
12:06:50 |threaded.tcp-connection(localhost:5672)  |connecting to tcp://localhost:5672
12:06:50 |threaded.tcp-connection(localhost:5671)  |connection tcp://localhost:5671 is open
12:06:50 |threaded.ping.tcp-server(5671 -> 62735)  |connection accepted - client at tcp://127.0.0.1:62735
12:06:50 |threaded.tcp-connection(localhost:5672)  |connection tcp://localhost:5672 is open
12:06:50 |threaded.tcp-connection(localhost:5671)  |< b'\n'
12:06:50 |threaded.ping.tcp-server(5672 -> 62736)  |connection accepted - client at tcp://127.0.0.1:62736
12:06:50 |threaded.tcp-connection(localhost:5672)  |< b'\n'
12:06:51 |threaded.tcp-connection(localhost:5672)  |< b'greg@debian:~$ ping 10.0.2.16\n'
12:06:51 |threaded.tcp-connection(localhost:5671)  |< b'greg@debian:~$ ping 10.0.2.15\n'
12:06:52 |threaded.tcp-connection(localhost:5672)  |< b'PING 10.0.2.16 (10.0.2.16) 56(84) bytes of data.\n'
12:06:52 |threaded.tcp-connection(localhost:5671)  |< b'PING 10.0.2.15 (10.0.2.15) 56(84) bytes of data.\n'
12:06:53 |threaded.tcp-connection(localhost:5672)  |< b'64 bytes from 10.0.2.16: icmp_req=1 ttl=64 time=0.080 ms\n'
12:06:53 |threaded.tcp-connection(localhost:5671)  |< b'64 bytes from 10.0.2.15: icmp_req=1 ttl=64 time=0.080 ms\n'
12:06:54 |threaded.tcp-connection(localhost:5672)  |< b'64 bytes from 10.0.2.16: icmp_req=2 ttl=64 time=0.037 ms\n'
12:06:54 |threaded.tcp-connection(localhost:5671)  |< b'64 bytes from 10.0.2.15: icmp_req=2 ttl=64 time=0.037 ms\n'
12:06:55 |threaded.tcp-connection(localhost:5672)  |< b'64 bytes from 10.0.2.16: icmp_req=3 ttl=64 time=0.045 ms\n'
12:06:55 |threaded.tcp-connection(localhost:5671)  |< b'64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms\n'
12:06:56 |threaded.tcp-connection(localhost:5672)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:56 |moler.NetworkDownDetector(id:46425704)   |Network 10.0.2.16 is down!
12:06:56 |moler.user.app-code                      |Network 10.0.2.16 is down from 12:06:56
12:06:56 |moler.user.app-code                      |observe 10.0.2.16 on tcp://localhost:5672 using NetworkUpDetector(id:46426096)
12:06:56 |threaded.tcp-connection(localhost:5671)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:56 |moler.NetworkDownDetector(id:46425312)   |Network 10.0.2.15 is down!
12:06:56 |moler.user.app-code                      |Network 10.0.2.15 is down from 12:06:56
12:06:56 |moler.user.app-code                      |observe 10.0.2.15 on tcp://localhost:5671 using NetworkUpDetector(id:46425480)
12:06:57 |threaded.tcp-connection(localhost:5672)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:57 |threaded.tcp-connection(localhost:5671)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:58 |threaded.tcp-connection(localhost:5672)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:58 |threaded.tcp-connection(localhost:5671)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:59 |threaded.tcp-connection(localhost:5672)  |< b'64 bytes from 10.0.2.16: icmp_req=7 ttl=64 time=0.123 ms\n'
12:06:59 |moler.NetworkUpDetector(id:46426096)     |Network 10.0.2.16 is up!
12:06:59 |threaded.tcp-connection(localhost:5671)  |< b'64 bytes from 10.0.2.15: icmp_req=7 ttl=64 time=0.123 ms\n'
12:06:59 |moler.NetworkUpDetector(id:46425480)     |Network 10.0.2.15 is up!
12:06:59 |moler.user.app-code                      |Network 10.0.2.15 is back "up" from 12:06:59
12:06:59 |threaded.tcp-connection(localhost:5671)  |connection tcp://localhost:5671 is closed
12:06:59 |moler.user.app-code                      |Network 10.0.2.16 is back "up" from 12:06:59
12:06:59 |threaded.tcp-connection(localhost:5672)  |connection tcp://localhost:5672 is closed
12:07:00 |threaded.ping.tcp-server(5671)           |Ping Sim: ... bye
12:07:00 |threaded.ping.tcp-server(5672)           |Ping Sim: ... bye
12:07:01 |threaded.ping.tcp-server(5672 -> 62736)  |Connection closed
12:07:01 |threaded.ping.tcp-server(5671 -> 62735)  |Connection closed
'''
