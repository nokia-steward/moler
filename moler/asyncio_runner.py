# -*- coding: utf-8 -*-
# Copyright (C) 2018-2026 Nokia
"""
Asyncio Runner
"""

__author__ = 'Grzegorz Latuszek, Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com'

# pylint: skip-file

import asyncio
import asyncio.futures
import asyncio.tasks
import atexit
import concurrent.futures
import logging
import threading
import time
import sys
import warnings
import psutil
import functools
import platform

from moler.exceptions import MolerTimeout
from moler.exceptions import MolerException
from moler.exceptions import WrongUsage
from moler.helpers import instance_id
from moler.util.connection_observer import exception_stored_if_not_main_thread
from moler.io.raw import TillDoneThread
from moler.runner import ConnectionObserverRunner
from moler.runner import result_for_runners, time_out_observer, his_remaining_time, await_future_or_eol
from moler.util.loghelper import debug_into_logger


current_process = psutil.Process()
if platform.system() == 'Windows':
    # https://docs.microsoft.com/en-us/cpp/c-runtime-library/reference/setmaxstdio?view=vs-2019
    (max_open_files_limit_soft, max_open_files_limit_hard) = (510, 512)  # TODO: any way on Win?
else:
    # Unix (Linux, Darwin, BSD, ...): read the real RLIMIT_NOFILE via stdlib resource module.
    import resource
    (max_open_files_limit_soft, max_open_files_limit_hard) = resource.getrlimit(resource.RLIMIT_NOFILE)


def system_resources_usage():
    if platform.system() == 'Windows':
        ofiles = current_process.open_files()
        osockets = current_process.connections(kind="all")
        curr_fds_open = len(ofiles) + len(osockets)  # TODO: any better way on Win?
    else:
        curr_fds_open = current_process.num_fds()
    curr_threads_nb = threading.active_count()
    return curr_fds_open, curr_threads_nb


def system_resources_usage_msg(curr_fds_open, curr_threads_nb):
    msg = f"RESOURCES USAGE: {curr_fds_open}/{max_open_files_limit_soft} FDs OPEN, {curr_threads_nb} threads active."
    return msg


def check_system_resources_limit(connection_observer, observer_lock, logger):
    # The number of file descriptors currently opened by this process
    curr_fds_open, curr_threads_nb = system_resources_usage()

    if curr_fds_open > max_open_files_limit_soft - 10:
        err_cause = "Can't run new asyncio loop - ALMOST REACHED MAX OPEN FILES LIMIT"
        msg = f"{err_cause} ({max_open_files_limit_soft}). Now {curr_fds_open} FDs open, {curr_threads_nb} threads active."
        logger.warning(msg)
        limit_exception = MolerException(msg)
        # make future done and observer done-with-exception
        with observer_lock:
            connection_observer.set_exception(limit_exception)
        # We need to return future informing "it's impossible to create new event loop"
        # However, it can't be asyncio.Future() since it requires event loop ;-)
        # We would get something like:
        #
        #    impossible_future = asyncio.Future()
        #  File "/opt/ute/python3/lib/python3.6/asyncio/events.py", line 676, in get_event_loop
        #    return get_event_loop_policy().get_event_loop()
        #  File "/opt/ute/python3/lib/python3.6/asyncio/events.py", line 584, in get_event_loop
        #    % threading.current_thread().name)
        # RuntimeError: There is no current event loop in thread 'Thread-5090'.
        #
        # So, we use concurrent.futures.Future - it has almost same API (duck typing for runner.wait_for() below)
        impossible_future = concurrent.futures.Future()
        impossible_future.set_result(None)
        return impossible_future
    return None


# class LoudEventLoop(asyncio.unix_events.SelectorEventLoop):
class LoudEventLoop(asyncio.SelectorEventLoop):
    def __init__(self, *args):
        super(LoudEventLoop, self).__init__(*args)

    def stop(self):
        logger = logging.getLogger('moler')
        loop_id = instance_id(self)
        msg = f"Called loop.stop() of {loop_id}:{self}"
        debug_into_logger(logger, msg=msg, levels_to_go_up=1)
        debug_into_logger(logger, msg=msg, levels_to_go_up=2)
        debug_into_logger(logger, msg=msg, levels_to_go_up=3)
        super(LoudEventLoop, self).stop()


def thread_secure_get_event_loop(logger_name="moler.runner.asyncio"):
    """
    Need securing since asyncio.get_event_loop() when called from new thread
    may raise sthg like:
    RuntimeError: There is no current event loop in thread 'Thread-3'
    It is so since MainThread has preinstalled loop but other threads must
    setup own loop by themselves.

    :return: loop of current thread + info if it was newly created
    """
    new_loop = False
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError as err:
        if "no current event loop in thread" in str(err):
            loop = asyncio.new_event_loop()
            loop_id = instance_id(loop)
            logger = logging.getLogger(logger_name)
            logger.debug(f"created new event loop {loop_id}:{loop}")
            asyncio.set_event_loop(loop)
            new_loop = True
        else:
            raise

    loop.set_debug(enabled=True)
    return loop, new_loop


