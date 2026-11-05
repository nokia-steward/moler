# -*- coding: utf-8 -*-

__author__ = 'Grzegorz Latuszek, Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com'

import importlib
import time

import pytest

from moler.threaded_moler_connection import ThreadedMolerConnection
from moler.connection_observer import ConnectionObserver
from moler.helpers import instance_id
import datetime


def test_connection_observer_instance_is_callable(connection_observer_major_base_class):
    """Future-like objects are callable"""
    assert callable(connection_observer_major_base_class)


def test_calling_start_on_connection_observer_returns_itself(do_nothing_connection_observer__for_major_base_class,
                                                             connection_to_remote):
    """
    connection_observer.start() is asynchronous run. Return itself to allow for acting on it.
    Simplest (stupid) case: connection_observer.start().await_done()
    """
    connection_observer = do_nothing_connection_observer__for_major_base_class
    connection_observer.connection = connection_to_remote.moler_connection
    assert connection_observer == connection_observer.start()
    connection_observer.cancel()


def test_can_retrieve_connection_observer_start_time(do_nothing_connection_observer__for_major_base_class,
                                                     connection_to_remote):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    connection_observer.connection = connection_to_remote.moler_connection
    time1 = time.monotonic()
    connection_observer.start()
    time2 = time.monotonic()
    assert connection_observer.start_time >= time1
    assert connection_observer.start_time <= time2


# str representation of class instances may be specific for given class - means: each derived class
# of ConnectionObserver may define its own __str__ conversion (or reuse the one from base class).
# But that doesn't break connection-observer API conformance - it is just textual representation.
# So, we don't make this test parametrized - we just check __str__ of ConnectionObserver
def test_str_conversion_of_connection_observer_object():
    """
    String conversion shows class of connection_observer object
    and id to allow for differentiating between multiple instances of same connection_observer
    """

    class TransferCounter(ConnectionObserver):
        def __init__(self, connection=None):
            super(TransferCounter, self).__init__(connection=connection)
            self.received_bytes = 0

        def data_received(self, data, recv_time):
            self.received_bytes += len(data)

    transfer_received = TransferCounter()
    observer_id = instance_id(transfer_received)
    assert f'TransferCounter(id:{observer_id})' == str(transfer_received)


# repr - same analysis as for str above
def test_repr_conversion_of_connection_observer_object():
    """
    repr() conversion shows same output as str()
    plus embedded connection used by connection_observer
    """

    class SshConnection(object):
        def __init__(self, target_host):
            self.target_host = target_host

        def __repr__(self):
            return f"<SshConnection({self.target_host})>"

        def get_runner(self):
            return None

    class TransferCounter(ConnectionObserver):
        def __init__(self, connection=None):
            super(TransferCounter, self).__init__(connection=connection)
            self.received_bytes = 0

        def data_received(self, data, recv_time):
            self.received_bytes += len(data)

    conn = SshConnection(target_host='127.0.0.1')
    transfer_received = TransferCounter(connection=conn)
    observer_id = instance_id(transfer_received)

    # repr(conn_observer) uses repr(connection) which is used by that observer
    assert f'TransferCounter(id:{observer_id}, using <SshConnection(127.0.0.1)>)' == repr(transfer_received)

    transfer_received.connection = None
    assert f'TransferCounter(id:{observer_id}, using <NO CONNECTION>)' == repr(transfer_received)


def test_connection_observer_stores_connection_it_is_operating_on(do_nothing_connection_observer__for_major_base_class):
    """Observers need to read from connection"""
    connection_observer_instance = do_nothing_connection_observer__for_major_base_class
    assert hasattr(connection_observer_instance, "connection")


