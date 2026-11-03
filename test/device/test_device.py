# -*- coding: utf-8 -*-

__author__ = 'Grzegorz Latuszek, Michal Ernst, Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2021, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, michal.ernst@nokia.com, marcin.usielski@nokia.com'

import pytest


def test_device_directly_created_must_be_given_io_connection(buffer_connection):
    from moler.device.unixlocal import UnixLocal

    dev = UnixLocal(io_connection=buffer_connection)
    assert dev.io_connection == buffer_connection


def test_device_add_neighbour_device(buffer_connection):
    from moler.device.unixlocal import UnixLocal

    dev1 = UnixLocal(io_connection=buffer_connection)
    dev2 = UnixLocal(io_connection=buffer_connection)
    neighbour_devices = dev1.get_neighbour_devices(device_type=UnixLocal)
    assert 0 == len(neighbour_devices)

    dev1.add_neighbour_device(neighbour_device=dev2, bidirectional=True)
    neighbour_devices = dev1.get_neighbour_devices(device_type=UnixLocal)
    assert 1 == len(neighbour_devices)

    neighbour_devices = dev2.get_neighbour_devices(device_type=UnixLocal)
    assert 1 == len(neighbour_devices)

    # device is added only once
    dev1.add_neighbour_device(neighbour_device=dev2)
    neighbour_devices = dev1.get_neighbour_devices(device_type=UnixLocal)
    assert 1 == len(neighbour_devices)

    neighbour_devices = dev1.get_neighbour_devices(device_type=None)
    assert 1 == len(neighbour_devices)

    neighbour_devices = dev1.get_neighbour_devices(device_type=int)
    assert 0 == len(neighbour_devices)


def test_device_add_neighbour_device_without_bidirectional(buffer_connection):
    from moler.device.unixlocal import UnixLocal
    dev1 = UnixLocal(io_connection=buffer_connection)
    dev2 = UnixLocal(io_connection=buffer_connection)

    dev1.add_neighbour_device(neighbour_device=dev2, bidirectional=False)

    neighbour_devices = dev1.get_neighbour_devices(device_type=UnixLocal)
    assert 1 == len(neighbour_devices)

    neighbour_devices = dev2.get_neighbour_devices(device_type=UnixLocal)
    assert 0 == len(neighbour_devices)


def test_device_may_be_created_on_named_connection(configure_net_1_connection):
    from moler.device.unixlocal import UnixLocal

    dev = UnixLocal.from_named_connection(connection_name='net_1')
    assert dev.io_connection is not None
    assert dev.io_connection.name == 'net_1'


def test_device_unix_can_return_cd_command(configure_net_1_connection):
    from moler.device.unixlocal import UnixLocal
    from moler.cmd.unix.cd import Cd

    ux = UnixLocal.from_named_connection(connection_name='net_1')
    ux.establish_connection()
    assert hasattr(ux, 'get_cmd')
    assert isinstance(
        ux.get_cmd(
            cmd_name='cd',
            cmd_params={
                "path": "/home/user/"
            }
        ),
        Cd
    )


def test_device_disable_and_enable_logging(buffer_connection):
    from moler.device.unixlocal import UnixLocal
    dev1 = UnixLocal(io_connection=buffer_connection)
    dev1.disable_logging()
    assert False == dev1.io_connection.moler_connection._enabled_logging
    dev1.disable_logging()
    assert False == dev1.io_connection.moler_connection._enabled_logging
    dev1.enable_logging()
    assert True == dev1.io_connection.moler_connection._enabled_logging
    dev1.enable_logging()
    assert True == dev1.io_connection.moler_connection._enabled_logging


def test_device_logging_suffix(buffer_connection):
    from moler.config.loggers import change_logging_suffix
    import moler
    from moler.device.unixlocal import UnixLocal
    suffix = "DEVICE_SUFFIX"
    dev1 = UnixLocal(io_connection=buffer_connection)
    device_name = dev1.name
    change_logging_suffix(None)
    dev1.set_logging_suffix(suffix)
    for logger_name in moler.config.loggers._logging_suffixes.keys():
        if device_name in logger_name:
            assert suffix == moler.config.loggers._logging_suffixes[logger_name]
        else:
            assert None is moler.config.loggers._logging_suffixes[logger_name]
    dev1.set_logging_suffix(None)
    for logger_name in moler.config.loggers._logging_suffixes.keys():
        assert None is moler.config.loggers._logging_suffixes[logger_name]


