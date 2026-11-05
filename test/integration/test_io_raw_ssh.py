# -*- coding: utf-8 -*-
"""
Testing external-IO SSH connection

- open/close
- send/receive (naming may differ)
"""

__author__ = 'Grzegorz Latuszek, Marcin Usielski'
__copyright__ = 'Copyright (C) 2020-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com'


import time
import importlib
import pytest
import mock
import threading
import platform


pytestmark = pytest.mark.skipif(
    "Linux" != platform.system(),
    reason="Linux-only SSH PTY integration tests.",
)


def test_can_create_passive_sshshell_connection_using_same_api(passive_sshshell_connection_class):
    # sshshell active and passive connections differ in API.
    # but we want to have all connections of class 'passive sshshell' to have same API

    connection = passive_sshshell_connection_class(host='localhost', port=22,
                                                   username='molerssh', password='moler_password')
    assert connection._ssh_transport is None
    assert connection._shell_channel is None
    assert hasattr(connection, "receive")

    # API allows to use "login" as alias for "username" parameter (to keep parity with ssh command / OpenSSH)
    connection1 = passive_sshshell_connection_class(host='localhost', port=22,
                                                    login='molerssh', password='moler_password')
    assert connection1._ssh_transport is None
    assert connection1._shell_channel is None
    assert hasattr(connection1, "receive")
    assert connection1.username == 'molerssh'

    # but you shouldn't use both names, we can't guess which one you wanted
    with pytest.raises(KeyError) as err:
        passive_sshshell_connection_class(host='localhost', port=22,
                                          username='molerssh1', login='molerssh2', password='moler_password')
    assert "Use either 'username' (molerssh1) or 'login' (molerssh2), not both" in str(err.value)


def test_can_create_active_sshshell_connection_using_same_api(active_sshshell_connection_class):
    # we want to have all connections of class 'active sshshell' to share same API

    from moler.threaded_moler_connection import ThreadedMolerConnection

    moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                         encoder=lambda data: data.encode("utf-8"))

    connection = active_sshshell_connection_class(moler_connection=moler_conn,
                                                  host='localhost', port=22,
                                                  username='molerssh', password='moler_password')
    assert connection._ssh_transport is None
    assert connection._shell_channel is None
    assert hasattr(connection, "data_received")

    # API allows to use "login" as alias for "username" parameter (to keep parity with ssh command / OpenSSH)
    connection1 = active_sshshell_connection_class(moler_connection=moler_conn,
                                                   host='localhost', port=22,
                                                   login='molerssh', password='moler_password')
    assert connection1._ssh_transport is None
    assert connection1._shell_channel is None
    assert hasattr(connection1, "data_received")
    assert connection1.sshshell.username == 'molerssh'

    # but you shouldn't use both names, we can't guess which one you wanted
    with pytest.raises(KeyError) as err:
        active_sshshell_connection_class(moler_connection=moler_conn, host='localhost', port=22,
                                         username='molerssh1', login='molerssh2', password='moler_password')
    assert "Use either 'username' (molerssh1) or 'login' (molerssh2), not both" in str(err.value)


def test_can_open_and_close_connection(sshshell_connection):
    """
    Not so atomic test (checks 2 things) but:
    - it is integration tests
    - anyway open needs close as cleanup to not have resources leaking in tests
    """
    connection = sshshell_connection

    connection.open()
    assert connection._ssh_transport is not None
    assert connection._shell_channel is not None
    assert connection._ssh_transport == connection._shell_channel.get_transport()
    assert connection._ssh_transport.is_active()
    assert connection._ssh_transport.is_authenticated()

    connection.close()
    assert connection._shell_channel is None
    assert connection._ssh_transport is None


def test_can_open_and_close_connection_as_context_manager(sshshell_connection):

    connection = sshshell_connection
    with connection.open():
        assert connection._ssh_transport.is_authenticated()
        assert connection._shell_channel is not None
    assert connection._ssh_transport is None
    assert connection._shell_channel is None

    with connection:
        assert connection._ssh_transport.is_authenticated()
        assert connection._shell_channel is not None
    assert connection._ssh_transport is None
    assert connection._shell_channel is None