def test_connection_observer_can_be_given_connection_it_is_operating_on(
        do_nothing_connection_observer_class__for_major_base_class):
    """We want ability to set it during construction time or later via direct member set"""
    connection_observer_class = do_nothing_connection_observer_class__for_major_base_class

    class Connection(object):
        pass

        def get_runner(self):
            return None

    conn = Connection()

    observer_with_connection_from_startup = connection_observer_class(connection=conn)
    assert observer_with_connection_from_startup.connection == conn

    observer_with_later_set_connection = connection_observer_class()
    observer_with_later_set_connection.connection = conn
    assert observer_with_later_set_connection.connection == conn


def test_connection_is_required_to_start_connection_observer(do_nothing_connection_observer__for_major_base_class):
    from moler.exceptions import NoConnectionProvided
    connection_observer = do_nothing_connection_observer__for_major_base_class
    # no connection at construction nor later assignment '.connection = ...'
    assert not connection_observer.connection

    with pytest.raises(NoConnectionProvided):
        connection_observer.start()  # start background-run of connection_observer-future
        connection_observer.await_done()


def test_connection_observer_is_running_after_it_calls_start(do_nothing_connection_observer__for_major_base_class,
                                                             connection_to_remote):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    assert not connection_observer.running()
    connection_observer.connection = connection_to_remote.moler_connection
    connection_observer.start()  # start background-run of connection_observer-future
    assert connection_observer.running()
    connection_observer.cancel()


def test_connection_observer_is_not_running_after_it_is_done(do_nothing_connection_observer__for_major_base_class,
                                                             connection_to_remote):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    connection_observer.connection = connection_to_remote.moler_connection
    connection_observer.start()  # start background-run of connection_observer-future
    assert connection_observer.running()
    connection_observer.cancel()  # one of ways to make it done; others are tested elsewhere
    assert not connection_observer.running()


def test_connection_observer_call_passes_positional_arguments_to_start(
        do_nothing_connection_observer_class__for_major_base_class):
    called_with_params = []

    class ParametrizedObserver(do_nothing_connection_observer_class__for_major_base_class):
        def start(self, timeout, param1, param2):
            called_with_params.append(param1)
            called_with_params.append(param2)

    connection_observer = ParametrizedObserver()

    connection_observer.start(1., 23, "foo")

    assert called_with_params == [23, "foo"]
    connection_observer.cancel()


def test_connection_observer_call_passes_keyword_arguments_to_start(
        do_nothing_connection_observer_class__for_major_base_class):
    called_with_params = []

    class ParametrizedObserver(do_nothing_connection_observer_class__for_major_base_class):
        def start(self, timeout, param1, param2):
            called_with_params.append(param1)
            called_with_params.append(param2)

    observer = ParametrizedObserver()

    observer.start(timeout=1.0, param2="foo", param1=23)

    assert called_with_params == [23, "foo"]
    observer.cancel()


