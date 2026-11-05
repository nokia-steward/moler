# -*- coding: utf-8 -*-
"""
Testing external-IO TCP connection

- open/close
- send/receive (naming may differ)
"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2018, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import time
import importlib
import asyncio
import pytest


@pytest.mark.xfail
@pytest.mark.asyncio
async def test_can_open_and_close_connection(tcp_connection_class,
                                             integration_tcp_server_and_pipe):
    """
    Not so atomic test (checks 2 things) but:
    - it is integration tests
    - anyway open needs close as cleanup to not have resources leaking in tests
    """
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    await connection.open()
    await connection.close()
    time.sleep(0.1)  # otherwise we have race between server's pipe and from-client-connection
    tcp_server_pipe.send(("get history", {}))
    dialog_with_server = tcp_server_pipe.recv()
    assert 'Client connected' in dialog_with_server
    assert 'Client disconnected' in dialog_with_server


@pytest.mark.xfail
@pytest.mark.asyncio
async def test_closing_closed_connection_does_nothing(tcp_connection_class,
                                                      integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    await connection.open()
    await connection.close()
    await connection.close()
    time.sleep(0.1)  # otherwise we have race between server's pipe and from-client-connection
    tcp_server_pipe.send(("get history", {}))
    dialog_with_server = tcp_server_pipe.recv()
    assert 'Client connected' in dialog_with_server
    assert 'Client disconnected' in dialog_with_server
    assert  dialog_with_server[-2] != 'Client disconnected'  # not closed twice


@pytest.mark.xfail
@pytest.mark.asyncio
async def test_can_open_and_close_connection_as_context_manager(tcp_connection_class,
                                                                integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    async with connection:
        pass
    time.sleep(0.1)  # otherwise we have race between server's pipe and from-client-connection
    tcp_server_pipe.send(("get history", {}))
    dialog_with_server = tcp_server_pipe.recv()
    assert 'Client connected' in dialog_with_server
    assert 'Client disconnected' in dialog_with_server


# Note: different external-IO connection may have different naming for their 'send' method
# however, they are uniformed via glueing with moler_connection.send()
# external-IO 'send' method works on bytes; moler_connection performs encoding
@pytest.mark.xfail
@pytest.mark.asyncio
async def test_can_send_binary_data_over_connection(tcp_connection_class,
                                                    integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()  # no decoder, just pass bytes 1:1
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    async with connection:
        moler_conn.send(data=b'data to be send')  # TODO: await moler_conn.send(data=b'data to be send') ???
        time.sleep(0.1)  # otherwise we have race between server's pipe and from-client-connection
        tcp_server_pipe.send(("get history", {}))
        dialog_with_server = tcp_server_pipe.recv()
        assert ['Received data:', b'data to be send'] == dialog_with_server[-1]


# TODO: shell we check that after moler_conn.send() all data is already transmitted?
#       or should we allow for "schedule for sending"

# Note: different external-IO connection may have different naming for their 'receive' method
# however, they are uniformed via glueing with moler_connection.data_received()
# so, external-IO forwards data to moler_connection.data_received()
# and moler-connection forwards it to anyone subscribed
@pytest.mark.xfail
@pytest.mark.asyncio
async def test_can_receive_binary_data_from_connection(tcp_connection_class,
                                                       integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe
    received_data = bytearray()
    receiver_called = asyncio.Event()

    def receiver(data, time_recv):
        received_data.extend(data)
        receiver_called.set()

    moler_conn = ThreadedMolerConnection()  # no decoder, just pass bytes 1:1
    moler_conn.subscribe(receiver)       # build forwarding path
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    async with connection:  # TODO: async with connection.open():
        time.sleep(0.1)  # otherwise we have race between server's pipe and from-client-connection
        tcp_server_pipe.send(("send async msg", {'msg': b'data to read'}))
        await asyncio.wait_for(receiver_called.wait(), timeout=0.5)

    assert b'data to read' == received_data


# TODO: tests for error cases raising Exceptions

# --------------------------- resources ---------------------------


@pytest.fixture(params=['io.asyncio.tcp.AsyncioTcp'])
def tcp_connection_class(request):
    module_name, class_name = request.param.rsplit('.', 1)
    module = importlib.import_module(f'moler.{module_name}')
    connection_class = getattr(module, class_name)
    return connection_class


@pytest.fixture()
def integration_tcp_server_and_pipe():
    from moler.io.raw.tcpserverpiped import tcp_server_piped
    with tcp_server_piped(use_stderr_logger=False) as server_and_pipe:
        (server, svr_ctrl_pipe) = server_and_pipe
        yield (server, svr_ctrl_pipe)
