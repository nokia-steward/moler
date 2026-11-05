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
import threading


def test_can_get_connection():
    from moler.connection_factory import get_connection
    tcp_connection = get_connection(io_type='tcp', variant='asyncio-in-thread', host='localhost', port=2345)
    assert tcp_connection is not None


@pytest.mark.xfail
def test_can_open_and_close_connection(tcp_connection_class,
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
    connection.open()
    connection.close()
    time.sleep(0.1)  # otherwise we have race between server's pipe and from-client-connection
    tcp_server_pipe.send(("get history", {}))
    dialog_with_server = tcp_server_pipe.recv()
    assert 'Client connected' in dialog_with_server
    assert 'Client disconnected' in dialog_with_server


@pytest.mark.xfail
def test_closing_closed_connection_does_nothing(tcp_connection_class,
                                                integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    connection.open()
    connection.close()
    connection.close()
    time.sleep(0.1)  # otherwise we have race between server's pipe and from-client-connection
    tcp_server_pipe.send(("get history", {}))
    dialog_with_server = tcp_server_pipe.recv()
    assert 'Client connected' in dialog_with_server
    assert 'Client disconnected' in dialog_with_server
    assert dialog_with_server[-2] != 'Client disconnected'  # not closed twice


@pytest.mark.xfail
def test_can_open_and_close_connection_as_context_manager(tcp_connection_class,
                                                          integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    with connection.open():
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
def test_can_send_binary_data_over_connection(tcp_connection_class,
                                              integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()  # no decoder, just pass bytes 1:1
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    with connection.open():
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
def test_can_receive_binary_data_from_connection(tcp_connection_class,
                                                 integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe
    received_data = bytearray()
    receiver_called = threading.Event()

    def receiver(data, time_recv):
        received_data.extend(data)
        receiver_called.set()

    def do_nothing_func():
        pass

    moler_conn = ThreadedMolerConnection()  # no decoder, just pass bytes 1:1
    moler_conn.subscribe(receiver, do_nothing_func)       # build forwarding path
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    with connection.open():  # TODO: async with connection.open():
        time.sleep(0.1)  # otherwise we have race between server's pipe and from-client-connection
        tcp_server_pipe.send(("send async msg", {'msg': b'data to read'}))
        receiver_called.wait(timeout=0.5)

    assert b'data to read' == received_data


@pytest.mark.xfail
def test_can_work_with_multiple_connections(tcp_connection_class,
                                            integration_tcp_server_and_pipe,
                                            integration_second_tcp_server_and_pipe):
    """Check open/close/send/receive on multiple connections"""
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server0, tcp_server0_pipe) = integration_tcp_server_and_pipe
    (tcp_server1, tcp_server1_pipe) = integration_second_tcp_server_and_pipe
    received_data = [bytearray(), bytearray()]
    receiver_called = [threading.Event(), threading.Event()]

    def receiver0(data, time_recv):
        received_data[0].extend(data)
        receiver_called[0].set()

    def receiver1(data, time_recv):
        received_data[1].extend(data)
        receiver_called[1].set()

    def do_nothig_func():
        pass

    moler_conn0 = ThreadedMolerConnection()
    moler_conn0.subscribe(receiver0, do_nothig_func)
    moler_conn1 = ThreadedMolerConnection()
    moler_conn1.subscribe(receiver1, do_nothig_func)
    connection0 = tcp_connection_class(moler_connection=moler_conn0, port=tcp_server0.port, host=tcp_server0.host)
    connection1 = tcp_connection_class(moler_connection=moler_conn1, port=tcp_server1.port, host=tcp_server1.host)
    with connection0.open():
        with connection1.open():
            time.sleep(0.1)  # to let servers notify connecting clients
            tcp_server0_pipe.send(("send async msg", {'msg': b'data from server 0'}))
            tcp_server1_pipe.send(("send async msg", {'msg': b'data from server 1'}))
            assert receiver_called[0].wait(timeout=0.5)
            assert receiver_called[1].wait(timeout=0.5)
            moler_conn0.send(data=b'data to server 0')
            moler_conn1.send(data=b'data to server 1')

    time.sleep(0.1)  # to let servers get what was sent
    # what we got from servers
    assert b'data from server 0' == received_data[0]
    assert b'data from server 1' == received_data[1]

    # what servers know about clients
    tcp_server0_pipe.send(("get history", {}))
    tcp_server1_pipe.send(("get history", {}))
    dialog_with_server0 = tcp_server0_pipe.recv()
    dialog_with_server1 = tcp_server1_pipe.recv()
    assert 'Client connected' == dialog_with_server0[0]
    assert 'Client connected' == dialog_with_server0[0]
    assert ['Received data:', b'data to server 0'] == dialog_with_server0[-2]
    assert ['Received data:', b'data to server 1'] == dialog_with_server1[-2]
    assert 'Client disconnected' == dialog_with_server0[-1]
    assert 'Client disconnected' == dialog_with_server1[-1]


# TODO: tests for error cases raising Exceptions


# --------------------------- test implementation -----------------
@pytest.mark.xfail
def test_asyncio_thread_has_running_thread_and_loop_after_start():
    from moler.asyncio_runner import AsyncioLoopThread

    thread4async = AsyncioLoopThread()
    thread4async.start()
    assert thread4async.is_alive()
    assert thread4async.ev_loop.is_running()


@pytest.mark.xfail
def test_asyncio_thread_has_stopped_thread_and_loop_after_join():
    from moler.asyncio_runner import AsyncioLoopThread

    thread4async = AsyncioLoopThread()
    thread4async.start()
    thread4async.join()
    assert not thread4async.ev_loop.is_running()
    assert not thread4async.is_alive()


@pytest.mark.xfail
def test_asyncio_thread_can_run_async_function():
    from moler.asyncio_runner import AsyncioLoopThread

    thread4async = AsyncioLoopThread()
    thread4async.start()

    async def my_coro(param):
        await asyncio.sleep(0.1)
        return f"called with param={param}"

    assert "called with param=2" == thread4async.run_async_coroutine(my_coro(param=2), timeout=0.2)


@pytest.mark.xfail
def test_asyncio_thread_can_timeout_async_function():
    from moler.asyncio_runner import AsyncioLoopThread
    from moler.exceptions import MolerTimeout

    thread4async = AsyncioLoopThread()
    thread4async.start()

    async def my_coro(param):
        await asyncio.sleep(0.2)
        return f"called with param={param}"

    with pytest.raises(MolerTimeout):
        thread4async.run_async_coroutine(my_coro(param=2), timeout=0.1)

# TODO - test cancel of async_function in asyncio_thread

# TODO - do we want thread4async.start_async_coroutine to let it run in background (returning future)


@pytest.mark.xfail
def test_can_get_same_asyncio_loop_thread():
    from moler.asyncio_runner import get_asyncio_loop_thread

    async_thrd_1 = get_asyncio_loop_thread()
    async_thrd_2 = get_asyncio_loop_thread()
    assert async_thrd_1 == async_thrd_2


@pytest.mark.xfail
def test_can_get_same_asyncio_loop_thread_even_from_different_calling_threads():
    from moler.asyncio_runner import get_asyncio_loop_thread
    async_thrds = [None, None, None]
    async_thrds[0] = get_asyncio_loop_thread()  # first one must be called from MainThread (unix signals issue)

    def call_from_thrd0():
        async_thrds[1] = get_asyncio_loop_thread()

    def call_from_thrd1():
        async_thrds[2] = get_asyncio_loop_thread()

    thrd0 = threading.Thread(target=call_from_thrd0)
    thrd1 = threading.Thread(target=call_from_thrd1)

    thrd0.start()
    thrd1.start()
    time.sleep(0.1)  # allow threads switch
    assert async_thrds[1] is not None
    assert async_thrds[0] is async_thrds[1]
    assert async_thrds[1] is async_thrds[2]


@pytest.mark.xfail
def test_get_asyncio_loop_thread_returns_running_thread_and_loop():
    from moler.asyncio_runner import get_asyncio_loop_thread

    async_thrd = get_asyncio_loop_thread()
    assert async_thrd.is_alive()
    assert async_thrd.ev_loop.is_running()


@pytest.mark.xfail
def test_connection_has_running_loop_after_open(tcp_connection_class,
                                                integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    connection.open()
    assert connection._async_tcp._stream_reader._loop.is_running()


@pytest.mark.xfail
def test_connection_has_not_stopped_loop_after_close(tcp_connection_class,
                                                     integration_tcp_server_and_pipe):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server, tcp_server_pipe) = integration_tcp_server_and_pipe

    moler_conn = ThreadedMolerConnection()
    connection = tcp_connection_class(moler_connection=moler_conn, port=tcp_server.port, host=tcp_server.host)
    connection.open()
    async_loop_of_connection = connection._async_tcp._stream_reader._loop
    connection.close()
    assert async_loop_of_connection.is_running()


@pytest.mark.xfail
def test_connections_use_same_loop(tcp_connection_class,
                                   integration_tcp_server_and_pipe,
                                   integration_second_tcp_server_and_pipe):
    # same loop means also same thread since asyncio has one loop in thread
    from moler.threaded_moler_connection import ThreadedMolerConnection
    (tcp_server0, tcp_server0_pipe) = integration_tcp_server_and_pipe
    (tcp_server1, tcp_server1_pipe) = integration_second_tcp_server_and_pipe

    connection0 = tcp_connection_class(moler_connection=ThreadedMolerConnection(),
                                       port=tcp_server0.port, host=tcp_server0.host)
    connection1 = tcp_connection_class(moler_connection=ThreadedMolerConnection(),
                                       port=tcp_server1.port, host=tcp_server1.host)
    with connection0.open():
        with connection1.open():
            # loop and thread appear after open()
            async_loop_of_connection0 = connection0._async_tcp._stream_reader._loop
            async_loop_of_connection1 = connection0._async_tcp._stream_reader._loop

            assert async_loop_of_connection0 == async_loop_of_connection1

# --------------------------- resources ---------------------------


@pytest.fixture(params=['io.asyncio.tcp.AsyncioInThreadTcp'])
def tcp_connection_class(request):
    module_name, class_name = request.param.rsplit('.', 1)
    module = importlib.import_module(f'moler.{module_name}')
    connection_class = getattr(module, class_name)
    return connection_class


@pytest.fixture()
def integration_tcp_server_and_pipe():
    from moler.io.raw.tcpserverpiped import tcp_server_piped
    with tcp_server_piped(port=19543, use_stderr_logger=True) as server_and_pipe:
        (server, svr_ctrl_pipe) = server_and_pipe
        yield (server, svr_ctrl_pipe)


@pytest.fixture()
def integration_second_tcp_server_and_pipe():
    from moler.io.raw.tcpserverpiped import tcp_server_piped
    with tcp_server_piped(port=19544, use_stderr_logger=True) as server_and_pipe:
        (server, svr_ctrl_pipe) = server_and_pipe
        yield (server, svr_ctrl_pipe)