def test_passive_connection_created_from_existing_open_connection_reuses_its_transport(passive_sshshell_connection_class):

    source_connection = passive_sshshell_connection_class(host='localhost', port=22,
                                                          username='molerssh', password='moler_password')
    with source_connection.open():
        source_transport = source_connection._ssh_transport
        # no host, port, username, password since we want to create another connection to new shell
        # towards same host/port using same credentials
        new_connection = passive_sshshell_connection_class.from_sshshell(sshshell=source_connection)

        assert source_transport is new_connection._ssh_transport

        assert new_connection._ssh_transport.is_authenticated()  # new one is authenticated
        assert new_connection._shell_channel is None  # but not open yet (no shell on remote)
        with new_connection.open():
            assert new_connection._shell_channel is not None
            assert source_transport is new_connection._ssh_transport  # no change after open()


def test_passive_connection_created_from_existing_nonopen_connection_will_share_same_transport(passive_sshshell_connection_class):

    source_connection = passive_sshshell_connection_class(host='localhost', port=22,
                                                          username='molerssh', password='moler_password')
    assert source_connection._ssh_transport is None
    new_connection = passive_sshshell_connection_class.from_sshshell(sshshell=source_connection)
    with source_connection.open():
        source_transport = source_connection._ssh_transport

        assert source_transport is new_connection._ssh_transport

        assert new_connection._ssh_transport.is_authenticated()  # new one is authenticated
        assert new_connection._shell_channel is None  # but not open yet (no shell on remote)
        with new_connection.open():
            assert new_connection._shell_channel is not None
            assert source_transport is new_connection._ssh_transport  # no change after open()


def test_active_connection_created_from_existing_open_connection_reuses_its_transport(active_sshshell_connection_class):
    from moler.threaded_moler_connection import ThreadedMolerConnection

    moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                         encoder=lambda data: data.encode("utf-8"))
    another_moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                                 encoder=lambda data: data.encode("utf-8"))

    source_connection = active_sshshell_connection_class(moler_connection=moler_conn,
                                                         host='localhost', port=22,
                                                         username='molerssh', password='moler_password')
    with source_connection.open():
        source_transport = source_connection._ssh_transport

        # no host, port, username, password since we want to create another connection to new shell
        # towards same host/port using same credentials
        ##################################################################################
        # CAUTION: they should not share same moler connection (hoever, it is not blocked)
        #          If they do you should be aware what you are doing
        #          You are multiplexing io-streams into single moler-connection
        ##################################################################################
        new_connection = active_sshshell_connection_class.from_sshshell(sshshell=source_connection,
                                                                        moler_connection=another_moler_conn)

        assert source_transport is new_connection._ssh_transport

        assert new_connection._ssh_transport.is_authenticated()  # new one is authenticated
        assert new_connection._shell_channel is None  # but not open yet (no shell on remote)
        with new_connection.open():
            assert new_connection._shell_channel is not None
            assert source_transport is new_connection._ssh_transport  # no change after open()


def test_active_connection_created_from_existing_nonopen_connection_will_share_same_transport(sshshell_connection,
                                                                                              active_sshshell_connection_class):
    from moler.threaded_moler_connection import ThreadedMolerConnection

    new_moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                             encoder=lambda data: data.encode("utf-8"))

    source_connection = sshshell_connection  # source might be either passive or active
    assert source_connection._ssh_transport is None
    new_connection = active_sshshell_connection_class.from_sshshell(sshshell=source_connection,
                                                                    moler_connection=new_moler_conn)
    with source_connection.open():
        source_transport = source_connection._ssh_transport

        assert source_transport is new_connection._ssh_transport

        assert new_connection._ssh_transport.is_authenticated()  # new one is authenticated
        assert new_connection._shell_channel is None  # but not open yet (no shell on remote)
        with new_connection.open():
            assert new_connection._shell_channel is not None
            assert source_transport is new_connection._ssh_transport  # no change after open()