def _run_until_complete_cb(fut):
    exc = fut._exception
    if isinstance(exc, BaseException) and not isinstance(exc, Exception):
        # Issue #22429: run_forever() already finished, no need to
        # stop it.
        return
    fut_id = instance_id(fut)
    msg = f"_run_until_complete_cb(fut_id = {fut_id}, {fut})"
    sys.stderr.write(f"{msg}\n")
    logging.getLogger("moler").debug(msg)
    fut._loop.stop()


def feeder_callback(future):
    """Used to recognize asyncio task as AsyncioRunner feeder"""
    pass


def is_feeder(task):
    """We recognize asyncio task to be feeder if it has feeder_callback attached"""
    removed_nb = task.remove_done_callback(feeder_callback)
    return removed_nb > 0


def handle_cancelled_feeder(connection_observer, observer_lock, subscribed_data_receiver, logger, future):
    if future.cancelled() and not connection_observer.done():
        logger.debug(f"cancelled {future}")
        with observer_lock:
            logger.debug(f"cancelling {connection_observer}")
            connection_observer.cancel()
        logger.debug(f"unsubscribing {connection_observer}")
        moler_conn = connection_observer.connection
        moler_conn.unsubscribe(observer=subscribed_data_receiver,
                               connection_closed_handler=connection_observer.connection_closed_handler)


def cancel_remaining_feeders(loop, logger_name="moler.runner.asyncio", in_shutdown=False):
    remaining = [task for task in asyncio.all_tasks(loop) if (not task.done()) and (is_feeder(task))]
    if remaining:
        logger = logging.getLogger(logger_name)
        loop_id = instance_id(loop)
        log_level = logging.WARNING if in_shutdown else logging.DEBUG
        logger.log(level=log_level, msg=f"cancelling all remaining feeders of loop {loop_id}:")
        remaining_tasks = asyncio.gather(*remaining, return_exceptions=True)  # loop is taken from the tasks
        for feeder in remaining:
            logger.log(level=log_level, msg=f"  remaining {instance_id(feeder)}:{feeder}")
        remaining_tasks.cancel()
        if not loop.is_running():
            # Keep the event loop running until it is either destroyed or all tasks have really terminated
            loop.run_until_complete(remaining_tasks)


