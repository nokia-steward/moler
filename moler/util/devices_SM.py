# -*- coding: utf-8 -*-
"""
Perform devices SM autotest.
"""

__author__ = "Michal Ernst, Marcin Usielski"
__copyright__ = "Copyright (C) 2019-2026, Nokia"
__email__ = "michal.ernst@nokia.com, marcin.usielski@nokia.com"

import math
import os
import queue
import random
import threading
import time
import traceback

from moler.config import load_config
from moler.device import DeviceFactory
from moler.device.textualdevice import TextualDevice
from moler.exceptions import MolerException
from moler.helpers import copy_list
from moler.io.raw.memory import ThreadedFifoBuffer
from moler.util.moler_test import MolerTest


def iterate_over_device_states(
    device,
    max_time=None,
    tests_per_device=300,
    max_no_of_threads=11,
    rerun=0,
    timeout_multiply=3.0,
    sleep_after_changed_state=0.0,
    states_to_skip=None,
):
    """
    Check all states in device under test.

    :param device: device
    :param max_time: maximum time of check. None for infinity. If execution time is greater then max_time then test is
     interrupted.
    :param tests_per_device: how many tests should be performed in one thread.
    :param max_no_of_threads: maximum number of threads that can be started.
    :param rerun: rerun for goto_state
    :param timeout_multiply: timeout_multiply for goto_state
    :param sleep_after_changed_state: sleep after state change
    :param states_to_skip: list of states to skip and not test. If None then all states are tested.
    :return: None
    """
    source_states = _get_all_states_from_device(device=device)
    if states_to_skip is not None:
        source_states = [state for state in source_states if state not in states_to_skip]
    target_states = copy_list(source_states)
    nr_of_tests = len(source_states) * len(target_states)

    device.last_wrong_wait4_occurrence = None
    device.set_all_prompts_on_line(True)

    device._goto_state_in_production_mode = False  # pylint: disable=protected-access
    device.goto_state(state=source_states[0], rerun=rerun, sleep_after_changed_state=sleep_after_changed_state)

    random.shuffle(source_states)
    random.shuffle(target_states)
    tested = set()

    states_to_test = queue.Queue(maxsize=nr_of_tests)
    for source in source_states:
        for target in target_states:
            states_to_test.put([source, target])
    assert states_to_test.qsize() == nr_of_tests

    nr_of_threads = math.ceil(nr_of_tests / float(tests_per_device))
    if nr_of_threads > max_no_of_threads:
        nr_of_threads = max_no_of_threads
    thread_nr = 1
    test_threads = []
    exceptions = []
    while thread_nr < nr_of_threads:
        new_connection = get_memory_device_connection()
        new_connection.open()
        new_device_name = f"{device.name}_C{thread_nr}"
        th = _perform_device_tests_start_thread(
            source_device=device,
            tested=tested,
            states_to_test=states_to_test,
            max_time=max_time,
            new_device_name=new_device_name,
            connection=new_connection,
            exceptions=exceptions,
            rerun=rerun,
            timeout_multiply=timeout_multiply,
            sleep_after_changed_state=sleep_after_changed_state
        )
        test_threads.append((th, new_connection))
        thread_nr += 1
    _perform_device_tests(
        device=device,
        tested=tested,
        states_to_test=states_to_test,
        max_time=max_time,
        rerun=rerun,
        timeout_multiply=timeout_multiply,
        sleep_after_changed_state=sleep_after_changed_state
    )
    for th, dev_connection in test_threads:
        th.join()
        dev_connection.close()
    if max_time is None:
        assert 0 == states_to_test.qsize()
    for ex in exceptions:
        print(f"ex: '{ex}' -> '{repr(ex)}': {traceback.format_tb(ex.__traceback__)}")
    assert 0 == len(exceptions)


def _perform_device_tests_start_thread(
    source_device,
    tested,
    states_to_test,
    max_time,
    new_device_name,
    connection,
    exceptions,
    rerun,
    timeout_multiply,
    sleep_after_changed_state,
):
    try:
        th = threading.Thread(
            target=_start_device_tests,
            args=(
                source_device,
                tested,
                states_to_test,
                max_time,
                new_device_name,
                connection,
                exceptions,
                rerun,
                timeout_multiply,
                sleep_after_changed_state,
            ),
        )
        th.daemon = True
        th.start()
        return th
    except Exception as ex:
        exceptions.append(ex)
        MolerTest.info(f"exception: '{ex}' -> '{repr(ex)}'")