def test_logging_for_open_close_of_passive_connection(passive_sshshell_connection_class, mocked_logger):
    logger = mocked_logger
    connection = passive_sshshell_connection_class(host='localhost', port=22,
                                                   username='molerssh', password='moler_password',
                                                   logger=logger)
    with connection.open():
        new_connection = passive_sshshell_connection_class.from_sshshell(sshshell=connection, logger=logger)
        with new_connection.open():
            pass
    assert logger.calls == ['DEBUG: connecting to ssh://molerssh@localhost:22',
                            'DEBUG:   established ssh transport to localhost:22',
                            'DEBUG:   established shell ssh to localhost:22 [channel 0]',
                            ' INFO: connection ssh://molerssh@localhost:22 [channel 0] is open',
                            'DEBUG: connecting to ssh://molerssh@localhost:22',
                            'DEBUG:   reusing ssh transport to localhost:22',
                            'DEBUG:   established shell ssh to localhost:22 [channel 1]',
                            ' INFO: connection ssh://molerssh@localhost:22 [channel 1] is open',
                            'DEBUG: closing ssh://molerssh@localhost:22 [channel 1]',
                            'DEBUG:   closed shell ssh to localhost:22 [channel 1]',
                            ' INFO: connection ssh://molerssh@localhost:22 [channel 1] is closed',
                            'DEBUG: closing ssh://molerssh@localhost:22 [channel 0]',
                            'DEBUG:   closed shell ssh to localhost:22 [channel 0]',
                            'DEBUG:   closing ssh transport to localhost:22',
                            ' INFO: connection ssh://molerssh@localhost:22 [channel 0] is closed']


def test_logging_for_open_close_of_active_connection(active_sshshell_connection_class, mocked_logger):
    from moler.threaded_moler_connection import ThreadedMolerConnection

    logger = mocked_logger
    moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                         encoder=lambda data: data.encode("utf-8"))
    another_moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                                 encoder=lambda data: data.encode("utf-8"))
    with mock.patch("moler.io.raw.sshshell.ThreadedSshShell._select_logger", lambda self, x,y,z: logger):
        connection = active_sshshell_connection_class(moler_connection=moler_conn,
                                                      host='localhost', port=22,
                                                      username='molerssh', password='moler_password',
                                                      name="source_sshshell", logger_name="")
        with connection.open():
            new_connection = active_sshshell_connection_class.from_sshshell(sshshell=connection,
                                                                            moler_connection=another_moler_conn,
                                                                            name="cloned_sshshell", logger_name="")
            with new_connection.open():
                pass
    assert logger.calls == ['DEBUG: connecting to ssh://molerssh@localhost:22',
                            'DEBUG:   established ssh transport to localhost:22',
                            'DEBUG:   established shell ssh to localhost:22 [channel 0]',
                            ' INFO: connection ssh://molerssh@localhost:22 [channel 0] is open',
                            " INFO: Connection to: 'source_sshshell' has been opened.",
                            'DEBUG: connecting to ssh://molerssh@localhost:22',
                            'DEBUG:   reusing ssh transport to localhost:22',
                            'DEBUG:   established shell ssh to localhost:22 [channel 1]',
                            ' INFO: connection ssh://molerssh@localhost:22 [channel 1] is open',
                            " INFO: Connection to: 'cloned_sshshell' has been opened.",
                            'DEBUG: closing ssh://molerssh@localhost:22 [channel 1]',
                            'DEBUG:   closed shell ssh to localhost:22 [channel 1]',
                            ' INFO: connection ssh://molerssh@localhost:22 [channel 1] is closed',
                            " INFO: Connection to: 'cloned_sshshell' has been closed.",
                            'DEBUG: closing ssh://molerssh@localhost:22 [channel 0]',
                            'DEBUG:   closed shell ssh to localhost:22 [channel 0]',
                            'DEBUG:   closing ssh transport to localhost:22',
                            ' INFO: connection ssh://molerssh@localhost:22 [channel 0] is closed',
                            " INFO: Connection to: 'source_sshshell' has been closed."]


def test_opening_connection_created_from_existing_one_is_quicker(sshshell_connection):
    from moler.threaded_moler_connection import ThreadedMolerConnection

    connection = sshshell_connection
    if hasattr(connection, "moler_connection"):  # active connection
        another_moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                                     encoder=lambda data: data.encode("utf-8"))
        new_connection = sshshell_connection.__class__.from_sshshell(moler_connection=another_moler_conn,
                                                                     sshshell=connection)
    else:
        new_connection = sshshell_connection.__class__.from_sshshell(sshshell=connection)

    full_open_durations = []
    reused_conn_open_durations = []
    for cnt in range(10):
        start1 = time.monotonic()
        with connection.open():
            end1 = time.monotonic()
            start2 = time.monotonic()
            with new_connection.open():
                end2 = time.monotonic()
        full_open_durations.append(end1 - start1)
        reused_conn_open_durations.append(end2 - start2)

    avr_full_open_duration = sum(full_open_durations) / len(full_open_durations)
    avr_reused_conn_open_duration = sum(reused_conn_open_durations) / len(reused_conn_open_durations)
    assert (avr_reused_conn_open_duration * 3) < avr_full_open_duration