def test_device_remove_unsubscribes_from_io_connection(buffer_connection):
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_UNSUBSCRIBE")
    assert dev.on_connection_made in buffer_connection._connect_subscribers
    assert dev.on_connection_lost in buffer_connection._disconnect_subscribers

    dev.remove()

    assert dev.on_connection_made not in buffer_connection._connect_subscribers
    assert dev.on_connection_lost not in buffer_connection._disconnect_subscribers


def test_device_remove_closes_log_handlers_and_same_name_logger_can_be_recreated(buffer_connection):
    import logging
    from moler.config.loggers import active_loggers, close_device_logger, configure_device_logger
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_LOGGER")
    logger = dev.device_data_logger
    handlers = list(logger.handlers)
    file_handlers = [handler for handler in handlers if isinstance(handler, logging.FileHandler)]
    assert file_handlers

    dev.remove()

    assert [] == logger.handlers
    for handler in file_handlers:
        assert handler.stream is None
    assert logger.name not in active_loggers

    recreated_logger = configure_device_logger(connection_name="REMOVE_LOGGER")
    try:
        assert recreated_logger is logger
        assert any(isinstance(handler, logging.FileHandler) for handler in recreated_logger.handlers)
    finally:
        close_device_logger(recreated_logger)


def test_device_remove_unlinks_neighbour_devices(buffer_connection):
    from moler.device.unixlocal import UnixLocal
    dev1 = UnixLocal(io_connection=buffer_connection, name="REMOVE_NEIGHBOUR_1")
    dev2 = UnixLocal(io_connection=buffer_connection, name="REMOVE_NEIGHBOUR_2")
    dev1.add_neighbour_device(neighbour_device=dev2, bidirectional=True)

    dev1.remove()

    assert [] == dev1.get_neighbour_devices(device_type=None)
    assert [] == dev2.get_neighbour_devices(device_type=None)
    dev2.remove()


def test_device_remove_calls_removal_callbacks_only_once(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_CALLBACKS")
    callback = mock.Mock()
    dev.register_device_removal_callback(callback)

    dev.remove()
    dev.remove()

    assert 1 == callback.call_count


def test_device_remove_drops_queued_states_and_waits_for_goto_state_thread(buffer_connection):
    import threading
    import time
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_GOTO_THREAD")
    dev._kept_state = "UNIX_LOCAL"
    dev._queue_states.put({"dest_state": "UNIX_LOCAL"})
    dev._queue_states.put({"dest_state": "UNIX_LOCAL_ROOT"})
    goto_thread = threading.Thread(target=time.sleep, args=(0.5,), daemon=True)
    goto_thread.start()
    dev._thread_for_goto_state = goto_thread

    dev.remove()

    assert dev._queue_states.empty()
    assert dev._kept_state is None
    assert not goto_thread.is_alive()


def test_device_remove_of_not_established_device_does_not_open_connection(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_NOT_ESTABLISHED")
    assert not dev.has_established_connection()

    with mock.patch.object(dev, "establish_connection") as establish_connection:
        dev.remove()

    establish_connection.assert_not_called()
    assert "NOT_CONNECTED" == dev.current_state


def test_device_remove_shuts_down_moler_connection(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_SHUTDOWN")
    moler_connection = buffer_connection.moler_connection

    with mock.patch.object(buffer_connection, "close"):
        dev.remove()

    assert not moler_connection.is_open()


def test_device_remove_of_established_device_closes_and_cleans_up(configure_net_1_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal.from_named_connection(connection_name='net_1')
    neighbour = UnixLocal.from_named_connection(connection_name='net_1')
    dev.add_neighbour_device(neighbour_device=neighbour, bidirectional=True)
    callback = mock.Mock()
    dev.register_device_removal_callback(callback)
    dev.establish_connection()
    assert "UNIX_LOCAL" == dev.current_state
    io_connection = dev.io_connection

    dev.remove()
    dev.remove()

    assert "NOT_CONNECTED" == dev.current_state
    assert not dev.has_established_connection()
    assert not io_connection.moler_connection.is_open()
    assert dev.on_connection_made not in io_connection._connect_subscribers
    assert dev.on_connection_lost not in io_connection._disconnect_subscribers
    assert [] == neighbour.get_neighbour_devices(device_type=None)
    assert 1 == callback.call_count
    assert [] == dev.device_data_logger.handlers

# --------------------------- resources ---------------------------


@pytest.fixture
def configure_net_1_connection():
    import mock
    from moler.config import connections as conn_cfg

    with mock.patch.object(conn_cfg, "default_variant", {}):
        with mock.patch.object(conn_cfg, "named_connections", {}):

            conn_cfg.set_default_variant(io_type='memory', variant="threaded")
            conn_cfg.define_connection(name='net_1', io_type='memory')

            yield
