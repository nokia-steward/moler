# -*- coding: utf-8 -*-
"""
Testing connection observer runner
"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import time
from unittest import mock

import pytest
from moler.threaded_moler_connection import ThreadedMolerConnection
from moler.connection_observer import ConnectionObserver
from moler.event import Event
from moler.command import Command


def test_can_use_runner_as_context_manager(connection_observer,
                                           observer_runner):
    original_shutdown = observer_runner.__class__.shutdown
    shutdown_call_params = []

    def proxy_shutdown(self):
        shutdown_call_params.append(self)
        original_shutdown(self)

    with mock.patch.object(observer_runner.__class__, "shutdown", proxy_shutdown):
        with observer_runner:
            connection_observer.life_status.start_time = time.monotonic()  # must start observer lifetime before runner.submit()
            observer_runner.submit(connection_observer)

    assert observer_runner in shutdown_call_params


def test_time_out_observer_can_set_proper_exception_inside_observer(conn_observer,
                                                                    observer_runner):
    from moler.runner import time_out_observer
    from moler.exceptions import CommandTimeout
    from moler.exceptions import ConnectionObserverTimeout

    if conn_observer.is_command():
        expected_timeout_class = CommandTimeout
    else:
        expected_timeout_class = ConnectionObserverTimeout

    with observer_runner:
        conn_observer.life_status.start_time = time.monotonic()
        observer_runner.submit(conn_observer)
        time_out_observer(conn_observer, timeout=2.3, passed_time=2.32, runner_logger=mock.MagicMock())

    assert conn_observer.done()
    with pytest.raises(expected_timeout_class):
        conn_observer.result()


def test_time_out_observer_sets_exception_inside_observer_before_calling_on_timeout(conn_observer,
                                                                                    observer_runner):
    from moler.runner import time_out_observer
    from moler.exceptions import ConnectionObserverTimeout

    def on_timeout_handler(self):
        with pytest.raises(ConnectionObserverTimeout):
            self.result()

    with mock.patch.object(conn_observer.__class__, "on_timeout", on_timeout_handler):
        with observer_runner:
            conn_observer.life_status.start_time = time.monotonic()
            observer_runner.submit(conn_observer)
            time_out_observer(conn_observer, timeout=2.3, passed_time=2.32, runner_logger=mock.MagicMock())


def test_runner_doesnt_impact_unrised_observer_exception_while_taking_observer_result(connection_observer,
                                                                                      observer_runner):
    from moler.runner import time_out_observer, result_for_runners
    from moler.exceptions import ConnectionObserverTimeout

    with observer_runner:
        connection_observer.life_status.start_time = time.monotonic()  # must start observer lifetime before runner.submit()
        observer_runner.submit(connection_observer)
        time_out_observer(connection_observer, timeout=2.3, passed_time=2.32, runner_logger=mock.MagicMock())

    timeout = connection_observer._exception
    assert timeout in ConnectionObserver._not_raised_exceptions
    try:
        result_for_runners(connection_observer)
    except ConnectionObserverTimeout as timeout:
        assert timeout in ConnectionObserver._not_raised_exceptions


def test_CancellableFuture_str_casting_shows_embedded_future():
    import threading
    from moler.runner import CancellableFuture
    from concurrent.futures import ThreadPoolExecutor

    def fun_with_future_result(delay):
        time.sleep(delay)
        return delay * 2

    executor = ThreadPoolExecutor()
    observer_lock = threading.Lock()
    stop_feeding = threading.Event()
    feed_done = threading.Event()
    connection_observer_future = executor.submit(fun_with_future_result, delay=0.1)
    c_future = CancellableFuture(connection_observer_future, observer_lock, stop_feeding, feed_done)
    connection_observer_future_as_str = str(connection_observer_future)
    c_future_as_str = str(c_future)
    assert c_future_as_str == f"CancellableFuture({connection_observer_future_as_str})"
    executor.shutdown()


def test_CancellableFuture_can_force_cancel_of_embedded_future():
    import threading
    from moler.runner import CancellableFuture
    from concurrent.futures import ThreadPoolExecutor
    from moler.exceptions import MolerException

    executor = ThreadPoolExecutor()
    observer_lock = threading.Lock()
    stop_feeding = threading.Event()
    feed_done = threading.Event()

    def fun_with_future_result(delay, should_stop):
        start_time = time.monotonic()
        while not should_stop.is_set() and ((time.monotonic() - start_time) < delay):
            time.sleep(0.01)
        return delay * 2

    connection_observer_future = executor.submit(fun_with_future_result, delay=0.5, should_stop=stop_feeding)
    c_future = CancellableFuture(connection_observer_future, observer_lock,
                                 stop_feeding, feed_done, stop_timeout=0.2)
    time.sleep(0.1)  # let thread switch happen
    assert "state=running" in str(connection_observer_future)
    with pytest.raises(MolerException) as exc:
        c_future.cancel(no_wait=False)
    time.sleep(0.1)
    assert "state=finished" in str(connection_observer_future)
    assert "Failed to stop thread-running function within 0.2 sec" in str(exc.value)


def test_ThreadPoolExecutorRunner_logs_about_reused_executor():
    import logging
    from concurrent.futures import ThreadPoolExecutor
    from moler.runner import ThreadPoolExecutorRunner

    logger = logging.getLogger('moler.runner.thread-pool')
    external_executor = ThreadPoolExecutor()
    with mock.patch.object(logger, "debug") as log_debug:
        ThreadPoolExecutorRunner(executor=external_executor)

    assert mock.call(f"reusing provided executor {external_executor!r}") in log_debug.mock_calls
    external_executor.shutdown()


# --------------------------- resources ---------------------------


@pytest.fixture()
def observer_runner():
    from moler.runner import ThreadPoolExecutorRunner
    runner = ThreadPoolExecutorRunner()
    return runner


class NetworkDownDetector(ConnectionObserver):
    def __init__(self, connection=None, runner=None):
        super(NetworkDownDetector, self).__init__(connection=connection, runner=runner)
        self.all_data_received = []

    def data_received(self, data, recv_time):
        """
        Awaiting change like:
        64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms
        ping: sendmsg: Network is unreachable
        """
        self.all_data_received.append(data)
        if not self.done():
            if "Network is unreachable" in data:
                when_detected = time.monotonic()
                self.set_result(result=when_detected)


class MyEvent(Event):
    def data_received(self, data, recv_time):
        pass

    def pause(self):
        pass

    def resume(self):
        pass


class MyCommand(Command):
    def __init__(self, connection=None, runner=None):
        super(MyCommand, self).__init__(connection=connection, runner=runner)
        self.command_string = 'hi'

    def data_received(self, data, recv_time):
        pass


@pytest.fixture()
def connection_observer():
    moler_conn = ThreadedMolerConnection()
    observer = NetworkDownDetector(connection=moler_conn)
    return observer


@pytest.fixture(params=['generic_observer', 'event', 'command'])
def conn_observer(request):
    moler_conn = ThreadedMolerConnection(how2send=mock.MagicMock())
    if request.param == 'generic_observer':
        observer = NetworkDownDetector(connection=moler_conn)
    elif request.param == 'event':
        observer = MyEvent(connection=moler_conn)
    elif request.param == 'command':
        observer = MyCommand(connection=moler_conn)
    return observer