def test_closing_connection_created_from_existing_one_is_not_closing_transport_till_last_channel(sshshell_connection):
    from moler.threaded_moler_connection import ThreadedMolerConnection

    connection = sshshell_connection
    with connection.open():
        if hasattr(connection, "moler_connection"):  # active connection
            another_moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                                         encoder=lambda data: data.encode("utf-8"))
            new_connection = sshshell_connection.__class__.from_sshshell(moler_connection=another_moler_conn,
                                                                         sshshell=connection)
        else:
            new_connection = sshshell_connection.__class__.from_sshshell(sshshell=connection)
        with new_connection.open():
            assert connection._shell_channel.get_transport().is_authenticated()
            assert new_connection._shell_channel.get_transport().is_authenticated()
        assert new_connection._shell_channel is None
        assert connection._shell_channel is not None
        assert connection._shell_channel.get_transport().is_authenticated()
    assert connection._shell_channel is None


def test_str_representation_of_connection(sshshell_connection):
    from moler.threaded_moler_connection import ThreadedMolerConnection

    if hasattr(sshshell_connection, "moler_connection"):  # active connection
        another_moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                                     encoder=lambda data: data.encode("utf-8"))
        connection = sshshell_connection.__class__(moler_connection=another_moler_conn,
                                                   host='localhost', port=22,
                                                   username='molerssh', password='moler_password')
    else:
        connection = sshshell_connection.__class__(host='localhost', port=22,
                                                   username='molerssh', password='moler_password')
    assert str(connection) == "ssh://molerssh@localhost:22"
    with connection.open():
        shell_channel_id = connection._shell_channel.get_id()
        assert str(connection) == f"ssh://molerssh@localhost:22 [channel {shell_channel_id}]"
    assert str(connection) == "ssh://molerssh@localhost:22"


# Note: we check sending and receiving together - checking send by its result on receive
def test_can_send_and_receive_binary_data_over_passive_connection(passive_sshshell_connection_class):

    connection = passive_sshshell_connection_class(host='localhost', port=22,
                                                   username='molerssh', password='moler_password')
    with connection.open():
        time.sleep(0.1)
        if connection._shell_channel.recv_ready():  # some banner just after open ssh
            connection.receive()
        request = "pwd\n"
        bytes2send = request.encode("utf-8")
        connection.send(bytes2send)
        time.sleep(0.1)
        resp_bytes = connection.receive()
        response = resp_bytes.decode("utf-8")
        assert ('/home/' in response) or ('pwd' in response)  # pwd output or just first chunk with pwd echo


# Note1 different active external-IO connections may have different naming for their 'send' method
# however, they are uniformed via glueing with moler_connection.send()
# external-IO 'send' method works on bytes; moler_connection performs encoding
def test_can_send_and_receive_binary_data_over_active_connection(active_sshshell_connection):
    received_data = ['']
    receiver_called = threading.Event()

    def receiver(data, timestamp):
        received_data.append(data)
        if "home" in data:
            receiver_called.set()

    def connection_closed_handler():
        pass

    connection = active_sshshell_connection
    moler_conn = connection.moler_connection
    with connection.open():  # started pulling thread will forward initial banner of server
        time.sleep(0.1)  # into embedded moler_connection. It will be just logged there.
        # ------------------------------------------------------------------------------
        # only after subscribing on moler_connection we will have client to consume pushed connection data
        moler_conn.subscribe(receiver, connection_closed_handler)
        request = "pwd\n"
        # sending is not directly via sshshell-io but via moler_connection that does encoding and forwarding
        moler_conn.send(data=request)
        receiver_called.wait(timeout=0.5)
        moler_conn.unsubscribe(receiver, connection_closed_handler)
        response = "".join(received_data)
        assert '/home/' in response


def test_cant_send_over_not_opened_connection(sshshell_connection):
    from moler.io.io_exceptions import RemoteEndpointNotConnected
    connection = sshshell_connection
    with pytest.raises(RemoteEndpointNotConnected):
        connection.send(b'ls -l\n')