class AsyncioRunner(ConnectionObserverRunner):
    runner_lock = threading.Lock()
    last_runner_id = 0

    def __init__(self, logger_name='moler.runner.asyncio'):
        """Create instance of AsyncioRunner class"""
        self._in_shutdown = False
        with AsyncioRunner.runner_lock:
            AsyncioRunner.last_runner_id += 1
            self._id = AsyncioRunner.last_runner_id  # instance_id(self)
        self.logger = logging.getLogger(f'{logger_name}.#{self._id}')
        self.logger.debug(f"created {self.__class__.__name__}.#{self._id}")
        logging.getLogger("asyncio").setLevel(logging.DEBUG)
        self._submitted_futures = {}  # id(future): future
        self._started_ev_loops = []
        atexit.register(self.shutdown)

    def shutdown(self):
        self.logger.debug("shutting down")
        self._in_shutdown = True  # will exit from feed()
        # TODO: need wait for all feed() coros before closing owned event loops

        with AsyncioRunner.runner_lock:
            owned_loops_nb = len(self._started_ev_loops)
            if owned_loops_nb:
                sys_resources_usage_msg = system_resources_usage_msg(*system_resources_usage())
                self.logger.debug(f"before closing loops ({owned_loops_nb} owned loops): {sys_resources_usage_msg}")
                for owned_loop in self._started_ev_loops:
                    msg = f"CLOSING EV_LOOP owned by AsyncioRunner {instance_id(owned_loop)}:{owned_loop!r}"
                    sys.stderr.write(f"{msg}\n")
                    self.logger.debug(msg)
                    cancel_remaining_feeders(owned_loop, logger_name=self.logger.name, in_shutdown=True)
                    remaining = [task for task in asyncio.all_tasks(owned_loop) if not task.done()]
                    if remaining:
                        msg = "AsyncioRunner owned loop has still running task"
                        for still_running_task in remaining:
                            msg = f"{msg}: {still_running_task!r}\n"
                            sys.stderr.write(f"{msg}\n")
                            self.logger.debug(msg)
                    owned_loop.close()
                self._started_ev_loops = []
                sys_resources_usage_msg = system_resources_usage_msg(*system_resources_usage())
                self.logger.debug(f"after closing loops: {sys_resources_usage_msg}")

        event_loop, its_new = thread_secure_get_event_loop(logger_name=self.logger.name)
        if not event_loop.is_closed():
            cancel_remaining_feeders(event_loop, logger_name=self.logger.name, in_shutdown=True)
        self._submitted_futures = {}

    def submit(self, connection_observer):
        """
        Submit connection observer to background execution.
        Returns Future that could be used to await for connection_observer done.
        """
        observer_lock = threading.Lock()  # against threads race write-access to observer

        impossible_future = check_system_resources_limit(connection_observer, observer_lock, self.logger)
        if impossible_future:
            return impossible_future

        assert connection_observer.life_status.start_time > 0.0  # connection-observer lifetime should
        # already been started
        observer_timeout = connection_observer.timeout
        remain_time, msg = his_remaining_time("remaining", timeout=observer_timeout,
                                              from_start_time=connection_observer.life_status.start_time)
        self.logger.debug(f"go background: {connection_observer!r} - {msg}")

        # Our submit consists of two steps:
        # 1. _start_feeding() which establishes data path from connection to observer
        # 2. starting "background feed" task handling native future bound to connection_observer
        #                               native future here is asyncio.Task
        #
        # By using the code of _start_feeding() we ensure that after submit() connection data could reach
        # data_received() of observer - as it would be "virtually running in background"
        # Another words, no data will be lost-for-observer between runner.submit() and runner.feed() really running
        #
        # We do not await here (before returning from submit()) for "background feed" to be really started.
        # Not waiting for "background feed" to be running is in line with generic scheme of any async-code: methods
        # should be as quick as possible.
        #
        # However, lifetime of connection_observer starts in connection_observer.start().
        # It gains it's own timer so that timeout is calculated from that connection_observer.life_status.start_time
        # That lifetime may start even before this submit() if observer is command and we have commands queue.
        #
        # As a corner case runner.wait_for() may timeout before feeding coroutine has started.
        #
        # duration of submit() is measured as around 0.0007sec (depends on machine).
        event_loop, its_new = thread_secure_get_event_loop(logger_name=self.logger.name)
        if its_new:
            with AsyncioRunner.runner_lock:
                self._started_ev_loops.append(event_loop)
        subscribed_data_receiver = self._start_feeding(connection_observer, observer_lock)
        self.logger.debug(f"scheduling feed({connection_observer})")
        connection_observer_future = asyncio.ensure_future(self.feed(connection_observer,
                                                                     subscribed_data_receiver,
                                                                     observer_lock),
                                                           loop=event_loop)
        self.logger.debug(f"runner submit() returning - future: {instance_id(connection_observer_future)}:{connection_observer_future}")
        if connection_observer_future.done():
            # most probably we have some exception during ensure_future(); it should be stored inside future
            try:
                too_early_result = connection_observer_future.result()
                err_msg = f"PROBLEM: future returned {too_early_result} already in runner.submit()"
                self.logger.warning(f"go background: {connection_observer} - {err_msg}")
            except Exception as err:
                err_msg = f"PROBLEM: future raised {err!r} during runner.submit()"
                self.logger.warning(f"go background: {connection_observer} - {err_msg}")
                self.logger.exception(err_msg)
                raise

        self._submitted_futures[id(connection_observer_future)] = connection_observer_future
        # need injecting new attribute inside asyncio.Future object
        # to allow passing lock to wait_for()
        connection_observer_future.observer_lock = observer_lock
        connection_observer_future.add_done_callback(feeder_callback)
        connection_observer_future.add_done_callback(functools.partial(handle_cancelled_feeder,
                                                                       connection_observer,
                                                                       observer_lock,
                                                                       subscribed_data_receiver,
                                                                       self.logger))
        return connection_observer_future

    def wait_for(self, connection_observer, connection_observer_future, timeout=None):
        """
        Await for connection_observer running in background or timeout.

        :param connection_observer: The one we are awaiting for.
        :param connection_observer_future: Future of connection-observer returned from submit().
        :param timeout: Max time (in float seconds) to await before give up. If None then taken from connection_observer
        :return:
        """
        if connection_observer.done():
            # 1. done() might mean "timed out" before future created (future is None)
            #    Observer lifetime started with its timeout clock so, it might timeout even before
            #    future created by runner.submit() - may happen for nonempty commands queue
            # 2. done() might mean "timed out" before future start
            #    Observer lifetime started with its timeout clock so, it might timeout even before
            #    connection_observer_future started - since future's coro might not get control yet
            # 3. done() might mean "timed out" before wait_for()
            #    wait_for() might be called so late after submit() that observer already "timed out"
            # 4. done() might mean have result or got exception
            #    wait_for() might be called so late after submit() that observer already got result/exception
            #
            # In all above cases we want to stop future if it is still running
            self.logger.debug(f"go foreground: {connection_observer} is already done")
            self._cancel_submitted_future(connection_observer, connection_observer_future)
            return None

        max_timeout = timeout
        observer_timeout = connection_observer.timeout
        # we count timeout from now if timeout is given; else we use .life_status.start_time and .timeout of observer
        start_time = time.monotonic() if max_timeout else connection_observer.life_status.start_time
        await_timeout = max_timeout if max_timeout else observer_timeout
        if max_timeout:
            remain_time, msg = his_remaining_time("await max.", timeout=max_timeout, from_start_time=start_time)
        else:
            remain_time, msg = his_remaining_time("remaining", timeout=observer_timeout, from_start_time=start_time)

        self.logger.debug(f"go foreground: {connection_observer} - {msg}")
        event_loop, its_new = thread_secure_get_event_loop()
        assert not its_new  # should not happen since submit() is called first

        with exception_stored_if_not_main_thread(connection_observer, logger=self.logger):
            try:
                # we might be already called from within running event loop
                # or we are just in synchronous code
                if event_loop.is_running():
                    # wait_for() should not be called from 'async def'
                    self._raise_wrong_usage_of_wait_for(connection_observer)

                if connection_observer_future is None:
                    end_of_life, remain_time = await_future_or_eol(connection_observer, remain_time, start_time, await_timeout, self.logger)
                    if end_of_life:
                        return None
                    if remain_time <= 0.0:
                        raise asyncio.futures.TimeoutError()
                    connection_observer_future = connection_observer._future
                    assert connection_observer_future is not None

                self._run_via_asyncio(event_loop, connection_observer_future, max_timeout, remain_time)

            except asyncio.futures.CancelledError:
                self.logger.debug(f"canceled {connection_observer}")
                connection_observer.cancel()
            except asyncio.futures.TimeoutError:
                self._wait_for_time_out(connection_observer, connection_observer_future,
                                        timeout=await_timeout)
            finally:
                self._cancel_submitted_future(connection_observer, connection_observer_future)
        return None

    def _cancel_submitted_future(self, connection_observer, connection_observer_future):
        future = connection_observer_future or connection_observer._future
        if future:
            if not future.done():
                future.cancel()
            if id(future) in self._submitted_futures:
                del self._submitted_futures[id(future)]

    def _wait_for_time_out(self, connection_observer, connection_observer_future, timeout):
        passed = time.monotonic() - connection_observer.life_status.start_time
        future = connection_observer_future or connection_observer._future
        if future:
            with future.observer_lock:
                time_out_observer(connection_observer=connection_observer,
                                  timeout=timeout, passed_time=passed,
                                  runner_logger=self.logger, kind="await_done")
        else:
            # sorry, we don't have lock yet (it is created by runner.submit()
            time_out_observer(connection_observer=connection_observer,
                              timeout=timeout, passed_time=passed,
                              runner_logger=self.logger, kind="await_done")

    @staticmethod
    def _run_via_asyncio(event_loop, connection_observer_future, max_timeout, remain_time):
        try:
            if max_timeout:
                timeout_limited_future = asyncio.wait_for(connection_observer_future, timeout=remain_time)

                fut_id = instance_id(connection_observer_future)
                msg = f"__run_via_asyncio with timeout: (fut_id = {fut_id}, {connection_observer_future})"
                sys.stderr.write(f"{msg}\n")
                logging.getLogger("moler").debug(msg)
                fut_id = instance_id(timeout_limited_future)
                msg = f"__run_via_asyncio with timeout: (tmout_fut_id = {fut_id}, {timeout_limited_future})"
                sys.stderr.write(f"{msg}\n")
                logging.getLogger("moler").debug(msg)

                AsyncioRunner._run_until_complete(event_loop, timeout_limited_future)

            else:
                fut_id = instance_id(connection_observer_future)
                msg = f"__run_via_asyncio no timeout: (fut_id = {fut_id}, {connection_observer_future})"
                sys.stderr.write(f"{msg}\n")
                logging.getLogger("moler").debug(msg)
                AsyncioRunner._run_until_complete(event_loop, connection_observer_future)  # timeout is handled by feed()

        except BaseException as exc:
            fut = connection_observer_future
            fut_id = instance_id(connection_observer_future)
            err_msg = f"_run_until_complete(max_tm={max_timeout}, remain={remain_time}): raised {exc!r}\n\tfut: {fut_id}:{fut!r}"
            sys.stderr.write(f"{err_msg}\n")
            logging.getLogger("moler").debug(err_msg)
            raise

    @staticmethod
    def _run_until_complete(event_loop, future):
        """Run until the Future is done.

        If the argument is a coroutine, it is wrapped in a Task.

        WARNING: It would be disastrous to call run_until_complete()
        with the same coroutine twice -- it would wrap it in two
        different Tasks and that can't be good.

        Return the Future's result, or raise its exception.
        """
        event_loop._check_closed()

        new_task = not asyncio.futures.isfuture(future)
        fut_id = instance_id(future)
        future = asyncio.tasks.ensure_future(future, loop=event_loop)
        task_id = instance_id(future)
        msg = f"task for future id ({fut_id}) future = asyncio.tasks.ensure_future: (task_id = {task_id}, {future})"
        sys.stderr.write(f"{msg}\n")
        logging.getLogger("moler").debug(msg)

        if new_task:
            # An exception is raised if the future didn't complete, so there
            # is no need to log the "destroy pending task" message
            future._log_destroy_pending = False

        future.add_done_callback(_run_until_complete_cb)
        try:
            event_loop.run_forever()
        except BaseException:
            if new_task and future.done() and not future.cancelled():
                # The coroutine raised a BaseException. Consume the exception
                # to not log a warning, the caller doesn't have access to the
                # local task.
                future.exception()
            raise
        finally:
            future.remove_done_callback(_run_until_complete_cb)
        if not future.done():
            fut_id = instance_id(future)
            msg = f"not done future in _run_until_complete(fut_id = {fut_id}, {future})"
            sys.stderr.write(f"{msg}\n")
            logging.getLogger("moler").debug(msg)
            raise RuntimeError(f'Event loop stopped before Future completed. (fut_id = {fut_id}, {future})')

        return future.result()

    def _raise_wrong_usage_of_wait_for(self, connection_observer):
        import inspect  # don't import if never raising this exception
        (_, _, _, caller_name, _, _) = inspect.stack()[1]
        (_, _, _, caller_caller_name, _, _) = inspect.stack()[2]
        # Prefer to speak in observer API not runner API since user uses observers-API (runner is hidden)
        user_call_name = caller_caller_name if caller_caller_name == 'await_done' else caller_name
        err_msg = f"Can't call {user_call_name}() from 'async def' - it is blocking call"
        err_msg += f"\n    observer = {connection_observer.__class__.__name__}()"
        err_msg += "\n    observer.start()"
        err_msg += "\nconsider using:"
        err_msg += "\n    await observer"
        err_msg += "\ninstead of:"
        err_msg += "\n    observer.await_done()"
        self.logger.error(msg=err_msg)
        raise WrongUsage(err_msg)

    # https://stackoverflow.com/questions/51029111/python-how-to-implement-a-c-function-as-awaitable-coroutine
    def wait_for_iterator(self, connection_observer, connection_observer_future):
        """
        Version of wait_for() intended to be used by Python3 to implement awaitable object.

        Note: we don't have timeout parameter here. If you want to await with timeout please do use asyncio machinery.
        For ex.:  await asyncio.wait_for(connection_observer, timeout=10)

        :param connection_observer: The one we are awaiting for.
        :param connection_observer_future: Future of connection-observer returned from submit().
        :return: iterator
        """
        self.logger.debug(f"go foreground: {connection_observer!r}")

        # assuming that connection_observer.start() / runner.submit(connection_observer)
        # has already scheduled future via asyncio.ensure_future
        assert asyncio.futures.isfuture(connection_observer_future)

        return connection_observer_future.__iter__()
        # Note: even if code is so simple we can't move it inside ConnectionObserver.__await__() since different runners
        # may provide different iterator implementing awaitable
        # Here we know, connection_observer_future is asyncio.Future (precisely asyncio.tasks.Task)
        # and we know it has __await__() method.

    def _start_feeding(self, connection_observer, observer_lock):
        """
        Start feeding connection_observer by establishing data-channel from connection to observer.
        """
        # we have following ending conditions:
        # 1) connection observer consuming data sets result      -> .done() == True
        # 2) connection observer consuming data sets exception   -> .done() == True
        # 3) connection observer is cancelled                    -> .done() == True
        # 4) connection observer times out                  ------> NOT HANDLED HERE (yet?)
        # 5) connection observer consuming data raises exception -> secured to .set_exception() here
        # 6) runner is in shutdown state
        #
        # main purpose of secure_data_received() is to progress observer-life by data
        #
        def secure_data_received(data, recv_time):
            try:
                if connection_observer.done() or self._in_shutdown:
                    return  # even not unsubscribed secure_data_received() won't pass data to done observer
                with observer_lock:
                    connection_observer.data_received(data, recv_time)

            except Exception as exc:  # TODO: handling stacktrace
                # observers should not raise exceptions during data parsing
                # but if they do so - we fix it
                with observer_lock:
                    connection_observer.set_exception(exc)
            finally:
                if connection_observer.done() and not connection_observer.cancelled():
                    if connection_observer._exception:
                        self.logger.debug(f"{connection_observer} raised: {connection_observer._exception!r}")
                    else:
                        self.logger.debug(f"{connection_observer} returned: {connection_observer._result}")

        moler_conn = connection_observer.connection
        self.logger.debug(f"subscribing for data {connection_observer}")
        moler_conn.subscribe(observer=secure_data_received,
                             connection_closed_handler=connection_observer.connection_closed_handler)
        if connection_observer.is_command():
            connection_observer.send_command()
        return secure_data_received  # to know what to unsubscribe

    async def feed(self, connection_observer, subscribed_data_receiver, observer_lock):
        """
        Feeds connection_observer by transferring data from connection and passing it to connection_observer.
        Should be called from background-processing of connection observer.
        """
        remain_time, msg = his_remaining_time("remaining", timeout=connection_observer.timeout,
                                              from_start_time=connection_observer.life_status.start_time)
        self.logger.debug(f"{connection_observer} started, {msg}")
        connection_observer._log(logging.INFO, f"{connection_observer.get_long_desc()} started, {msg}")

        if not subscribed_data_receiver:
            subscribed_data_receiver = self._start_feeding(connection_observer, observer_lock)

        await asyncio.sleep(0.005)  # give control back before we start processing
        start_time = connection_observer.life_status.start_time

        moler_conn = connection_observer.connection
        try:
            while True:
                if connection_observer.done():
                    self.logger.debug(f"done {connection_observer}")
                    break
                run_duration = time.monotonic() - start_time
                # we need to check connection_observer.timeout at each round since timeout may change
                # during lifetime of connection_observer
                if (connection_observer.timeout is not None) and (run_duration >= connection_observer.timeout):
                    with observer_lock:
                        time_out_observer(connection_observer,
                                          timeout=connection_observer.timeout,
                                          passed_time=run_duration,
                                          runner_logger=self.logger)
                    break
                if self._in_shutdown:
                    self.logger.debug(f"shutdown so cancelling {connection_observer}")
                    connection_observer.cancel()
                await asyncio.sleep(0.005)  # give moler_conn a chance to feed observer
            #
            # main purpose of feed() is to progress observer-life by time
            #             firing timeout should do: observer.set_exception(Timeout)
            #
            # second responsibility: subscribe, unsubscribe observer from connection (build/break data path)
            # third responsibility: react on external stop request via observer.cancel() or runner.shutdown()

            # There is no need to put observer's result/exception into future:
            # Future's goal is to feed observer (by data or time) - exiting future here means observer is already fed.
            #
            # Moreover, putting observer's exception here, in future, causes problem at asyncio shutdown:
            # we get logs like: "Task exception was never retrieved" with bunch of stacktraces.
            # That is correct behaviour of asyncio to not exit silently when future/task has gone wrong.
            # However, feed() task worked fine since it correctly handled observer's exception.
            # Another words - it is not feed's exception but observer's exception so, it should not be raised here.
            #
        except asyncio.CancelledError:
            self.logger.debug(f"cancelling {self}.feed")
            # cancelling connection_observer is done inside handle_cancelled_feeder()
            raise  # need to reraise to inform "I agree for cancellation"

        finally:
            self.logger.debug(f"unsubscribing {connection_observer}")
            moler_conn.unsubscribe(observer=subscribed_data_receiver,
                                   connection_closed_handler=connection_observer.connection_closed_handler)
            # feed_done.set()

            remain_time, msg = his_remaining_time("remaining", timeout=connection_observer.timeout,
                                                  from_start_time=connection_observer.life_status.start_time)
            connection_observer._log(logging.INFO, f"{connection_observer.get_short_desc()} finished, {msg}")
            self.logger.debug(f"{connection_observer} finished, {msg}")
        return None

    def timeout_change(self, timedelta):
        pass