def _start_device_tests(
    source_device,
    tested,
    states_to_test,
    max_time,
    new_device_name,
    connection,
    exceptions,
    rerun,
    timeout_multiply,
    sleep_after_changed_state
):
    try:
        device = get_cloned_device(
            src_device=source_device,
            new_name=new_device_name,
            new_connection=connection,
        )
        device.goto_state(state=states_to_test.queue[0][0], rerun=rerun, sleep_after_changed_state=sleep_after_changed_state)
        _perform_device_tests(
            device=device,
            tested=tested,
            states_to_test=states_to_test,
            max_time=max_time,
            rerun=rerun,
            timeout_multiply=timeout_multiply,
            sleep_after_changed_state=sleep_after_changed_state
        )
        device.remove()
    except Exception as ex:
        exceptions.append(ex)
        MolerTest.info(f"exception: '{ex}' -> '{repr(ex)}'")


def _perform_device_tests(
    device, tested, states_to_test, max_time, rerun, timeout_multiply, sleep_after_changed_state
):
    device.set_all_prompts_on_line(True)
    start_time = time.monotonic()
    test_nr = 0
    while 0 < states_to_test.qsize():
        source_state, target_state = states_to_test.get(0)
        if (source_state, target_state) in tested:
            continue
        try:
            state_before_test = device.current_state
            device.goto_state(
                source_state,
                keep_state=False,
                rerun=rerun,
                timeout_multiply=timeout_multiply,
                sleep_after_changed_state=sleep_after_changed_state,
            )
            tested.add((state_before_test, source_state))
            device.goto_state(
                target_state,
                keep_state=False,
                rerun=rerun,
                timeout_multiply=timeout_multiply,
                sleep_after_changed_state=sleep_after_changed_state,
            )
            tested.add((source_state, target_state))

            _raise_if_wrong_wait4_occurrence(device, state_before_test, source_state, target_state)
        except Exception as exc:
            if device.last_wrong_wait4_occurrence is not None and not _is_wrong_wait4_exception(exc):
                try:
                    _raise_if_wrong_wait4_occurrence(device, state_before_test, source_state, target_state)
                except MolerException as wrong_wait4_exc:
                    raise MolerException(
                        f"Cannot trigger change state: '{source_state}' -> '{target_state}'. Successful tests: {test_nr}\n{wrong_wait4_exc}\nOriginal exception: {exc}\nAlready tested '{tested}'."
                    ) from exc
            raise MolerException(
                f"Cannot trigger change state: '{source_state}' -> '{target_state}'. Successful tests: {test_nr}\n{exc}\nAlready tested '{tested}'."
            ) from exc
        test_nr += 1
        if max_time is not None and time.monotonic() - start_time > max_time:
            return


_WRONG_WAIT4_MSG = "More than 1 prompt match the same line!"


def _is_wrong_wait4_exception(exc):
    return _WRONG_WAIT4_MSG in str(exc)


def _raise_if_wrong_wait4_occurrence(device, state_before_test, source_state, target_state):
    occurrence = device.last_wrong_wait4_occurrence
    if occurrence is None:
        return
    prompts = [{item["state"]: item["prompt_regex"]} for item in occurrence["list_matched"]]
    raise MolerException(
        f"{_WRONG_WAIT4_MSG}: {prompts} in line '{occurrence['line']}' '{occurrence}' in change state "
        f"'{state_before_test}' -> '{source_state}' -> '{target_state}'"
    )


def get_device(name, connection, device_output, test_file_path):
    dir_path = os.path.dirname(os.path.realpath(test_file_path))
    load_config(
        os.path.join(
            dir_path, os.pardir, os.pardir, "test", "resources", "device_config.yml"
        )
    )
    device = DeviceFactory.get_device(name, io_connection=connection)
    _prepare_device(device=device, connection=connection, device_output=device_output)
    return device


def _prepare_device(device, connection, device_output):
    if connection != device.io_connection:
        device.exchange_io_connection(io_connection=connection)
    assert "RemoteConnection" in device.io_connection.__class__.__name__
    connection.send_last_prompt_on_error = True
    connection.set_device(device=device)
    device.set_all_prompts_on_line(True)
    device.io_connection.remote_inject_response(device_output)
    assert device.io_connection.data == device_output
    if device._prompts_event is None:  # pylint: disable=protected-access
        device._run_prompts_observers()  # pylint: disable=protected-access
    assert device._check_all_prompts_on_line is True  # pylint: disable=protected-access
    assert device._prompts_event.check_against_all_prompts is True  # pylint: disable=protected-access
    connection.open()
    if device.current_state == "NOT_CONNECTED":
        if device._established is True:  # pylint: disable=protected-access
            device._established = False  # pylint: disable=protected-access
        device.establish_connection()
        if device.current_state == "NOT_CONNECTED":
            device.io_connection.inject(b"moler_bash#")
            time.sleep(0.2)
    assert device.current_state != "NOT_CONNECTED"