def test_cant_receive_from_not_opened_connection(sshshell_connection):
    from moler.io.io_exceptions import RemoteEndpointNotConnected
    connection = sshshell_connection
    with pytest.raises(RemoteEndpointNotConnected):
        connection.receive()


def test_receive_on_passive_connection_is_timeout_protected(passive_sshshell_connection_class):
    from moler.io.io_exceptions import ConnectionTimeout
    connection = passive_sshshell_connection_class(host='localhost', port=22, username='molerssh', password='moler_password')
    with connection.open():
        time.sleep(0.3)
        if connection._shell_channel.recv_ready():  # some banner just after open ssh
            connection.receive()
        with pytest.raises(ConnectionTimeout) as exc:
            connection.receive(timeout=0.2)
        assert "Timeout (> 0.200 sec) on ssh://molerssh@localhost:22" in str(exc.value)


def test_passive_connection_receive_detects_remote_end_close(passive_sshshell_connection_class):
    from moler.io.io_exceptions import RemoteEndpointDisconnected
    connection = passive_sshshell_connection_class(host='localhost', port=22, username='molerssh', password='moler_password')
    with connection.open():
        time.sleep(0.1)
        if connection._shell_channel.recv_ready():  # some banner just after open ssh
            print(connection.receive())
        request = "exit\n"
        bytes2send = request.encode("utf-8")
        connection.send(bytes2send)
        time.sleep(0.1)

        # response bytes happen to come in multiple tcp chunks
        chunks_nb = 0
        resp = ''
        while chunks_nb < 100:  # should be just few chunks but let's secure against infinite loop
            resp_bytes = connection.receive(timeout=0.5)
            chunks_nb += 1
            resp += resp_bytes.decode("utf-8")
            print(f"resp = {resp}")
            if ('logout' in resp) and resp.endswith("\n"):
                break
        time.sleep(0.1)  # let it drop connection

        with pytest.raises(RemoteEndpointDisconnected):
            resp = connection.receive(timeout=0.5)
            print(f"resp = {resp}")
        assert connection._shell_channel is None
        assert connection._ssh_transport is None


def test_active_connection_pulling_detects_remote_end_close(active_sshshell_connection):
    received_data = ['']
    receiver_called = threading.Event()

    def receiver(data, timestamp):
        received_data.append(data)
        if "exit" in data:
            receiver_called.set()

    def connection_closed_handler():
        pass

    connection = active_sshshell_connection
    moler_conn = connection.moler_connection
    with connection.open():
        time.sleep(0.1)
        moler_conn.subscribe(receiver, connection_closed_handler)
        request = "exit\n"
        # sending is not directly via sshshell-io but via moler_connection that does encoding and forwarding
        moler_conn.send(data=request)
        receiver_called.wait(timeout=0.4)
        moler_conn.unsubscribe(receiver, connection_closed_handler)
        echo = "".join(received_data)
        assert "exit" in echo
        time.sleep(0.3)  # allow threads switch
        assert connection._shell_channel is None  # means already closed
        assert connection._ssh_transport is None


def test_send_can_timeout(sshshell_connection):
    from moler.io.io_exceptions import ConnectionTimeout
    connection = sshshell_connection
    with connection.open():
        big_data = "123456789 " * 10000
        request = f"echo {big_data}\n"
        bytes2send = request.encode("utf-8")

        original_send = connection._shell_channel.send

        def slow_send_in_small_chunks(data):
            # fast machine may push whole data via localhost ssh before timeout, so emulate slow channel
            time.sleep(0.002)
            return original_send(data[:100])

        with mock.patch.object(connection._shell_channel, "send", slow_send_in_small_chunks):
            with pytest.raises(ConnectionTimeout) as exc:
                connection.send(bytes2send, timeout=0.0005)
        assert "Timeout (> 0.001 sec) on ssh://molerssh@localhost:22" in str(exc.value)


def test_send_can_push_remaining_data_within_timeout(sshshell_connection):
    connection = sshshell_connection
    with connection.open():
        big_data = "123456789 " * 10000
        request = f"echo {big_data}\n"
        bytes2send = request.encode("utf-8")

        data_chunks_len = []
        original_send = connection._shell_channel.send

        def send_counting_chunks(data):
            nb_bytes_sent = original_send(data)
            data_chunks_len.append(nb_bytes_sent)
            return nb_bytes_sent

        with mock.patch.object(connection._shell_channel, "send", send_counting_chunks):
            connection.send(bytes2send, timeout=0.1)
        assert len(data_chunks_len) > 1  # indeed, there were chunks
        assert sum(data_chunks_len) == len(bytes2send)


