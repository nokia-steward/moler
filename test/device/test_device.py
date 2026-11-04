# -*- coding: utf-8 -*-

__author__ = 'Grzegorz Latuszek, Michal Ernst, Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
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


def test_background_goto_state_stops_between_hops_after_remove(buffer_connection):
    import mock
    import threading
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_GOTO_HOPS")
    hops = []

    def trigger_change_state(**kwargs):
        hops.append(kwargs["next_state"])
        dev._removed = True  # Device is removed while the first hop is executed.

    dev._queue_states.put({
        "dest_state": "UNIX_LOCAL_ROOT", "keep_state": True, "timeout": 5, "rerun": 0,
        "send_enter_after_changed_state": False, "log_stacktrace_on_fail": False,
        "queue_if_goto_state_in_another_thread": False, "ignore_exceptions": True,
    })
    thread = threading.Thread(target=dev._goto_state_thread, daemon=True)
    dev._thread_for_goto_state = thread
    with mock.patch.object(dev, "_get_next_state", return_value="UNIX_LOCAL"), \
            mock.patch.object(dev, "_trigger_change_state", side_effect=trigger_change_state):
        thread.start()
        thread.join(timeout=3)

    try:
        assert not thread.is_alive()
        assert ["UNIX_LOCAL"] == hops
        assert dev._kept_state is None
        assert dev._thread_for_goto_state is None
    finally:
        dev._removed = False  # Let remove() really clean up.
        dev.remove()


def test_device_remove_cancels_observers_to_stop_busy_goto_state_thread(buffer_connection):
    import mock
    import threading
    import time
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_GOTO_BUSY")
    dev._goto_state_thread_grace_timeout = 0.2
    dev._goto_state_thread_join_timeout = 3
    command_cancelled = threading.Event()
    prompts_event = mock.Mock(name="prompts_event")
    dev._prompts_event = prompts_event
    dev._created_observers.add(prompts_event)
    prompts_cancelled_before_command = []

    def cancel_command():
        prompts_cancelled_before_command.append(prompts_event.cancel.call_count)
        command_cancelled.set()
        return True

    running_command = mock.Mock(name="running_command")
    running_command.cancel.side_effect = cancel_command
    dev._created_observers.add(running_command)
    goto_thread = threading.Thread(target=command_cancelled.wait, args=(10,), daemon=True)
    goto_thread.start()
    dev._thread_for_goto_state = goto_thread

    start_time = time.monotonic()
    dev.remove()
    elapsed = time.monotonic() - start_time

    assert not goto_thread.is_alive()
    assert elapsed < 3
    running_command.cancel.assert_called_once_with()
    assert [0] == prompts_cancelled_before_command  # Prompts observer is kept for leaving states.


def test_device_remove_gives_up_waiting_for_goto_state_thread_that_cannot_be_stopped(buffer_connection):
    import logging
    import mock
    import threading
    import time
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_GOTO_HUNG")
    dev._goto_state_thread_grace_timeout = 0.1
    dev._goto_state_thread_join_timeout = 0.2
    goto_thread = threading.Thread(target=time.sleep, args=(1.5,), daemon=True)
    goto_thread.start()
    dev._thread_for_goto_state = goto_thread

    try:
        with mock.patch.object(dev, "_log", wraps=dev._log) as log:
            start_time = time.monotonic()
            dev.remove()
            elapsed = time.monotonic() - start_time

        assert goto_thread.is_alive()
        assert elapsed < 1.2
        warnings = [call.args[1] for call in log.call_args_list
                    if len(call.args) > 1 and call.args[0] == logging.WARNING]
        assert any("still alive" in warning for warning in warnings)
    finally:
        goto_thread.join(timeout=3)


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
    from moler.connection_factory import get_connection
    # Unique name so devices leaked by other tests do not share (and keep open) the logger of this test.
    dev = UnixLocal(io_connection=get_connection(name='net_1'), name="REMOVE_ESTABLISHED")
    neighbour = UnixLocal(io_connection=get_connection(name='net_1'), name="REMOVE_ESTABLISHED")
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
    # Devices of the same name share logger, so it must stay open until the last device is removed.
    assert dev.device_data_logger.handlers
    neighbour.remove()
    assert [] == dev.device_data_logger.handlers