def get_cloned_device(src_device, new_name, new_connection):
    device_output = src_device.io_connection.data
    device = DeviceFactory.get_cloned_device(
        source_device=src_device,
        new_name=new_name,
        establish_connection=False,
        lazy_cmds_events=True,
        io_connection=new_connection,
    )
    _prepare_device(
        device=device, connection=new_connection, device_output=device_output
    )
    return device


class RemoteConnection(ThreadedFifoBuffer):
    def __init__(self, moler_connection, echo=True, name=None, logger_name=""):
        self.device = None
        self.data = None
        self.input_bytes = None
        self.send_last_prompt_on_error = False
        self._last_prompt = "".encode("utf-8")
        super(RemoteConnection, self).__init__(
            moler_connection=moler_connection,
            echo=echo,
            name=name,
            logger_name=logger_name,
        )

    def remote_inject_response(self, input_strings):
        """
        Simulate remote endpoint that sends response.
        Response is given as strings.
        """
        self.data = input_strings

    def _inject_deferred(self):
        """
        Inject response on connection.
        """
        if self.device.state == "NOT_CONNECTED":
            raise MolerException(
                f"Device '{self.device.name}' in unsupported state '{self.device.state}'."
            )
        cmd_data_string = self.input_bytes.decode("utf-8")
        if cmd_data_string:
            if "\n" in cmd_data_string:
                cmd_data_string = cmd_data_string[:-1]  # remove \n from command_string on connection
        else:
            cmd_data_string = self.input_bytes

        try:
            binary_cmd_ret = self.data[self.device.state][cmd_data_string].encode(
                "utf-8"
            )
            self._last_prompt = binary_cmd_ret
            self.inject([self.input_bytes + binary_cmd_ret])
        except KeyError as exc:
            if self.send_last_prompt_on_error and (cmd_data_string == "\x03"):  # ctrl+c
                self.inject([self.input_bytes + self._last_prompt])
                return
            try:
                available_outputs = self.data[self.device.state].keys()
            except (KeyError, AttributeError):
                available_outputs = f"No output for state '{self.device.state}'. Data: '{self.data}'."
            raise MolerException(
                f"No output for cmd: '{cmd_data_string}' in state '{self.device.state}'!\n"
                f"Available outputs for the state: '{available_outputs}'.\n"
                "Please update your device_output dict!\n"
                f"{exc}"
            ) from exc

    def write(self, input_bytes):
        """
        What is written to connection comes back on read()
        only if we simulate echo service of remote end.
        """
        if self.echo:
            self.inject([input_bytes])

        self.input_bytes = input_bytes
        self._inject_deferred()

    def set_device(self, device):
        """
        Need to get actual state of device when sending cmds response.
        """
        self.device = device

    send = write  # just alias to make base class happy :-)


def get_memory_device_connection():
    from moler.config.loggers import configure_device_logger
    from moler.moler_connection_for_single_thread_runner import (
        MolerConnectionForSingleThreadRunner,
    )

    moler_conn = MolerConnectionForSingleThreadRunner(
        encoder=lambda data: data.encode("utf-8"),
        decoder=lambda data: data.decode("utf-8"),
        name="buffer",
    )
    ext_io_in_memory = RemoteConnection(
        moler_connection=moler_conn, echo=False
    )  # we don't want echo on connection
    configure_device_logger(moler_conn.name)
    moler_conn.how2send = ext_io_in_memory.send
    return ext_io_in_memory


def _get_all_states_from_device(device):
    states = copy_list(device.states)
    states.remove("NOT_CONNECTED")
    assert "NOT_CONNECTED" not in states
    states_to_skip = "NOT_CONNECTED"

    for attr_name in dir(device):
        attr = getattr(device, attr_name)
        if type(attr) is str and not attr_name.startswith("_") and attr_name not in dir(TextualDevice):
            if attr not in states and attr not in states_to_skip:
                states.append(attr)

    if "PROXY_PC" in states and hasattr(device, "_use_proxy_pc") and not getattr(device, "_use_proxy_pc"):
        states.remove("PROXY_PC")
    assert "NOT_CONNECTED" not in states
    return states