def test_passive_connection_send_detects_remote_end_closed(passive_sshshell_connection_class):
    from moler.io.io_exceptions import RemoteEndpointDisconnected
    connection = passive_sshshell_connection_class(host='localhost', port=22, username='molerssh', password='moler_password')
    with connection.open():
        time.sleep(0.1)
        if connection._shell_channel.recv_ready():  # some banner just after open ssh
            banner = connection.receive()
            print(banner)
        request = "exit\n"
        bytes2send = request.encode("utf-8")
        connection.send(bytes2send)
        time.sleep(0.1)

        # response bytes happen to come in multiple tcp chunks
        chunks_nb = 0
        resp = ''
        while chunks_nb < 100:  # should be just few chunks but let's secure against infinite loop
            resp_bytes = connection.receive(timeout=0.5)
            chunks_nb += 1
            resp += resp_bytes.decode("utf-8")
            print(f"resp = {resp}")
            if ('logout' in resp) and resp.endswith("\n"):
                break
        time.sleep(0.1)  # let it drop connection

        with pytest.raises(RemoteEndpointDisconnected):
            connection.send(bytes2send)
        assert connection._shell_channel is None
        assert connection._ssh_transport is None


def test_active_connection_send_detects_remote_end_closed(active_sshshell_connection):
    from moler.io.io_exceptions import RemoteEndpointNotConnected

    connection = active_sshshell_connection
    moler_conn = connection.moler_connection
    with connection.open():
        time.sleep(0.1)
        moler_conn.send(data="exit\n")
        time.sleep(0.5)  # allow active connection to get command echo (tested elsewhere) and react on remote end close

        with pytest.raises(RemoteEndpointNotConnected):
            moler_conn.send(data="exit\n")


def test_active_connection_can_notify_on_establishing_and_closing_connection(active_sshshell_connection):
    notifications = []

    def on_connection_made(connection):
        notifications.append(("made", time.monotonic(), connection))

    def on_connection_lost(connection):
        notifications.append(("lost", time.monotonic(), connection))

    connection = active_sshshell_connection
    connection.notify(callback=on_connection_made, when="connection_made")
    connection.notify(callback=on_connection_lost, when="connection_lost")
    before_open_time = time.monotonic()
    with connection.open():
        after_open_time = time.monotonic()
        time.sleep(0.1)
        before_close_time = time.monotonic()
        time.sleep(0.1)
    after_close_time = time.monotonic()

    assert len(notifications) == 2
    assert "made" == notifications[0][0]
    assert "lost" == notifications[1][0]
    assert connection is notifications[0][2]
    assert connection is notifications[1][2]
    made_time = notifications[0][1]
    lost_time = notifications[1][1]

    assert before_open_time < made_time < after_open_time
    assert before_close_time < lost_time < after_close_time


def test_active_connection_can_notify_on_losing_connection(active_sshshell_connection):
    lost_time = []

    def on_connection_lost(connection):
        lost_time.append(time.monotonic())

    connection = active_sshshell_connection
    moler_conn = connection.moler_connection
    connection.notify(callback=on_connection_lost, when="connection_lost")
    with connection.open():
        time.sleep(0.1)
        moler_conn.send(data="exit\n")
        before_exit_from_remote_time = time.monotonic()
        time.sleep(0.5)
        before_close_time = time.monotonic()

    assert len(lost_time) == 1
    connection_lost_time = lost_time[0]

    assert before_exit_from_remote_time < connection_lost_time < before_close_time