def test_device_remove_closes_connection_directly_if_leaving_states_fails(configure_net_1_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal.from_named_connection(connection_name='net_1')
    dev.establish_connection()
    io_connection = dev.io_connection

    with mock.patch.object(dev, "goto_state", side_effect=RuntimeError("cannot leave state")):
        dev.remove()

    assert not dev.has_established_connection()
    assert "NOT_CONNECTED" == dev.current_state
    assert not io_connection.moler_connection.is_open()


def test_device_remove_does_cleanup_even_if_closing_connection_fails(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_CLOSE_FAILS")
    callback = mock.Mock()
    dev.register_device_removal_callback(callback)
    logger = dev.device_data_logger

    with mock.patch.object(dev, "_close_connection", side_effect=RuntimeError("close failed")):
        with pytest.raises(RuntimeError, match="close failed"):
            dev.remove()

    assert 1 == callback.call_count
    assert dev.on_connection_made not in buffer_connection._connect_subscribers
    assert dev.on_connection_lost not in buffer_connection._disconnect_subscribers
    assert [] == logger.handlers


def test_device_remove_does_not_close_connection_shared_with_neighbour(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev1 = UnixLocal(io_connection=buffer_connection, name="REMOVE_SHARED_1")
    dev2 = UnixLocal(io_connection=buffer_connection, name="REMOVE_SHARED_2")
    dev1.add_neighbour_device(neighbour_device=dev2, bidirectional=True)
    moler_connection = buffer_connection.moler_connection

    with mock.patch.object(buffer_connection, "close") as close, \
            mock.patch.object(moler_connection, "shutdown") as shutdown:
        dev1.remove()
        close.assert_not_called()
        shutdown.assert_not_called()
        assert "NOT_CONNECTED" == dev1.current_state
        dev2.remove()
        close.assert_called_once_with()
        shutdown.assert_called_once_with()


def test_device_remove_of_shared_connection_hands_it_over_to_neighbour(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev1 = UnixLocal(io_connection=buffer_connection, name="HAND_OVER_SHARED_1")
    dev2 = UnixLocal(io_connection=buffer_connection, name="HAND_OVER_SHARED_2")
    dev1.add_neighbour_device(neighbour_device=dev2, bidirectional=True)
    moler_connection = buffer_connection.moler_connection
    assert moler_connection.data_logger is dev2.device_data_logger
    cmd_params = {"prompt": r"^moler_bash#"}
    cmd1 = dev1.get_cmd(cmd_name="ls", cmd_params=cmd_params, check_state=False, for_state="UNIX_LOCAL")
    cmd2 = dev2.get_cmd(cmd_name="ls", cmd_params=cmd_params, check_state=False, for_state="UNIX_LOCAL")

    with mock.patch.object(buffer_connection, "close"), mock.patch.object(moler_connection, "shutdown"):
        dev2.remove()

        assert cmd2.cancelled()
        assert not cmd1.done()
        assert moler_connection.data_logger is dev1.device_data_logger
        assert buffer_connection.name == "HAND_OVER_SHARED_1"
        assert moler_connection.name == "HAND_OVER_SHARED_1"
        dev1.remove()


def test_removed_device_does_not_recover_kept_state(buffer_connection):
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVED_NO_RECOVER")
    dev.remove()
    dev._kept_state = "UNIX_LOCAL"  # As set by goto state thread outliving remove().

    dev._set_state("NOT_CONNECTED")

    assert dev._thread_for_goto_state is None
    assert dev._queue_states.empty()


def test_device_remove_twice_closes_connection_only_once(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_TWICE")

    with mock.patch.object(buffer_connection, "close") as close:
        dev.remove()
        dev.remove()

    close.assert_called_once_with()


def test_device_remove_calls_all_removal_callbacks_even_if_one_fails(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_FAILING_CALLBACK")
    failing_callback = mock.Mock(side_effect=RuntimeError("callback failed"))
    other_callback = mock.Mock()
    dev.register_device_removal_callback(failing_callback)
    dev.register_device_removal_callback(other_callback)
    logger = dev.device_data_logger

    with pytest.raises(RuntimeError, match="callback failed"):
        dev.remove()

    assert 1 == failing_callback.call_count
    assert 1 == other_callback.call_count
    assert [] == logger.handlers


def test_device_remove_logs_all_failing_removal_callbacks_and_raises_first(buffer_connection):
    import mock
    import moler.device.abstract_device as abstract_device
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_FAILING_CALLBACKS")
    first_callback = mock.Mock(side_effect=RuntimeError("first failed"))
    middle_callback = mock.Mock()
    last_callback = mock.Mock(side_effect=ValueError("last failed"))
    for callback in (first_callback, middle_callback, last_callback):
        dev.register_device_removal_callback(callback)

    with mock.patch.object(abstract_device._logger, "warning") as warning:
        with pytest.raises(RuntimeError, match="first failed"):
            dev.remove()

    assert 1 == middle_callback.call_count
    logged_exceptions = [call.args[2] for call in warning.call_args_list]
    assert 2 == len(logged_exceptions)
    assert isinstance(logged_exceptions[0], RuntimeError)
    assert isinstance(logged_exceptions[1], ValueError)


def test_device_remove_skips_unsubscribe_for_connection_without_it(buffer_connection):
    from moler.device.unixlocal import UnixLocal
    connection = _ConnectionWithoutUnsubscribe(io_connection=buffer_connection)
    dev = UnixLocal(io_connection=connection, name="REMOVE_NO_UNSUBSCRIBE")

    dev.remove()

    assert "NOT_CONNECTED" == dev.current_state


def test_device_exchange_io_connection_skips_unsubscribe_for_connection_without_it(buffer_connection):
    from moler.device.unixlocal import UnixLocal
    from moler.util.devices_SM import get_memory_device_connection
    dev = UnixLocal(io_connection=_ConnectionWithoutUnsubscribe(io_connection=buffer_connection),
                    name="EXCHANGE_NO_UNSUBSCRIBE")
    new_connection = get_memory_device_connection()

    dev.exchange_io_connection(io_connection=new_connection)
    try:
        assert dev.io_connection is new_connection
    finally:
        dev.remove()


def test_device_remove_without_data_logger(buffer_connection):
    from moler.config.loggers import close_device_logger
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="REMOVE_NO_DATA_LOGGER")
    data_logger = dev.device_data_logger
    dev.device_data_logger = None
    try:
        dev.remove()
    finally:
        close_device_logger(data_logger)


def test_removed_device_is_not_returned_as_neighbour_of_one_directional_link(buffer_connection):
    from moler.device.unixlocal import UnixLocal
    dev1 = UnixLocal(io_connection=buffer_connection, name="REMOVE_ONE_WAY_1")
    dev2 = UnixLocal(io_connection=buffer_connection, name="REMOVE_ONE_WAY_2")
    dev1.add_neighbour_device(neighbour_device=dev2, bidirectional=False)
    assert [dev2] == dev1.get_neighbour_devices(device_type=None)

    dev2.remove()

    assert [] == dev1.get_neighbour_devices(device_type=None)
    assert [] == dev1.get_neighbour_devices(device_type=UnixLocal)
    dev1.remove()


def test_device_logger_shared_by_devices_of_the_same_name_is_closed_by_the_last_one():
    from moler.config.loggers import active_loggers, close_device_logger, configure_device_logger
    logger = configure_device_logger(connection_name="REMOVE_SHARED_LOGGER")
    try:
        assert logger is configure_device_logger(connection_name="REMOVE_SHARED_LOGGER")
        assert logger.handlers

        close_device_logger(logger)
        assert logger.handlers
        assert logger.name in active_loggers

        close_device_logger(logger)
        assert [] == logger.handlers
        assert logger.name not in active_loggers
    finally:
        close_device_logger(logger)


def test_device_exchange_io_connection_releases_old_connection():
    from moler.device.unixlocal import UnixLocal
    from moler.util.devices_SM import get_memory_device_connection
    old_connection = get_memory_device_connection()
    new_connection = get_memory_device_connection()
    dev = UnixLocal(io_connection=old_connection, name="EXCHANGE_RELEASES_OLD")
    old_moler_connection = old_connection.moler_connection

    dev.exchange_io_connection(io_connection=new_connection)
    try:
        assert dev.io_connection is new_connection
        assert dev.on_connection_made not in old_connection._connect_subscribers
        assert dev.on_connection_lost not in old_connection._disconnect_subscribers
        assert not old_moler_connection.is_open()
    finally:
        dev.remove()


def test_device_exchange_io_connection_stops_goto_state_thread_before_closing_old_connection():
    import mock
    import threading
    from moler.device.unixlocal import UnixLocal
    from moler.util.devices_SM import get_memory_device_connection
    old_connection = get_memory_device_connection()
    new_connection = get_memory_device_connection()
    dev = UnixLocal(io_connection=old_connection, name="EXCHANGE_GOTO_BUSY")
    dev._goto_state_thread_grace_timeout = 0.2
    dev._goto_state_thread_join_timeout = 3
    command_cancelled = threading.Event()
    running_command = mock.Mock(name="running_command")
    running_command.cancel.side_effect = lambda: command_cancelled.set() or True
    dev._created_observers.add(running_command)
    goto_thread = threading.Thread(target=command_cancelled.wait, args=(10,), daemon=True)
    goto_thread.start()
    dev._thread_for_goto_state = goto_thread
    dev._kept_state = "UNIX_LOCAL_ROOT"
    dev._queue_states.put({"dest_state": "UNIX_LOCAL_ROOT"})
    thread_alive_when_old_connection_closed = []
    original_close = old_connection.close

    def close():
        thread_alive_when_old_connection_closed.append(goto_thread.is_alive())
        return original_close()

    with mock.patch.object(old_connection, "close", side_effect=close):
        dev.exchange_io_connection(io_connection=new_connection)
    try:
        assert [False] == thread_alive_when_old_connection_closed
        running_command.cancel.assert_called_once_with()
        assert dev._queue_states.empty()
        assert dev._kept_state is None
        assert dev.io_connection is new_connection
        assert "UNIX_LOCAL" == dev.current_state
    finally:
        dev.remove()


def test_background_goto_state_stops_between_hops_after_exchange_of_io_connection(buffer_connection):
    import mock
    import threading
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="EXCHANGE_GOTO_HOPS")
    hops = []

    def trigger_change_state(**kwargs):
        hops.append(kwargs["next_state"])
        dev._goto_state_generation += 1  # io_connection is exchanged while the first hop is executed.

    state_options = {
        "dest_state": "UNIX_LOCAL_ROOT", "keep_state": True, "timeout": 5, "rerun": 0,
        "send_enter_after_changed_state": False, "log_stacktrace_on_fail": False,
        "queue_if_goto_state_in_another_thread": False, "ignore_exceptions": True,
    }
    dev._queue_states.put(state_options)
    dev._queue_states.put(dict(state_options, dest_state="UNIX_LOCAL"))  # Belongs to a newer thread.
    thread = threading.Thread(target=dev._goto_state_thread, daemon=True)
    dev._thread_for_goto_state = thread
    with mock.patch.object(dev, "_get_next_state", return_value="UNIX_LOCAL"), \
            mock.patch.object(dev, "_trigger_change_state", side_effect=trigger_change_state):
        thread.start()
        thread.join(timeout=3)

    try:
        assert not thread.is_alive()
        assert ["UNIX_LOCAL"] == hops
        assert dev._kept_state is None
        assert dev._thread_for_goto_state is None
        assert 1 == dev._queue_states.qsize()  # Device is not removed so states of newer thread are kept.
    finally:
        dev._drop_queued_states()
        dev.remove()


def test_stop_goto_state_thread_forgets_thread_that_cannot_be_stopped(buffer_connection):
    import threading
    import time
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="GOTO_THREAD_NOT_STOPPED")
    goto_thread = threading.Thread(target=time.sleep, args=(1.0,), daemon=True)
    goto_thread.start()
    dev._thread_for_goto_state = goto_thread
    try:
        dev._stop_goto_state_thread(timeout=0.05, grace_timeout=0.05)

        assert goto_thread.is_alive()
        assert dev._thread_for_goto_state is None  # New states are not queued for the thread that is stuck.
    finally:
        goto_thread.join(timeout=3)
        dev.remove()


def test_goto_state_thread_does_not_forget_newer_thread(buffer_connection):
    import threading
    from moler.device.unixlocal import UnixLocal
    dev = UnixLocal(io_connection=buffer_connection, name="GOTO_THREAD_NEWER")
    newer_thread = threading.Thread(target=lambda: None)
    dev._thread_for_goto_state = newer_thread
    try:
        dev._forget_goto_state_thread()  # Called by a thread that is not the registered one.

        assert dev._thread_for_goto_state is newer_thread
    finally:
        dev._thread_for_goto_state = None
        dev.remove()


def test_device_exchange_io_connection_attaches_new_connection():
    from moler.device.unixlocal import UnixLocal
    from moler.util.devices_SM import get_memory_device_connection
    old_connection = get_memory_device_connection()
    new_connection = get_memory_device_connection()
    dev = UnixLocal(io_connection=old_connection, name="EXCHANGE_ATTACHES_NEW")

    dev.exchange_io_connection(io_connection=new_connection)
    try:
        assert "UNIX_LOCAL" == dev.current_state
        assert dev._prompts_event is not None
        assert new_connection.name == "EXCHANGE_ATTACHES_NEW"
        assert new_connection.moler_connection.name == "EXCHANGE_ATTACHES_NEW"
        assert new_connection.moler_connection.data_logger is dev.device_data_logger
        assert dev.on_connection_made in new_connection._connect_subscribers
        assert dev.on_connection_lost in new_connection._disconnect_subscribers

        new_connection.close()

        assert "NOT_CONNECTED" == dev.current_state
    finally:
        dev.remove()


def test_device_exchange_io_connection_cancels_observers_created_on_old_connection():
    from moler.device.unixlocal import UnixLocal
    from moler.util.devices_SM import get_memory_device_connection
    old_connection = get_memory_device_connection()
    dev = UnixLocal(io_connection=old_connection, name="EXCHANGE_CANCELS_OBSERVERS")
    cmd = dev.get_cmd(cmd_name="ls", cmd_params={"prompt": r"^moler_bash#"}, check_state=False,
                      for_state="UNIX_LOCAL")

    dev.exchange_io_connection(io_connection=get_memory_device_connection())
    try:
        assert cmd.cancelled()
    finally:
        dev.remove()


def test_device_exchange_io_connection_does_not_close_connection_shared_with_neighbour(buffer_connection):
    import mock
    from moler.device.unixlocal import UnixLocal
    from moler.util.devices_SM import get_memory_device_connection
    dev1 = UnixLocal(io_connection=buffer_connection, name="EXCHANGE_SHARED_1")
    dev2 = UnixLocal(io_connection=buffer_connection, name="EXCHANGE_SHARED_2")
    dev1.add_neighbour_device(neighbour_device=dev2, bidirectional=True)
    moler_connection = buffer_connection.moler_connection
    cmd_params = {"prompt": r"^moler_bash#"}
    cmd2 = dev2.get_cmd(cmd_name="ls", cmd_params=cmd_params, check_state=False, for_state="UNIX_LOCAL")

    with mock.patch.object(buffer_connection, "close") as close, \
            mock.patch.object(moler_connection, "shutdown") as shutdown:
        dev2.exchange_io_connection(io_connection=get_memory_device_connection())
        try:
            close.assert_not_called()
            shutdown.assert_not_called()
            assert dev2.on_connection_made not in buffer_connection._connect_subscribers
            assert dev1.on_connection_made in buffer_connection._connect_subscribers
            assert cmd2.cancelled()
            assert moler_connection.data_logger is dev1.device_data_logger
            assert buffer_connection.name == "EXCHANGE_SHARED_1"
            assert moler_connection.name == "EXCHANGE_SHARED_1"
        finally:
            dev2.remove()
            dev1.remove()


def test_device_exchange_io_connection_to_the_same_connection_does_nothing():
    import mock
    from moler.device.unixlocal import UnixLocal
    from moler.util.devices_SM import get_memory_device_connection
    connection = get_memory_device_connection()
    dev = UnixLocal(io_connection=connection, name="EXCHANGE_SAME")

    with mock.patch.object(connection, "close") as close:
        dev.exchange_io_connection(io_connection=connection)
    try:
        close.assert_not_called()
        assert dev.io_connection is connection
        assert connection.moler_connection.is_open()
        assert dev.on_connection_made in connection._connect_subscribers
    finally:
        dev.remove()


def test_devices_sm_get_device_for_existing_device_moves_it_to_new_connection():
    from moler.device import DeviceFactory
    from moler.util.devices_SM import get_device, get_memory_device_connection
    device_output = {
        "UNIX_LOCAL": {
            'su': 'local_root_prompt'
        },
        "UNIX_LOCAL_ROOT": {
            'exit': 'moler_bash#'
        },
    }
    old_connection = get_memory_device_connection()
    new_connection = get_memory_device_connection()
    dev = get_device(name="UNIX_LOCAL", connection=old_connection, device_output=device_output,
                     test_file_path=__file__)
    try:
        same_dev = get_device(name="UNIX_LOCAL", connection=new_connection, device_output=device_output,
                              test_file_path=__file__)

        assert same_dev is dev
        assert dev.io_connection is new_connection
        assert dev.on_connection_lost not in old_connection._disconnect_subscribers
        assert not old_connection.moler_connection.is_open()
        dev.goto_state("UNIX_LOCAL_ROOT")
        assert "UNIX_LOCAL_ROOT" == dev.current_state
        dev.goto_state("UNIX_LOCAL")
        assert "UNIX_LOCAL" == dev.current_state
    finally:
        DeviceFactory.remove_device(device=dev)


# --------------------------- resources ---------------------------


class _ConnectionWithoutUnsubscribe(object):
    """Connection not derived from IOConnection, without unsubscribe methods."""

    def __init__(self, io_connection):
        object.__setattr__(self, "_io_connection", io_connection)

    def __getattr__(self, name):
        if name.startswith("unsubscribe_"):
            raise AttributeError(name)
        return getattr(self._io_connection, name)

    def __setattr__(self, name, value):
        setattr(self._io_connection, name, value)


@pytest.fixture
def configure_net_1_connection():
    import mock
    from moler.config import connections as conn_cfg

    with mock.patch.object(conn_cfg, "default_variant", {}):
        with mock.patch.object(conn_cfg, "named_connections", {}):

            conn_cfg.set_default_variant(io_type='memory', variant="threaded")
            conn_cfg.define_connection(name='net_1', io_type='memory')

            yield
