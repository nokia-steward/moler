# -*- coding: utf-8 -*-

"""Base class for all events and commands that are to be observed on connection."""

__author__ = "Grzegorz Latuszek, Marcin Usielski, Michal Ernst"
__copyright__ = "Copyright (C) 2018-2026 Nokia"
__email__ = (
    "grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com, michal.ernst@nokia.com"
)

import logging
import threading
import time
import traceback
from abc import ABCMeta, abstractmethod
from typing import Optional

from moler.abstract_moler_connection import AbstractMolerConnection
from moler.command_scheduler import CommandScheduler
from moler.exceptions import (
    ConnectionObserverNotStarted,
    ConnectionObserverTimeout,
    NoConnectionProvided,
    NoResultSinceCancelCalled,
    ResultAlreadySet,
    ResultNotAvailableYet,
    WrongUsage,
)
from moler.helpers import (
    ClassProperty,
    camel_case_to_lower_case_underscore,
    copy_list,
    instance_id,
)
from moler.runner import ConnectionObserverRunner
from moler.runner_factory import get_runner
from moler.util.connection_observer import exception_stored_if_not_main_thread
from moler.util.connection_observer_life_status import ConnectionObserverLifeStatus
from moler.util.loghelper import log_into_logger


class ConnectionObserver(metaclass=ABCMeta):

    """Base class for all events and commands that are to be observed on connection."""

    _not_raised_exceptions = []  # list of dict: "exception" and "time"
    _exceptions_lock = threading.Lock()

    def __init__(
        self,
        connection: Optional[AbstractMolerConnection] = None,
        runner: Optional[ConnectionObserverRunner] = None,
    ):
        """
        Create instance of ConnectionObserver class
        :param connection: connection used to receive data awaited for
        """
        super(ConnectionObserver, self).__init__()
        self.life_status: ConnectionObserverLifeStatus = ConnectionObserverLifeStatus()
        self.connection: AbstractMolerConnection = connection
        self.runner: ConnectionObserverRunner = self._get_runner(runner=runner)
        self._result = None
        self._exception: Optional[Exception] = None
        self._exception_stack_msg: Optional[str] = None

        self._future = None

        self.device_logger = logging.getLogger(
            f"moler.{self.get_logger_name()}"
        )
        self.logger = logging.getLogger(
            f"moler.connection.{self.get_logger_name()}"
        )

    def _get_runner(
        self, runner: Optional[ConnectionObserverRunner]
    ) -> ConnectionObserverRunner:
        """

        :param runner: Runner
        :return: Runner instance
        """
        return_runner = runner
        if return_runner is None and self.connection is not None:
            return_runner = self.connection.get_runner()
        if return_runner is None:
            return_runner = get_runner()
        return return_runner

    def __str__(self):
        return f"{self.__class__.__name__}(id:{instance_id(self)})"

    __base_str = __str__

    def __repr__(self):
        cmd_str = self.__str__()
        connection_str = "<NO CONNECTION>"
        if self.connection:
            connection_str = repr(self.connection)
        return f"{cmd_str[:-1]}, using {connection_str})"

    # pylint: disable=keyword-arg-before-vararg
    def __call__(self, timeout=None, *args, **kwargs):
        """
        Run connection-observer in foreground
        till it is done or timeouted

        CAUTION: if you call it from asynchronous code (async def) you may block events loop for long time.
        You should rather await it via:
        result = await connection_observer
        or (to have timeout)
        result = await asyncio.wait_for(connection_observer, timeout=10)
        or you may delegate blocking call execution to separate thread,
        see: https://pymotw.com/3/asyncio/executors.html
        """
        self.start(timeout, *args, **kwargs)
        # started_observer = self.start(timeout, *args, **kwargs)
        # if started_observer:
        #     return started_observer.await_done(*args, **kwargs)
        return self.await_done()
        # TODO: raise ConnectionObserverFailedToStart

    @property
    def _is_done(self) -> bool:
        """Return if observer is done."""
        return self.life_status.is_done

    @_is_done.setter
    def _is_done(self, value: bool):
        """Set if observer is done."""
        self.life_status.is_done = value
        if value:
            CommandScheduler.dequeue_running_on_connection(connection_observer=self)

    @property
    def _is_cancelled(self) -> bool:
        """Return if observer is cancelled."""
        return self.life_status.is_cancelled

    @_is_cancelled.setter
    def _is_cancelled(self, value: bool):
        """Set if observer is cancelled."""
        self.life_status.is_cancelled = value

    @property
    def terminating_timeout(self) -> float:
        """Return timeout for observer termination."""
        return self.life_status.terminating_timeout

    @terminating_timeout.setter
    def terminating_timeout(self, value: float):
        """Set timeout for observer termination."""
        self.life_status.terminating_timeout = value

    @property
    def timeout(self) -> float:
        """Return timeout for observer."""
        return self.life_status.timeout

    @timeout.setter
    def timeout(self, value: float):
        # levels_to_go_up=2 : extract caller info to log where .timeout=XXX has been called from
        self._log(
            logging.DEBUG,
            f"Setting {ConnectionObserver.__base_str(self)} timeout to {value} [sec]",
            levels_to_go_up=2,
        )
        self.life_status.timeout = value

    @property
    def start_time(self) -> float:
        """Return time when observer has been started."""
        return self.life_status.start_time

    def get_logger_name(self) -> str:
        """Return logger name for this connection-observer"""
        if self.connection and hasattr(self.connection, "name"):
            return self.connection.name
        return self.__class__.__name__

    # pylint: disable=keyword-arg-before-vararg
    def start(self, timeout: Optional[float] = None, *args, **kwargs):
        """Start background execution of connection-observer."""
        with exception_stored_if_not_main_thread(self):
            if timeout:
                self.timeout = timeout
            self._validate_start(*args, **kwargs)
            # After start we treat it as started even if it's underlying
            # parallelism machinery (threads, coroutines, ...) has not started yet
            # (thread didn't get control, coro didn't start in async-loop)
            # That is so, since observer lifetime starts with it's timeout-clock
            # and timeout is counted from calling observer.start()
            self.life_status._is_running = True  # pylint: disable=protected-access
            self.life_status.start_time = time.monotonic()
            # Besides not started parallelism machinery causing start-delay
            # we can have start-delay caused by commands queue on connection
            # (can't submit command to background-run till previous stops running)
            CommandScheduler.enqueue_starting_on_connection(connection_observer=self)
            # Above line will set self._future when it is possible to submit
            # observer to background-run (observer not command, or empty commands queue)
            # or setting self._future will be delayed by nonempty commands queue.
        return self

    # pylint: disable-next=unused-argument
    def _validate_start(self, *args, **kwargs) -> None:
        # check base class invariants first
        if self.done():
            raise WrongUsage(
                f"You can't run same {self} multiple times. It is already done."
            )
        if not self.connection:
            # only if we have connection we can expect some data on it
            # at the latest "just before start" we need connection
            raise NoConnectionProvided(self)
        # ----------------------------------------------------------------------
        # We intentionally do not check if connection is open here.
        # In such case net result anyway will be failed/timeouted observer -
        # - so, user will need to investigate "why".
        # Checking connection state would benefit in early detection of:
        # "error condition - no chance to succeed since connection is closed".
        # However, drawback is a requirement on connection to have is_open() API
        # We choose minimalistic dependency over better troubleshooting support.
        # ----------------------------------------------------------------------
        if self.timeout <= 0.0:
            raise ConnectionObserverTimeout(
                self, self.timeout, "before run", "timeout is not positive value"
            )

    def __iter__(self):
        """
        Implement iterator protocol to support 'yield from' in @asyncio.coroutine
        :return:
        """
        if self._future is None:
            self.start()
        assert self._future is not None
        return self.runner.wait_for_iterator(self, self._future)

    def __await__(self):
        """
        Await completion of connection-observer.

        Allows to use Python3 'await' syntax

        According to https://www.python.org/dev/peps/pep-0492/#await-expression
        it is a SyntaxError to use await outside of an async def function.
        :return:
        """
        # We may have already started connection_observer:
        #    connection_observer = SomeObserver()
        #    connection_observer.start()
        # then we await it via:
        #    result = await connection_observer
        # but above notation in terms of Python3 async code may also mean "start it and await completion", so it may
        # look like:
        #    connection_observer = SomeObserver()
        #    result = await connection_observer
        return self.__iter__()

    def await_done(self, timeout: Optional[float] = None):
        """
        Await completion of connection-observer.

        CAUTION: if you call it from asynchronous code (async def) you may block events loop for long time.
        You should rather await it via:
        result = await connection_observer
        or (to have timeout)
        result = await asyncio.wait_for(connection_observer, timeout=10)
        or you may delegate blocking call execution to separate thread,
        see: https://pymotw.com/3/asyncio/executors.html

        :param timeout:
        :return: observer result
        """
        if self.done():
            return self.result()
        with exception_stored_if_not_main_thread(self):
            if not self.life_status._is_running:  # pylint: disable=protected-access
                raise ConnectionObserverNotStarted(self)
            # check if already is running
            self.runner.wait_for(
                connection_observer=self,
                connection_observer_future=self._future,
                timeout=timeout,
            )
        return self.result()

    def cancel(self) -> bool:
        """Cancel execution of connection-observer."""
        # TODO: call cancel on runner to stop background run of connection-observer
        if self.cancelled() or self.done():
            return False
        self._is_cancelled = True
        self._is_done = True
        return True

    def set_end_of_life(self) -> None:
        """
        Set end of life of object. Dedicated for runners only!

        :return: None
        """
        self._is_done = True

    def cancelled(self) -> bool:
        """Return True if the connection-observer has been cancelled."""
        return self._is_cancelled

    def running(self) -> bool:
        """Return True if the connection-observer is currently executing."""
        if self.done() and self.life_status._is_running:  # pylint: disable=protected-access
            self.life_status._is_running = False  # pylint: disable=protected-access
        return self.life_status._is_running  # pylint: disable=protected-access

    def done(self) -> bool:
        """Return True if the connection-observer is already done."""
        return self._is_done

    def set_result(self, result) -> None:
        """Should be used to set final result"""
        if self.done():
            raise ResultAlreadySet(self)
        self._result = result
        self._is_done = True

    def connection_closed_handler(self) -> None:
        """
        Called by Moler (ThreadedMolerConnection) when connection is closed.

        :return: None
        """
        if not self.done():
            connection_name = self.get_logger_name()
            msg = f"'{self}' is not done but connection '{connection_name}' is about to be closed."
            ex = WrongUsage(msg)
            self.set_exception(ex)
        self.cancel()

    @abstractmethod
    def data_received(self, data, recv_time):
        """
        Entry point where feeders pass data read from connection
        Here we perform data parsing to conclude in result setting.

        :param data: List of strings sent by device.
        :param recv_time: time stamp with the moment when the data was read from connection.  Time is given as
         datetime.datetime instance.
        :return: None
        """

    def set_exception(self, exception: Exception) -> None:
        """
        Should be used to indicate some failure during observation.

        :param exception: Exception to set
        :return: None
        """
        self._set_exception_without_done(exception)
        self._is_done = True

    def _set_exception_without_done(self, exception: Exception) -> None:
        """
        Should be used to indicate some failure during observation. This method does not finish connection observer
        object!

        :param exception: exception to set
        :return: None
        """
        mg = traceback.format_list(traceback.extract_stack()[:-3] + traceback.extract_tb(exception.__traceback__))
        stack_msg = f"{''.join(mg)}\n  {exception.__class__} {exception}"

        if self._is_done:
            self._log(
                logging.WARNING,
                f"Attempt to set exception {exception!r} on already done {self}",
                levels_to_go_up=2,
            )
            self._log(
                logging.WARNING,
                f"Stack for unsuccessful set exception: {stack_msg}",
            )

            return
        ConnectionObserver._change_unraised_exception(
            new_exception=exception, observer=self, stack_msg=stack_msg
        )
        self._log(
            logging.INFO,
            f"{self.__class__.__module__}.{self} has set exception {exception!r}",
            levels_to_go_up=2,
        )
        self._log(
            logging.WARNING, f"Stack for successful set exception: {stack_msg}"
        )

    def result(self):
        """Retrieve final result of connection-observer"""
        with ConnectionObserver._exceptions_lock:
            ConnectionObserver._log_unraised_exceptions(self)
            if self._exception is not None:
                exception = self._exception
                if exception in ConnectionObserver._not_raised_exceptions:
                    ConnectionObserver._not_raised_exceptions.remove(exception)
                self._log(
                    logging.INFO,
                    f"Stack stored with the exception: {self._exception_stack_msg}",
                )
                raise exception
        if self.cancelled():
            raise NoResultSinceCancelCalled(self)
        if not self.done():
            raise ResultNotAvailableYet(self)
        return self._result

    def on_timeout(self) -> None:
        """Callback called when observer times out"""
        self._log_timeout()

    def _log_timeout(self) -> None:
        """Log timeout message. Used for logging."""
        msg = self._get_timeout_msg()
        self._log(lvl=logging.INFO, msg=msg, levels_to_go_up=2)

    def _get_timeout_msg(self) -> str:
        """Return message about timeout. Used for logging."""
        msg = ""
        for attribute_name in sorted(self.__dict__.keys()):
            if msg:
                msg = f"{msg}, '{attribute_name}':'{self.__dict__[attribute_name]}'"
            else:
                msg = f"Timeout when '{attribute_name}':'{self.__dict__[attribute_name]}'"
        return msg

    def is_command(self) -> bool:
        """
        :return: True if instance of ConnectionObserver is a command. False if not a command.
        """
        return False

    def extend_timeout(self, timedelta: float) -> None:
        """
        Extend timeout by timedelta seconds.

        :param timedelta: The time to extend the timeout by.
        :return: None
        """
        # TODO: probably API to remove since we have runner tracking .timeout=XXX
        prev_timeout = self.timeout
        self.timeout = self.timeout + timedelta
        msg = f"Extended timeout from {prev_timeout:.2f} with delta {timedelta:.2f} to {self.timeout:.2f}"
        self.runner.timeout_change(timedelta)
        self._log(logging.INFO, msg)

    def on_inactivity(self) -> None:
        """
        Callback called when no data is received on connection within self.life_status.inactivity_timeout seconds

        :return: None
        """

    @ClassProperty
    def observer_name(self) -> str:
        """
        Return the name of the observer.
        """
        name = camel_case_to_lower_case_underscore(self.__name__)
        return name

    @staticmethod
    def get_unraised_exceptions(remove: bool = True) -> list:
        """
        Return list of unraised exceptions.

        :param remove: If True, remove the exceptions from the list. Defaults to True.
        :return: list of unraised exceptions.
        """
        with ConnectionObserver._exceptions_lock:
            if remove:
                list_of_exceptions = ConnectionObserver._not_raised_exceptions
                ConnectionObserver._not_raised_exceptions = []
            else:
                list_of_exceptions = copy_list(ConnectionObserver._not_raised_exceptions)
            return list_of_exceptions

    @staticmethod
    def _change_unraised_exception(new_exception: Exception, observer, stack_msg: str) -> None:
        """
        Change the unraised exception for the given observer.

        :param  new_exception: The new exception to be set.
        :param  observer: The observer object.
        :param  stack_msg: The stack message associated with the exception.

        return: None
        """
        with ConnectionObserver._exceptions_lock:
            old_exception = observer._exception  # pylint: disable=protected-access
            ConnectionObserver._log_unraised_exceptions(observer)
            if old_exception:
                observer._log(  # pylint: disable=protected-access
                    logging.DEBUG,
                    f"{observer} has overwritten exception. From {old_exception!r} to {new_exception!r}",
                )
                if old_exception in ConnectionObserver._not_raised_exceptions:
                    ConnectionObserver._not_raised_exceptions.remove(old_exception)
                else:
                    observer._log(  # pylint: disable=protected-access
                        logging.DEBUG,
                        f"{observer}: cannot find exception {old_exception!r} in _not_raised_exceptions.",
                    )
                    ConnectionObserver._log_unraised_exceptions(observer)

            ConnectionObserver._not_raised_exceptions.append(new_exception)
            observer._exception = new_exception  # pylint: disable=protected-access
            observer._exception_stack_msg = stack_msg  # pylint: disable=protected-access

    @staticmethod
    def _log_unraised_exceptions(observer) -> None:
        """
        Logs the unraised exceptions for the observer.


        :param observer: The observer object (command or event).
        :return: None
        """
        for i, item in enumerate(ConnectionObserver._not_raised_exceptions):
            observer._log(  # pylint: disable=protected-access
                logging.DEBUG,
                f"{i + 1:4d} NOT RAISED: {item!r}",
                levels_to_go_up=2,
            )
            observer._log(logging.DEBUG, observer._exception_stack_msg)  # pylint: disable=protected-access

    def get_long_desc(self) -> str:
        """
        Return a long description of the observer.
        """
        return f"Observer '{self.__class__.__module__}.{self}'"

    def get_short_desc(self) -> str:
        """
        Return a short description of the observer.
        """
        return f"Observer '{self.__class__.__module__}.{self}'"

    def _log(self, lvl: int, msg: str, extra: Optional[dict] = None, levels_to_go_up: int = 1) -> None:
        """
        Log a message with the specified level.

        :param lvl: The log level.
        :param msg: The log message.
        :param extra: Extra parameters to include in the log message. Defaults to None.
        :param levels_to_go_up: The number of levels to go up in the call stack to determine the caller info. Defaults to 1.
        """
        extra_params = {"log_name": self.get_logger_name()}

        if extra:
            extra_params.update(extra)

        # levels_to_go_up=1 : extract caller info to log where _log() has been called from
        log_into_logger(
            self.logger, lvl, msg, extra=extra_params, levels_to_go_up=levels_to_go_up
        )
        log_into_logger(
            self.device_logger,
            lvl,
            msg,
            extra=extra_params,
            levels_to_go_up=levels_to_go_up,
        )

    def is_in_runner(self) -> bool:
        """
        Return True if the observer is currently being executed by a runner.

        :return: True if the observer is currently being executed by a runner, False otherwise.
        """
        return self.runner.is_connection_observer_running(self)