def test_active_connection_with_unexpected_exception_inside_pull_thread_should_always_close_connection(active_sshshell_connection):
    # This requirement is against leaking resources caused by not closed ssh
    import logging
    lost_conn = []

    def on_connection_lost(connection):
        lost_conn.append(connection)

    def exc_raiser(self):
        raise IndexError()

    connection = active_sshshell_connection
    connection.notify(callback=on_connection_lost, when="connection_lost")

    with connection.open():
        time.sleep(0.1)
        with mock.patch("moler.io.raw.sshshell.SshShell._recv", exc_raiser):
            time.sleep(0.5)

    assert connection._shell_channel is None
    assert connection._ssh_transport is None
    assert connection in lost_conn

    logging_records = []

    def log_handler(record):
        logging_records.append(record)

    logger = logging.getLogger("sshshell-io")
    connection.sshshell.logger = logger
    with connection.open():
        time.sleep(0.1)
        with mock.patch.object(logger, "handle", log_handler):
            with mock.patch("moler.io.raw.sshshell.SshShell._recv", exc_raiser):
                time.sleep(0.5)
    assert logging_records
    print(logging_records[0])
    assert logging_records[0].exc_info is not None


def test_can_assign_name_to_connection(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection

    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost',
                                                  name="ctrl_server")
    assert connection.name == "ctrl_server"