def test_connection_observer_is_done_after_setting_result(do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    assert not connection_observer.done()
    # We start feeding connection-observer with data coming from connection
    # till it decides "ok, I've found what I was looking for"
    # and it internally sets the result
    connection_observer.set_result(14361)
    assert connection_observer.done()


def test_connection_observer_is_done_after_setting_exception(do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    assert not connection_observer.done()
    # We start feeding connection-observer with data coming from connection
    # till it decides "ok, I've found something what indicates error-condition"
    #                  or it catches exception of it's internal processing
    # and it internally sets the exception
    connection_observer.set_exception(IndexError())
    assert connection_observer.done()

    ConnectionObserver.get_unraised_exceptions()


def test_connection_observer_is_done_after_cancelling(do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    assert not connection_observer.done()
    # We start feeding connection-observer with data coming from connection
    # but before it finds what it is waiting for
    # its user cancels it
    connection_observer.cancel()
    assert connection_observer.done()


def test_connection_observer_is_cancelled_after_cancelling(do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    assert not connection_observer.cancelled()
    # We start feeding connection-observer with data coming from connection
    # but before it finds what it is waiting for
    # its user cancels it
    connection_observer.cancel()
    assert connection_observer.cancelled()


def test_cancel_returns_false_if_connection_observer_is_cancelled(do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    # We start feeding connection-observer with data coming from connection
    # but before it finds what it is waiting for
    # its user cancels it
    connection_observer.cancel()
    # after that user cancels it again
    assert connection_observer.cancel() is False


def test_cancel_returns_false_if_connection_observer_is_done(do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    # We start feeding connection-observer with data coming from connection
    # till it decides "ok, I've found what I was looking for"
    # and it internally sets the result
    connection_observer.set_result(14361)  # connection_observer internally sets the result
    # after that its user cancels it
    assert connection_observer.cancel() is False


def test_cancel_returns_true_if_connection_observer_is_not_cancelled_nor_done(
        do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    # We start feeding connection-observer with data coming from connection
    # but before it finds what it is waiting for
    # its user cancels it
    assert connection_observer.cancel() is True


def test_can_retrieve_connection_observer_result_after_setting_result(
        do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    # We start feeding connection-observer with data coming from connection
    # till it decides "ok, I've found what I was looking for"
    # and it internally sets the result
    connection_observer.set_result(14361)
    assert connection_observer.result() == 14361


def test_setting_result_multiple_times_raises_ResultAlreadySet(do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    from moler.exceptions import ResultAlreadySet
    # We start feeding connection-observer with data coming from connection
    # till it decides "ok, I've found what I was looking for"
    # and it internally sets the result
    connection_observer.set_result(14361)
    with pytest.raises(ResultAlreadySet) as error:
        connection_observer.set_result(78990)  # connection_observer internally tries to overwrite the result

    assert error.value.connection_observer == connection_observer
    assert str(error.value) == f'for {str(connection_observer)}'


def test_setting_result_after_set_exception_raises_ResultAlreadySet(do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    from moler.exceptions import ResultAlreadySet
    # set_exception() and set_result() may come from different threads (runner/external-io) - so,
    # we must be secured against race
    exc = Exception("exception in runner")
    connection_observer.set_exception(exc)
    with pytest.raises(ResultAlreadySet) as error:
        connection_observer.set_result(78990)  # trial to overwrite exception with the result

    assert error.value.connection_observer == connection_observer
    assert str(error.value) == f'for {str(connection_observer)}'


def test_calling_result_on_cancelled_connection_observer_raises_NoResultSinceCommandCancelled(
        do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    from moler.exceptions import NoResultSinceCancelCalled
    # We start feeding connection-observer with data coming from connection
    # but before it finds what it is waiting for
    # its user cancels it
    connection_observer.cancel()
    with pytest.raises(NoResultSinceCancelCalled) as error:
        connection_observer.result()

    assert error.value.connection_observer == connection_observer
    assert str(error.value) == f'for {str(connection_observer)}'


def test_calling_result_on_exception_broken_connection_observer_raises_that_exception(
        do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    # We start feeding connection-observer with data coming from connection
    # till it decides "ok, I've found something what indicates error-condition"
    #                  or it catches exception of it's internal processing
    # and it internally sets the exception
    index_err = IndexError()
    connection_observer.set_exception(index_err)
    with pytest.raises(IndexError) as error:
        connection_observer.result()
    assert error.value == index_err

    ConnectionObserver.get_unraised_exceptions()


def test_calling_result_while_result_is_yet_not_available_raises_CommandResultNotAvailableYet(
        do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    from moler.exceptions import ResultNotAvailableYet
    # We start feeding connection-observer with data coming from connection
    # but before it finds what it is waiting for - user asks for result
    with pytest.raises(ResultNotAvailableYet) as error:
        connection_observer.result()

    assert error.value.connection_observer == connection_observer
    assert str(error.value) == f'for {str(connection_observer)}'


def test_awaiting_done_on_already_done_connection_observer_immediately_returns_result(
        do_nothing_connection_observer__for_major_base_class):
    connection_observer = do_nothing_connection_observer__for_major_base_class
    # We start feeding connection-observer with data coming from connection
    # till it decides "ok, I've found what I was looking for"
    # and it internally sets the result
    connection_observer.set_result(14361)
    result_set_time = time.monotonic()
    assert connection_observer.await_done() == 14361
    assert time.monotonic() - result_set_time < 0.01  # our immediately ;-)


def test_awaiting_done_on_not_running_connection_observer_raises_ConnectionObserverNotStarted(
        do_nothing_connection_observer__for_major_base_class):
    from moler.exceptions import ConnectionObserverNotStarted
    connection_observer = do_nothing_connection_observer__for_major_base_class
    with pytest.raises(ConnectionObserverNotStarted) as error:
        connection_observer.await_done()
    assert error.value.connection_observer == connection_observer
    assert str(error.value) == f'for {str(connection_observer)}'


def test_connection_observer_has_data_received_api(connection_observer_major_base_class):
    connection_observer_class = connection_observer_major_base_class
    assert hasattr(connection_observer_class, "data_received")

    # base class is abstract - forces derived to define data_received()
    # only derived ones can have logic "what to do with incoming data"
    with pytest.raises(TypeError) as error:
        hasattr(connection_observer_class(), "data_received")
    assert "Can't instantiate abstract class {} with abstract method".format(  # <3.12
        connection_observer_class.__name__) in str(error.value) or\
           "Can't instantiate abstract class {} without an implementation for abstract method".format(
        connection_observer_class.__name__) in str(error.value)  # 3.12
    assert "data_received" in str(error.value)

    # example of derived connection_observer implementing it's "data consumption logic"
    class AnyResponseObserver(connection_observer_class):
        def data_received(self, data, recv_time):
            if not self.done():
                self.set_result(result=data)  # any first call to data_received sets result of connection_observer

    assert hasattr(AnyResponseObserver(), "data_received")


def test_connection_observer_consumes_data_via_data_received_in_order_to_produce_result(
        connection_observer_major_base_class):
    # any feeder of any runner should use .data_received() to let observer consume data of connection:
    def feeder(observer):
        #            example output of 'du -s /home/greg'
        for line in ['7538128    /home/greg', 'ute@debian:~$']:  # here our "virtual connection" is just list
            observer.data_received(line, datetime.datetime.now())

    class DiskUsageObserver(connection_observer_major_base_class):
        def data_received(self, data, recv_time):
            if not self.done():
                self.set_result(result=data)

    disk_usage_observer = DiskUsageObserver()

    # We start feeding connection-observer with data coming from connection
    feeder(disk_usage_observer)  # disk_usage_observer is done after first data passed to data_received()

    assert disk_usage_observer.done()
    assert disk_usage_observer.result() == '7538128    /home/greg'


def test_connection_observer_parses_data_inside_data_received_in_order_to_produce_result(
        connection_observer_major_base_class):
    # any observer should do its parsing (if any needed) inside .data_received() or it should be called from within .data_received()
    def feeder(observer):
        for line in ['7538128    /home/greg', 'greg@debian:~$']:
            observer.data_received(line, datetime.datetime.now())

    class DiskUsageObserver(connection_observer_major_base_class):
        def __init__(self):
            """observing output of 'du -s /home/greg'"""
            super(DiskUsageObserver, self).__init__()

        def data_received(self, data, recv_time):
            # 7538128    /home/greg
            if not self.done():
                size, path = data.split()
                self.set_result(result={'size': int(size), 'path': path})

    disk_usage_observer = DiskUsageObserver()

    # We start feeding connection-observer with data coming from connection
    feeder(disk_usage_observer)

    assert disk_usage_observer.done()
    disk_usage_parsed_output = {'size': 7538128, 'path': '/home/greg'}
    assert disk_usage_observer.result() == disk_usage_parsed_output


def test_connection_observer_one_exception():
    ConnectionObserver.get_unraised_exceptions(True)
    time.sleep(0.1)
    from moler.cmd.unix.ls import Ls
    from moler.exceptions import CommandTimeout
    cmd = Ls(None)
    none_exceptions = ConnectionObserver.get_unraised_exceptions(True)
    assert 0 == len(none_exceptions)
    cmd.set_exception(CommandTimeout(cmd, 0.1))
    cmd._is_done = True
    active_exceptions = ConnectionObserver.get_unraised_exceptions(True)
    assert 1 == len(active_exceptions)
    try:
        cmd.result()
    except CommandTimeout:
        pass
    none_exceptions = ConnectionObserver.get_unraised_exceptions(True)
    assert 0 == len(none_exceptions)
    none_exceptions = ConnectionObserver.get_unraised_exceptions(True)
    assert 0 == len(none_exceptions)


def test_connection_observer_exception_do_not_remove():
    time.sleep(0.1)
    ConnectionObserver.get_unraised_exceptions(True)
    from moler.cmd.unix.ls import Ls
    from moler.exceptions import CommandTimeout
    from moler.exceptions import WrongUsage
    cmd = Ls(None)
    none_exceptions = ConnectionObserver.get_unraised_exceptions(True)
    assert 0 == len(none_exceptions)
    cmd.set_exception(CommandTimeout(cmd, 0.1))
    cmd._is_done = True
    active_exceptions = ConnectionObserver.get_unraised_exceptions(False)
    assert 1 == len(active_exceptions)
    cmd = Ls(None)
    ctoe = CommandTimeout(cmd, 0.1)
    cwue = WrongUsage(cmd, "Another exception")
    cmd.set_exception(ctoe)
    cmd._is_done = True
    cmd.set_exception(cwue)
    active_exceptions = ConnectionObserver.get_unraised_exceptions(False)
    assert ctoe == active_exceptions[1]
    assert 2 == len(active_exceptions)
    active_exceptions = ConnectionObserver.get_unraised_exceptions(True)
    assert 2 == len(active_exceptions)
    none_exceptions = ConnectionObserver.get_unraised_exceptions(True)
    assert 0 == len(none_exceptions)


# --------------------------- resources ---------------------------


@pytest.fixture(params=['connection_observer.ConnectionObserver', 'command.Command'])
def connection_observer_major_base_class(request):
    module_name, class_name = request.param.rsplit('.', 1)
    module = importlib.import_module(f'moler.{module_name}')
    klass = getattr(module, class_name)
    yield klass
    # remove exceptions collected inside ConnectionObserver
    ConnectionObserver.get_unraised_exceptions(remove=True)


def do_nothing_connection_observer_class(base_class):
    """Observer class that can be instantiated (overwritten abstract methods); uses different base class"""

    class DoNothingObserver(base_class):
        def data_received(self, data, recv_time):  # we need to overwrite it since it is @abstractmethod
            pass  # ignore incoming data

    return DoNothingObserver


@pytest.fixture
def do_nothing_connection_observer_class__for_major_base_class(connection_observer_major_base_class):
    klass = do_nothing_connection_observer_class(base_class=connection_observer_major_base_class)
    return klass


@pytest.fixture
def do_nothing_connection_observer__for_major_base_class(do_nothing_connection_observer_class__for_major_base_class):
    from moler.command import Command
    instance = do_nothing_connection_observer_class__for_major_base_class()
    if isinstance(instance, Command):
        instance.command_string = 'dummy command'  # required by .start() of Command
    return instance


@pytest.fixture
def connection_to_remote():
    """
    Any external-IO connection that embeds Moler-connection
    Alows to check if data send from command has reached remote side via:
    `data in conn.remote_endpoint()`
    """
    from moler.io.raw.memory import FifoBuffer

    class RemoteConnection(FifoBuffer):
        def remote_endpoint(self):
            """Simulate remote endpoint that gets data"""
            return self.buffer

        def get_runner(self):
            """Get default runner for this connection."""
            return None

    ext_io = RemoteConnection(moler_connection=ThreadedMolerConnection(encoder=lambda data: data.encode("utf-8"),
                                                                       decoder=lambda data: data.decode("utf-8")))
    return ext_io