class AsyncioEventThreadsafe(asyncio.Event):
    def __init__(self, loop):
        # asyncio.Event(loop=...) was removed in Python 3.10 - Event binds to running loop on first use,
        # so we need to remember loop owning this event to allow set()/clear() from other threads.
        super().__init__()
        self._owner_loop = loop

    def set(self):
        self._owner_loop.call_soon_threadsafe(super().set)

    def clear(self):
        self._owner_loop.call_soon_threadsafe(super().clear)


class AsyncioInThreadRunner(AsyncioRunner):
    def __init__(self):
        """Create instance of AsyncioInThreadRunner class"""
        super(AsyncioInThreadRunner, self).__init__(logger_name='moler.runner.asyncio-in-thrd')
        # AsyncioLoopThread must be created from MainThread since it adds signal handlers
        # (AsyncioLoopThread needs unix watchers embeding signal handles used to stop subprocesses)
        get_asyncio_loop_thread()

    def shutdown(self):
        self.logger.debug("shutting down")
        self._in_shutdown = True  # will exit from feed()
        # event_loop, its_new = thread_secure_get_event_loop()
        # if not event_loop.is_closed():
        #     remaining_tasks = asyncio.gather(*self._submitted_futures, return_exceptions=True)
        #     remaining_tasks.cancel()
        #     # cleanup_selected_tasks(tasks2cancel=self._submitted_futures, loop=event_loop, logger=self.logger)
        #     self._submitted_futures = []

    def submit(self, connection_observer):
        """
        Submit connection observer to background execution.
        Returns Future that could be used to await for connection_observer done.
        """
        self.logger.debug(f"go background: {connection_observer!r}")

        # TODO: check dependency - connection_observer.connection

        # Our submit consists of two steps:
        # 1. scheduling start_feeder() in asyncio dedicated thread via run_async_coroutine()
        # 2. scheduling "background feed" via asyncio.ensure_future()
        #    - internally it calls _start_feeding() which sets feed_started event
        #
        # Moreover, we await here (before returning from submit()) for "background feed" to be really started.
        # That is realized by 0.5sec timeout and awaiting for feed_started asyncio.Event.
        # It ensures that feed() coroutine is already running inside asyncio loop.
        # Such functionality is possible thanks to using thread.
        #
        # By using the code of _start_feeding() we ensure that after submit() connection data could reach
        # data_received() of observer. Another words, no data will be lost-for-observer after runner.submit().
        #
        # Consequence of waiting for "background feed" to be running is that submit is blocking call till feed() start.
        # Generic scheme of any async-code is: methods should be as quick as possible. Because async frameworks
        # operate inside single thread blocking call means "nothing else could happen". Nothing here may
        # mean for example "handling data of other connections", "handling other observers".
        # So, if we put observer with AsyncioInThreadRunner inside some event loop then that loop will block
        # for duration of submit() which is measured as around 0.01sec (depends on machine).
        #
        # That 0.01sec price we want to pay since we gain another benefit for that price.
        # If anything goes wrong and start_feeder() can't be completed in 0.5sec we will be at least notified
        # by MolerException.

        async def start_feeder():
            feed_started = asyncio.Event()
            self.logger.debug(f"scheduling feed({connection_observer})")
            # noinspection PyArgumentList
            conn_observer_future = asyncio.ensure_future(self.feed(connection_observer,
                                                                   feed_started,
                                                                   subscribed_data_receiver=None))
            self.logger.debug(f"scheduled feed() - future: {conn_observer_future}")
            await feed_started.wait()
            self.logger.debug(f"feed() started - future: {instance_id(conn_observer_future)}:{conn_observer_future}")
            return conn_observer_future

        thread4async = get_asyncio_loop_thread()
        start_timeout = 0.5
        try:
            connection_observer_future = thread4async.run_async_coroutine(start_feeder(), timeout=start_timeout)
        except MolerTimeout:
            err_msg = f"Failed to start observer feeder within {start_timeout} sec"
            self.logger.error(err_msg)
            exc = MolerException(err_msg)
            connection_observer.set_exception(exception=exc)
            return None
        self.logger.debug(f"runner submit() returning - future: {instance_id(connection_observer_future)}:{connection_observer_future}")
        return connection_observer_future

    def wait_for(self, connection_observer, connection_observer_future, timeout=None):
        """
        Await for connection_observer running in background or timeout.

        :param connection_observer: The one we are awaiting for.
        :param connection_observer_future: Future of connection-observer returned from submit().
        :param timeout: Max time (in float seconds) to await before give up. None - use connection_observer.timeout
        :return:
        """
        self.logger.debug(f"go foreground: {connection_observer!r} - await max. {timeout} [sec]")
        if connection_observer.done():  # may happen when failed to start observer feeder
            return None
        start_time = time.monotonic()

        async def wait_for_connection_observer_done():
            result_of_future = await connection_observer_future  # feed() always returns None
            return result_of_future

        thread4async = get_asyncio_loop_thread()
        try:
            event_loop, its_new = thread_secure_get_event_loop()
            if event_loop.is_running():
                # wait_for() should not be called from 'async def'
                self._raise_wrong_usage_of_wait_for(connection_observer)

            # If we have have timeout=None then concurrent.futures will wait infinitely
            # and feed() inside asyncio-loop will work on connection_observer.timeout
            #
            # If timeout is given then it defines max timeout (from "now") that concurrent.futures
            # may use to shorten lifetime of feed().
            # In such case we have concurrent.futures and asyncio race here - race about timeouts.
            thread4async.run_async_coroutine(wait_for_connection_observer_done(), timeout=timeout)
            # If feed() inside asyncio-loop handles timeout as first - we exit here.
            return None
        except MolerTimeout:
            # If run_async_coroutine() times out - we follow from here.
            pass
        except concurrent.futures.CancelledError:
            connection_observer.cancel()
            return None
        except Exception as err:
            err_msg = f"{connection_observer} raised {err!r}"
            self.logger.debug(err_msg)
            if connection_observer._exception != err:
                connection_observer.set_exception(err)
            return None  # will be reraised during call to connection_observer.result()
        finally:
            # protect against leaking coroutines
            if not connection_observer_future.done():
                async def conn_observer_fut_cancel():
                    connection_observer_future.cancel()
                thread4async.start_async_coroutine(conn_observer_fut_cancel())

        # handle timeout
        passed = time.monotonic() - start_time
        fired_timeout = timeout if timeout else connection_observer.timeout
        time_out_observer(connection_observer=connection_observer,
                          timeout=fired_timeout, passed_time=passed,
                          runner_logger=self.logger, kind="await_done")
        return None

    def wait_for_iterator(self, connection_observer, connection_observer_future):
        """
        Version of wait_for() intended to be used by Python3 to implement iterable/awaitable object.

        Note: we don't have timeout parameter here. If you want to await with timeout please do use timeout machinery
        of selected parallelism.

        :param connection_observer: The one we are awaiting for.
        :param connection_observer_future: Future of connection-observer returned from submit().
        :return: iterator
        """
        self.logger.debug(f"returning iterator for {connection_observer}")
        while not connection_observer_future.done():
            yield None
        return result_for_runners(connection_observer)  # May raise too.