def moler_check_sm_identity(devices: list):
    from moler.helpers import compare_objects
    from pprint import pformat
    dev0 = devices[0]
    states = _get_all_states_from_device(device=dev0)
    for dev1 in devices[1:]:
        assert dev0.name != dev1.name
        assert type(dev0).__name__ != type(dev1).__name__
        if dev0._stored_transitions != dev1._stored_transitions:
            print(f"dev0._stored_transitions=\n{pformat(dev0._stored_transitions)},\n dev1._stored_transitions={pformat(dev1._stored_transitions)}\n")
            print(f"diff: {compare_objects(dev0._stored_transitions, dev1._stored_transitions)}")
        assert dev0._stored_transitions == dev1._stored_transitions
        if dev0._state_hops != dev1._state_hops:
            print(f"dev0._state_hops={pformat(dev0._state_hops)}, dev1._state_hops={pformat(dev1._state_hops)}")
            print(f"diff: {compare_objects(dev0._state_hops, dev1._state_hops)}")
        assert dev0._state_hops == dev1._state_hops
        if dev0._state_prompts != dev1._state_prompts:
            print(f"dev0._state_prompts={pformat(dev0._state_prompts)}, dev1._state_prompts={pformat(dev1._state_prompts)}")
            print(f"diff: {compare_objects(dev0._state_prompts, dev1._state_prompts)}")
        assert dev0._state_prompts == dev1._state_prompts
        if dev0._configurations != dev1._configurations:
            print(f"dev0._configurations={pformat(dev0._configurations)}, dev1._configurations={pformat(dev1._configurations)}")
            print(f"diff: {compare_objects(dev0._configurations, dev1._configurations)}")
        assert dev0._configurations == dev1._configurations
        assert dev0._newline_chars == dev1._newline_chars
        for state in states:
            for observer in ['cmd', 'event']:
                obs0 = dev0._get_packages_for_state(state=state, observer=observer)
                obs1 = dev1._get_packages_for_state(state=state, observer=observer)
                if obs0 != obs1:
                    print(f"state={state}, observer={observer}, obs0={pformat(obs0)}, obs1={pformat(obs1)}")
                    print(f"diff: {compare_objects(obs0, obs1)}")
                assert obs0 == obs1


class DeviceCM:

    _any_instance = False

    def __init__(self, name, connection, device_output, test_file_path):
        self.name = name
        self.connection = connection
        self.device_output = device_output
        self.test_file_path = test_file_path
        self._device = None
        self._threading_tick = 1  # seconds to wait between checks if threads are finished after device removal
        self._thread_timeout = 20  # seconds to wait for threads to finish after device removal
        self._threads_nr = -1
        self._threads_names = []

    def __enter__(self):
        if self._device is None:
            for thread in threading.enumerate():
                if "RunnerSingle" in thread.name:
                    if DeviceCM._any_instance:
                        self._threads_nr = threading.active_count()
                        self._threads_names = [thread.name for thread in threading.enumerate()]
                        break
                    else:
                        DeviceCM._any_instance = True
            self._device = get_device(name=self.name, connection=self.connection, device_output=self.device_output,
                                      test_file_path=self.test_file_path)
        return self._device

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._device is not None:
            DeviceFactory.remove_device(device=self._device)
            self._device = None
        if self._threads_nr > 0:
            start_time = time.monotonic()
            current_threads_names = [thread.name for thread in threading.enumerate()]
            unexpected_thread_names = [name for name in current_threads_names if name not in self._threads_names]
            while threading.active_count() > self._threads_nr or len(unexpected_thread_names) > 0:
                current_threads_names = [thread.name for thread in threading.enumerate()]
                unexpected_thread_names = [name for name in current_threads_names if name not in self._threads_names]
                if time.monotonic() - start_time > self._thread_timeout:
                    break
                time.sleep(self._threading_tick)
            msg = (f"threads no after device removal: {threading.active_count()}, expected no more than {self._threads_nr}:"
                   f"current threads: {current_threads_names}, expected threads: {self._threads_names}, "
                   f"unexpected threads: {unexpected_thread_names}")
            assert threading.active_count() <= self._threads_nr and len(unexpected_thread_names) == 0, msg  # No new thread was left after device removal.
        else:
            time.sleep(3 * self._threading_tick)  # just wait a bit to be sure that all threads are finished after device removal
        return False  # don't suppress exceptions