def test_uses_moler_connection_name_if_none_given(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection

    moler_conn = Connection()
    moler_conn.name = "srv2"
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost')
    assert connection.name == moler_conn.name


def test_overwrites_moler_connection_name_with_own_one(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection

    moler_conn = Connection()
    # during construction
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost', name="web_srv")
    assert moler_conn.name == "web_srv"
    # during direct attribute set
    connection.name = "http_srv"
    assert moler_conn.name == "http_srv"


def test_can_use_provided_logger(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection
    import logging

    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost',
                                                  logger_name="conn.web_srv")
    assert isinstance(connection.logger, logging.Logger)
    assert connection.logger.name == "conn.web_srv"


def test_can_switch_off_logging(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection

    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost',
                                                  logger_name=None)
    assert connection.logger is None


def test_can_use_default_logger_based_on_connection_name(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection
    import logging

    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost', name="ABC")
    assert isinstance(connection.logger, logging.Logger)
    assert connection.logger.name == "moler.connection.ABC.io"

    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost')
    assert isinstance(connection.logger, logging.Logger)
    assert connection.logger.name == f"moler.connection.{connection.name}.io"


def test_can_use_default_logger_based_on_moler_connection_name(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection
    import logging

    moler_conn = Connection(name="ABC", logger_name="conn.DEF")
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost')
    assert isinstance(connection.logger, logging.Logger)
    assert connection.logger.name == "conn.DEF.io"


def test_changing_connection_name_doesnt_switch_logger_if_external_logger_used(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection

    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost',
                                                  name="ABC",
                                                  logger_name="conn.ABC")
    assert connection.logger.name == "conn.ABC"
    connection.name = "DEF"
    assert connection.logger.name == "conn.ABC"


def test_changing_connection_name_doesnt_activate_logger_if_logging_is_off(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection

    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost',
                                                  name="ABC",
                                                  logger_name=None)
    assert connection.logger is None
    connection.name = "DEF"
    assert connection.logger is None


def test_changing_connection_name_switches_logger_if_default_logger_used(active_sshshell_connection_class):
    from moler.abstract_moler_connection import AbstractMolerConnection as Connection

    # default logger generated internally by connection
    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost',
                                                  name="ABC")
    assert connection.logger.name == "moler.connection.ABC.io"

    connection.name = "DEF"
    assert connection.logger.name == "moler.connection.DEF.io"
    assert connection.sshshell.logger.name == "moler.connection.DEF.io"

    # default logger via default naming
    moler_conn = Connection()
    connection = active_sshshell_connection_class(moler_connection=moler_conn, host='localhost',
                                                  name="ABC",
                                                  logger_name="moler.connection.ABC.io")
    connection.name = "DEF"
    assert connection.logger.name == "moler.connection.DEF.io"
    assert connection.sshshell.logger.name == "moler.connection.DEF.io"


def test_connection_factory_has_sshshell_constructor_active_by_default():
    from moler.connection_factory import get_connection

    conn = get_connection(io_type='sshshell', variant='threaded',
                          host='localhost', port=2222, username="moler", password="moler_passwd")
    assert conn.__module__ == 'moler.io.raw.sshshell'
    assert conn.__class__.__name__ == 'ThreadedSshShell'
    assert hasattr(conn, 'moler_connection')
    assert conn.sshshell.host == "localhost"
    assert conn.sshshell.port == 2222
    assert conn.sshshell.username == "moler"
    assert conn.sshshell.password == "moler_passwd"


def test_connection_factory_has_threaded_registered_as_default_variant_of_sshshell():
    from moler.connection_factory import get_connection

    conn = get_connection(io_type='sshshell',
                          host='localhost', port=2222, username="moler", password="moler_passwd")
    assert conn.__module__ == 'moler.io.raw.sshshell'
    assert conn.__class__.__name__ == 'ThreadedSshShell'


def test_connection_factory_can_use_alternate_login_param_of_sshshell():
    from moler.connection_factory import get_connection

    conn = get_connection(io_type='sshshell',
                          host='localhost', port=2222, login="moler", password="moler_passwd")
    assert conn.__module__ == 'moler.io.raw.sshshell'
    assert conn.__class__.__name__ == 'ThreadedSshShell'


def test_connection_factory_can_build_sshshell_based_on_other_sshshell_for_sshtransport_reuse():
    from moler.connection_factory import get_connection

    conn1 = get_connection(io_type='sshshell', host='localhost', port=2222, username="moler", password="moler_passwd")
    conn2 = get_connection(io_type='sshshell', reuse_ssh_of_shell=conn1)
    assert conn2.sshshell.host == "localhost"
    assert conn2.sshshell.port == 2222
    assert conn2.sshshell.username == "moler"
    assert conn2.sshshell.password == "moler_passwd"


# --------------------------- resources ---------------------------


def import_class(packet_prefixed_class_name):
    module_name, class_name = packet_prefixed_class_name.rsplit('.', 1)
    module = importlib.import_module(module_name)
    connection_class = getattr(module, class_name)
    return connection_class

#########################################################################
# Connection like SshShell is passive connection - needs pulling for data
# uses receive() API
#########################################################################
@pytest.fixture(params=['io.raw.sshshell.SshShell'])
def passive_sshshell_connection_class(request):
    connection_class = import_class(f"moler.{request.param}")
    return connection_class


######################################################################################################################
# Connection like ThreadedSshShell is active connections - pushes data by itself (same model as asyncio, Twisted, etc)
# uses data_received() API which delivers data to embedded moler_connection
######################################################################################################################
@pytest.fixture(params=['io.raw.sshshell.ThreadedSshShell'])
def active_sshshell_connection_class(request):
    connection_class = import_class(f"moler.{request.param}")
    return connection_class


@pytest.fixture(params=['io.raw.sshshell.SshShell', 'io.raw.sshshell.ThreadedSshShell'])
def sshshell_connection(request):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    connection_class = import_class(f"moler.{request.param}")
    ######################################################################################
    # SshShell and ThreadedSshShell differ in API - ThreadedSshShell gets moler_connection
    # Why - see comment in sshshell.py
    ######################################################################################
    if "Threaded" in request.param:
        moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                             encoder=lambda data: data.encode("utf-8"))
        connection = connection_class(moler_connection=moler_conn,
                                      host='localhost', port=22, username='molerssh', password='moler_password')
    else:
        connection = connection_class(host='localhost', port=22, username='molerssh', password='moler_password')
    return connection


@pytest.fixture
def active_sshshell_connection(active_sshshell_connection_class):
    from moler.threaded_moler_connection import ThreadedMolerConnection
    connection_class = active_sshshell_connection_class
    moler_conn = ThreadedMolerConnection(decoder=lambda data: data.decode("utf-8"),
                                         encoder=lambda data: data.encode("utf-8"))
    connection = connection_class(moler_connection=moler_conn,
                                  host='localhost', port=22, username='molerssh', password='moler_password')
    return connection


@pytest.fixture
def mocked_logger():
    import logging

    class MyLogger(object):
        def __init__(self):
            self.calls = []

        def debug(self, msg):
            msg_without_details = msg.split(" |", 1)
            self.calls.append(f"DEBUG: {msg_without_details[0]}")

        def info(self, msg, **kwargs):
            msg_without_details = msg.split(" |", 1)
            self.calls.append(f" INFO: {msg_without_details[0]}")

    def mocked_log(self, msg, level, levels_to_go_up=1):
        if level == logging.DEBUG:
            logger.debug(msg)
        elif level == logging.INFO:
            logger.info(msg)
        else:
            raise ValueError(f"unexpected logging level = {level}")

    with mock.patch("moler.io.raw.sshshell.SshShell._log", mocked_log):
        logger = MyLogger()
        yield logger