def cleanup_remaining_tasks(loop, logger):
    # https://stackoverflow.com/questions/30765606/whats-the-correct-way-to-clean-up-after-an-interrupted-event-loop
    # https://medium.com/python-pandemonium/asyncio-coroutine-patterns-beyond-await-a6121486656f
    # Handle shutdown gracefully by waiting for all tasks to be cancelled

    not_done_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
    if not_done_tasks:
        logger.info("cancelling all remaining tasks")
        # NOTE: following code cancels all tasks - possibly not ours as well

        cleanup_selected_tasks(tasks2cancel=not_done_tasks, loop=loop, logger=logger)


def cleanup_selected_tasks(tasks2cancel, loop, logger):
    logger.debug(f"tasks to cancel: {tasks2cancel}")
    remaining_tasks = asyncio.gather(*tasks2cancel, return_exceptions=True)  # loop is taken from the tasks
    remaining_tasks.add_done_callback(lambda t: loop.stop())
    remaining_tasks.cancel()

    # Keep the event loop running until it is either destroyed or all
    # tasks have really terminated
    loop.run_until_complete(remaining_tasks)


class AsyncioLoopThread(TillDoneThread):
    def __init__(self, name="Asyncio"):
        self.logger = logging.getLogger('moler.asyncio-loop-thrd')
        self.ev_loop = asyncio.new_event_loop()

        # to allow subprocesses running in "subthread"
        # otherwise we get error:
        # RuntimeError: Cannot add child handler, the child watcher does not have a loop attached
        # This is because unix watchers embed signal handles used to stop subprocesses
        #
        # https://stackoverflow.com/questions/28915607/does-asyncio-support-running-a-subprocess-from-a-non-main-thread/28917653#28917653
        #   When asyncio starts subprocess it need to be notified by subproc finish event.
        #   Unfortunately in Unix systems the generic way to do it is catching SIG_CHLD signal.
        #   Python interpreter can process signals only in main thread.
        # answer by: https://stackoverflow.com/users/3454879/andrew-svetlov
        #
        # asyncio.get_child_watcher() is deprecated since Python 3.12 and removed in 3.14.
        # Since 3.8 default watcher (ThreadedChildWatcher/PidfdChildWatcher) doesn't need attached loop.
        if hasattr(asyncio, "get_child_watcher"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                asyncio.get_child_watcher().attach_loop(self.ev_loop)

        self.ev_loop.set_debug(enabled=True)

        self.logger.debug(f"created asyncio loop: {id(self.ev_loop)}:{self.ev_loop}")
        self.ev_loop_done = AsyncioEventThreadsafe(loop=self.ev_loop)
        self.ev_loop_done.clear()
        self.ev_loop_started = threading.Event()

        super(AsyncioLoopThread, self).__init__(target=self._start_loop,
                                                done_event=self.ev_loop_done,
                                                kwargs={'loop': self.ev_loop,
                                                        'loop_started': self.ev_loop_started,
                                                        'loop_done': self.ev_loop_done})
        # Thread-3  -->  [Thread, 3]
        name_parts = self.name.split('-')
        self.name = f"{name}-{name_parts[-1]}"
        self.logger.debug(f"created thread {self} for asyncio loop")

    def start(self):
        """
        We wan't this method to not return before it ensures
        that thread and it's enclosed loop are really running.
        """
        super(AsyncioLoopThread, self).start()
        # await loop thread to be really started
        start_timeout = 0.5
        if not self.ev_loop_started.wait(timeout=start_timeout):
            err_msg = f"Failed to start asyncio loop thread within {start_timeout} sec"
            self.ev_loop_done.set()
            raise MolerException(err_msg)
        self.logger.info("started new asyncio-loop-thrd ...")

    def join(self, timeout=None):
        """
        Closing asyncio loop must be done from MainThread
        to allow for removing signal handlers
        """
        super(AsyncioLoopThread, self).join(timeout=timeout)
        self.logger.info("finished asyncio-loop-thrd ...")
        self.logger.info("closing events loop ...")
        sys.stderr.write(f"CLOSING EV_LOOP of AsyncioLoopThread {self.ev_loop!r}\n")
        for still_running_tasks in asyncio.all_tasks(self.ev_loop):
            sys.stderr.write(f"AsyncioLoopThread has still running task: {still_running_tasks!r}\n")
        self.ev_loop.close()
        self.logger.info("... asyncio loop closed")

    def _start_loop(self, loop, loop_started, loop_done):
        asyncio.set_event_loop(loop)
        try:
            self.logger.info("starting new asyncio loop ...")
            loop.run_until_complete(self._await_stop_loop(loop_started=loop_started, stop_event=loop_done))
            # cleanup_remaining_tasks(loop=loop, logger=self.logger)
        finally:
            self.logger.info("asyncio loop is done ...")

    async def _await_stop_loop(self, loop_started, stop_event):
        # stop_event may be set directly via self._loop_done.set()
        # or indirectly by TillDoneThread when python calls join on all active threads during python shutdown
        self.logger.info("will await loop stop_event ...")
        loop_started.set()
        await stop_event.wait()
        self.logger.info("... await loop stop_event done")

    def run_async_coroutine(self, coroutine_to_run, timeout):
        """Start coroutine in dedicated thread and await its result with timeout"""
        start_time = time.monotonic()
        coro_future = self.start_async_coroutine(coroutine_to_run)
        # run_coroutine_threadsafe returns future as concurrent.futures.Future() and not asyncio.Future
        # so, we can await it with timeout inside current thread
        try:
            coro_result = coro_future.result(timeout=timeout)
            self.logger.debug(f"scheduled {coroutine_to_run} returned {coro_result}")
            return coro_result
        except concurrent.futures.TimeoutError:
            passed = time.monotonic() - start_time
            raise MolerTimeout(timeout=timeout,
                               kind=f"run_async_coroutine({coroutine_to_run})",
                               passed_time=passed)
        except concurrent.futures.CancelledError:
            raise

    def start_async_coroutine(self, coroutine_to_run):
        """Start coroutine in dedicated thread, don't await its result"""
        # we are scheduling to other thread (so, can't use asyncio.ensure_future() )
        self.logger.debug(f"scheduling {coroutine_to_run} into {self.ev_loop}")
        coro_future = asyncio.run_coroutine_threadsafe(coroutine_to_run, loop=self.ev_loop)
        return coro_future


_asyncio_loop_thread = None
_asyncio_loop_thread_lock = threading.Lock()


def get_asyncio_loop_thread():
    logger = logging.getLogger('moler.asyncio-loop-thrd')
    with _asyncio_loop_thread_lock:
        global _asyncio_loop_thread  # pylint: disable=global-statement
        if _asyncio_loop_thread is None:
            logger.debug(f">>> >>> found _asyncio_loop_thread as {_asyncio_loop_thread}")

            logger.debug(f">>> >>> will create thread {_asyncio_loop_thread}")
            new_loop_thread = AsyncioLoopThread()
            logger.debug(f">>> >>> AsyncioLoopThread() --> {new_loop_thread}")
            new_loop_thread.start()
            logger.debug(f">>> >>> started {new_loop_thread}")
            _asyncio_loop_thread = new_loop_thread
    logger.debug(f">>> >>> returning {_asyncio_loop_thread}")
    return _asyncio_loop_thread
