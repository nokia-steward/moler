# -*- coding: utf-8 -*-
"""
Moler's device has 2 main responsibilities:
- be the factory that returns commands of that device
- be the state machine that controls which commands may run in given state
"""
__author__ = "Grzegorz Latuszek, Marcin Usielski, Michal Ernst"
__copyright__ = "Copyright (C) 2018-2026, Nokia"
__email__ = (
    "grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com, michal.ernst@nokia.com"
)

import abc
import functools
import importlib
import inspect
import logging
import pkgutil
import queue
import re
import threading
import time
import traceback

from moler.config.loggers import change_logging_suffix, configure_device_logger
from moler.connection_factory import get_connection
from moler.connection_observer import ConnectionObserver
from moler.device.abstract_device import AbstractDevice
from moler.device.state_machine import StateMachine
from moler.exceptions import (
    CommandWrongState,
    DeviceChangeStateFailure,
    DeviceFailure,
    EventWrongState,
)
from moler.helpers import copy_dict, copy_list, update_dict
from moler.instance_loader import create_instance_from_class_fullname
from pprint import pformat


# TODO: name, logger/logger_name as param
class TextualDevice(AbstractDevice):
    cmds = "cmd"
    events = "event"

    not_connected = "NOT_CONNECTED"
    connection_hops = "CONNECTION_HOPS"

    def __init__(
        self,
        sm_params=None,
        name=None,
        io_connection=None,
        io_type=None,
        variant=None,
        io_constructor_kwargs=None,
        initial_state=None,
        lazy_cmds_events=False,
    ):
        """
        Create Device communicating over io_connection
        CAUTION: Device owns (takes over ownership) of connection. It will be open when device "is born" and close when
        device "dies".

        :param sm_params: dict with parameters of state machine for device
        :param name: name of device
        :param io_connection: External-IO connection having embedded moler-connection
        :param io_type: type of connection - tcp, udp, ssh, telnet, ...
        :param variant: connection implementation variant, ex. 'threaded', 'twisted', 'asyncio', ...
                        (if not given then default one is taken)
        :param io_constructor_kwargs: additional parameter into constructor of selected connection type
                        (if not given then default one is taken)
        :param initial_state: name of initial state. State machine tries to enter this state just after creation.
        :param lazy_cmds_events: set False to load all commands and events when device is initialized, set True to load
                        commands and events when they are required for the first time.
        """
        super(TextualDevice, self).__init__()
        if io_constructor_kwargs is None:
            io_constructor_kwargs = {}
        sm_params = copy_dict(sm_params, deep_copy=True)
        io_constructor_kwargs = copy_dict(io_constructor_kwargs, deep_copy=True)
        self.initial_state = (
            initial_state if initial_state is not None else "NOT_CONNECTED"
        )
        self.states = [TextualDevice.not_connected]
        self.goto_states_triggers = []
        self._name = name
        self.device_data_logger = None
        self.timeout_keep_state = (
            10  # Timeout for background goto state after unexpected state change.
        )
        self.lazy_cmds_events = (
            lazy_cmds_events  # Set True to lazy load commands and events.
        )

        # Below line will modify self extending it with methods and attributes od StateMachine
        # For eg. it will add attribute self.state
        self.SM = StateMachine(
            model=self,
            states=self.states,
            initial=TextualDevice.not_connected,
            auto_transitions=False,
            queued=True,
        )

        self._state_hops = {}
        self._state_prompts = {}
        self._state_prompts_lock = threading.Lock()
        self._reverse_state_prompts_dict = {}
        self._prompts_event = None
        self._kept_state = None
        self._configurations = {}
        self._newline_chars = {}  # key is state, value is chars to send as newline
        if io_connection:
            self.io_connection = io_connection
        else:
            self.io_connection = get_connection(
                io_type=io_type, variant=variant, **io_constructor_kwargs
            )

        self.io_connection.name = self.name
        self.io_connection.moler_connection.name = self.name
        self.logger = logging.getLogger(f"moler.connection.{self.name}")
        self.configure_logger(name=self.name, propagate=False)

        self._stored_transitions = {}
        self._prepare_sm_data(sm_params=sm_params)

        # TODO: Need test to ensure above sentence for all connection
        self.io_connection.notify(
            callback=self.on_connection_made, when="connection_made"
        )
        self.io_connection.notify(
            callback=self.on_connection_lost, when="connection_lost"
        )

        self._cmdnames_available_in_state = {}
        self._eventnames_available_in_state = {}
        self._default_prompt = re.compile(r"^[^<]*[\$|%|#|>|~]\s*$")
        self._neighbour_devices = None
        self._established = False
        msg = f"Created device '{self.name}' as instance of class '{self.__class__.__module__}.{self.__class__.__name__}'."
        self._log(level=logging.DEBUG, msg=msg)
        self._public_name = None
        self._warning_was_sent = False
        self._goto_state_lock = threading.Lock()
        self._goto_state_thread_manipulation_lock = threading.Lock()
        self._queue_states = queue.Queue()
        self._thread_for_goto_state = None
        self.SM.state_change_log_callable = self._log
        self.SM.current_state_callable = self._get_current_state
        self._goto_state_in_production_mode = True  # Set False only for tests. May cause problems in production code.
        self._check_all_prompts_on_line = False
        self.last_wrong_wait4_occurrence = None  # Last occurrence from Wait4prompts if at least 2 prompts matched the
        # same line.
        self._sleep_after_state_change = 0.5
        self._tick_to_check_runner = 0.1

    def _prepare_sm_data(self, sm_params):
        self._prepare_transitions()
        self._prepare_state_hops()
        self._configure_state_machine(sm_params)
        self._validate_device_configuration()
        self._prepare_state_prompts()
        self._prepare_newline_chars()
        self._send_transitions_to_sm(self._stored_transitions)

    def set_all_prompts_on_line(self, value=True):
        """
        Set True to check all prompts on line. False to interrupt after 1st prompt (default).
        :param value: True to check all prompts on line. False to interrupt after 1st prompt (default).
        :return: None
        """
        self._check_all_prompts_on_line = value
        if self._prompts_event:
            self._prompts_event.check_against_all_prompts = value

    def disable_logging(self):
        """
        Disable logging incoming data.
        :return: None
        """
        self.io_connection.disable_logging()

    def enable_logging(self):
        """
        Enable logging incoming data.
        :return: None
        """
        self.io_connection.enable_logging()

    def set_logging_suffix(self, suffix):
        """
        Set logging suffix.
        :param suffix: Suffix for device log. Use None for no suffix.
        :return: None
        """
        for logger in [self.device_data_logger, self.logger]:
            if logger is not None:
                logger_name = logger.name
                change_logging_suffix(suffix=suffix, logger_name=logger_name)

    def establish_connection(self):
        """
        Establishes real connection to device. You have to call this method before device is full operable.

        :return: None
        """
        if self._established:
            return
        self.io_connection.open()
        self.io_connection.moler_connection.open()

        self._collect_cmds_for_state_machine()
        self._collect_events_for_state_machine()
        with self._state_prompts_lock:
            self._run_prompts_observers()

        msg = (
            f"Established connection to device '{self.name}' ({self.public_name}) (as instance of class '{self.__class__.__module__}.{self.__class__.__name__}', "
            f"io_connection: '{self.io_connection.__class__.__module__}.{self.io_connection.__class__.__name__}', "
            f"moler_connection: '{self.io_connection.moler_connection.__class__.__module__}.{self.io_connection.moler_connection.__class__.__name__}') "
            f"with prompts: '{self._state_prompts}'."
        )
        self._established = True
        self._log(level=logging.INFO, msg=msg)

    def remove(self, stack_limit=6):
        """
        Closes device, if any command or event is attached to this device they will be finished.

        :param stack_limit: how many stack frames to keep. If None then all stack frames are kept.
        :return: None
        """
        mg = pformat(traceback.format_list(traceback.extract_stack(limit=stack_limit))[::-1])
        self._log(level=logging.INFO, msg=f"Device '{self.name}' is about to remove. Requested by: {mg}\n(...)")

        try:
            self.goto_state(TextualDevice.not_connected, rerun=5)
        except DeviceChangeStateFailure:
            self._close_connection(None, None, None)

        super(TextualDevice, self).remove()
        msg = f"Device '{self.name}' is closed."
        self._log(level=logging.INFO, msg=msg)
        self._close_logger()

    def has_established_connection(self):
        return self._established

    def add_neighbour_device(self, neighbour_device, bidirectional=True):
        """
        Adds neighbour device to this device.

        :param neighbour_device: device object or string with device name.
        :param bidirectional: If True then this device will be added to f_device.
        :return: None
        """
        if self._neighbour_devices is None:
            self._neighbour_devices = []
        if neighbour_device not in self._neighbour_devices:
            self._neighbour_devices.append(neighbour_device)
        if bidirectional:
            neighbour_device.add_neighbour_device(
                neighbour_device=self, bidirectional=False
            )

    def get_neighbour_devices(self, device_type):
        """
        Returns list of neighbour devices of passed type.

        :param device_type: type of device. If None then all neighbour devices will be returned.
        :return: list of devices.
        """
        neighbour_devices = []
        if self._neighbour_devices is not None:
            if device_type is None:
                neighbour_devices = copy_list(
                    src=self._neighbour_devices, deep_copy=False
                )
            else:
                for device in self._neighbour_devices:
                    if isinstance(device, device_type):
                        neighbour_devices.append(device)
        return neighbour_devices

    def calc_timeout_for_command(self, passed_timeout, configurations):
        command_timeout = None
        configuration_timeout = -1
        if "timeout" in configurations:
            configuration_timeout = float(configurations["timeout"])
        if passed_timeout <= 0 and configuration_timeout > 0:
            command_timeout = configuration_timeout
        elif passed_timeout > 0 and configuration_timeout <= 0:
            command_timeout = passed_timeout
        elif passed_timeout > 0 and configuration_timeout > 0:
            command_timeout = passed_timeout
            if configuration_timeout < passed_timeout:
                command_timeout = configuration_timeout
        return command_timeout

    def configure_logger(self, name, propagate):
        if not self.device_data_logger:
            self.device_data_logger = configure_device_logger(
                connection_name=name, propagate=propagate
            )

        self.io_connection.moler_connection.set_data_logger(self.device_data_logger)

    def _close_logger(self):
        self.device_data_logger.handlers = []

    @abc.abstractmethod
    def _prepare_transitions(self):
        pass

    @abc.abstractmethod
    def _prepare_state_prompts(self):
        pass

    @abc.abstractmethod
    def _prepare_newline_chars(self):
        pass

    @abc.abstractmethod
    def _prepare_state_hops(self):
        pass

    @classmethod
    def from_named_connection(cls, connection_name):
        io_conn = get_connection(name=connection_name)
        return cls(io_connection=io_conn)

    def __del__(self):
        self._stop_prompts_observers()

    def _load_cmdnames_for_state(self, state):
        """
        Load command names for state.

        :param state: name of state of the device.
        :return: None
        """
        self._cmdnames_available_in_state[state] = {}
        cmds = self._collect_cmds_for_state(state)
        self._cmdnames_available_in_state[state].update(cmds)

    def _load_eventnames_for_state(self, state):
        """
        Load event names for state.

        :param state: name of state of the device.
        :return: None
        """
        self._eventnames_available_in_state[state] = {}
        events = self._collect_events_for_state(state)
        self._eventnames_available_in_state[state].update(events)

    def _collect_cmds_for_state_machine(self):
        for state in self._get_available_states():
            if self.lazy_cmds_events:
                self._cmdnames_available_in_state[state] = None
            else:
                self._load_cmdnames_for_state(state=state)

    def _collect_events_for_state_machine(self):
        for state in self._get_available_states():
            if self.lazy_cmds_events:
                self._eventnames_available_in_state[state] = None
            else:
                self._load_eventnames_for_state(state=state)

    @property
    def current_state(self):
        return self.state

    def _get_current_state(self):
        """
        Pass reference to this method to state machine. State machine will call this method to read current state of
        device.

        :return: String with current state.
        """
        return self.current_state

    @property
    def name(self):
        if self._name:
            return self._name
        else:
            return self.io_connection.moler_connection.name

    @name.setter
    def name(self, value):
        if not self._name:
            self._name = value

    @property
    def public_name(self):
        """
        Getter for publicly used device name.

        Internal name of device (.name attribute) may be modified by device itself  in some circumstances (to not
        overwrite logs). However, public_name is guaranteed to be preserved as it was set by external/client code.

        :return: String with the device alias name.
        """
        ret = self.name
        if self._public_name:
            ret = self._public_name
        return ret

    @public_name.setter
    def public_name(self, value):
        """
        Setter for publicly used device name. If you clone devices and close them then if you want to create with
        already used name then device will be created with different name but public name will be as you want.

        :param value: String with device name.
        :return: None
        """
        if not self._public_name:
            self._public_name = value

    def _log(self, level, msg, extra=None):
        if self.logger:
            extra_params = {"log_name": self.name}

            if extra:
                extra_params.update(extra)

            self.logger.log(level, msg, extra=extra_params)

        self.device_data_logger.log(level, msg)

    def _set_state(self, state):
        if self.current_state != state:
            self.SM.set_state(state=state)
        if self._kept_state is not None and self.current_state != self._kept_state:
            state = self._kept_state
            self._recover_state(state=state)

    def goto_state(
        self,
        state,
        timeout=-1,
        rerun=0,
        send_enter_after_changed_state=False,
        log_stacktrace_on_fail=True,
        keep_state=False,
        timeout_multiply=1.0,
        sleep_after_changed_state=0.5,
    ):
        """
        Go to specific state.

        :param state: Name to state to change on the device.
        :param timeout: Timeout for changing state, if negative then timeout from commands are taken.
        :param rerun: How many times rerun the procedure before it fails.
        :param send_enter_after_changed_state: If True then enter is sent after state is changed. False nothing is sent.
        :param log_stacktrace_on_fail: Set True to have stacktrace in logs when failed, otherwise False.
        :param keep_state: if True and state is changed without goto_state then device tries to change state to state
         defined by goto_state.
        :param timeout_multiply: how many times multiply passed timeout to get final timeout.
        :param sleep_after_change: Time in seconds to sleep after state change.
        :return: None
        :raise: DeviceChangeStateFailure if cannot change the state of device.
        """
        self._sleep_after_state_change = sleep_after_changed_state
        self._kept_state = None
        if not self.has_established_connection():
            self.establish_connection()
        if self.current_state == state:
            if keep_state:
                self._kept_state = state
            return

        self._queue_states.empty()
        self._goto_state_execute(
            dest_state=state,
            keep_state=keep_state,
            timeout=timeout,
            rerun=rerun,
            send_enter_after_changed_state=send_enter_after_changed_state,
            log_stacktrace_on_fail=log_stacktrace_on_fail,
            queue_if_goto_state_in_another_thread=True,
            ignore_exceptions=False,
            timeout_multiply=timeout_multiply,
        )

    def goto_state_bg(self, state, keep_state=False):
        """
        Starts to go to state. Returns immediately.
        :param state: name of state.
        :param keep_state: if True and state is changed without goto_state then device tries to change state to state
        defined by goto_state.
        :return: None
        """
        self._recover_state(state=state, keep_state=keep_state)

    def await_goto_state(self, timeout=10):
        """
        Waits till goto_state chain is empty.
        :param timeout: timeout in seconds.
        :return: None
        :raise DeviceChangeStateFailure: if the goto_state chain is not empty and timeout occurs.
        """
        start_time = time.monotonic()
        while time.monotonic() - start_time <= timeout:
            if self._queue_states.empty() and self._thread_for_goto_state is None:
                return
        raise DeviceChangeStateFailure(
            device=self.__class__.__name__,
            exception=f"After {time.monotonic() - start_time} seconds there are still states to go: '{list(self._queue_states.queue)}' and/or thread to change state. {self._thread_for_goto_state}",
            device_name=self.name,
        )

    def _recover_state(self, state, keep_state=True):
        if self._goto_state_in_production_mode is False:
            return
        with self._goto_state_thread_manipulation_lock:
            state_options = {
                "dest_state": state,
                "keep_state": keep_state,
                "timeout": self.timeout_keep_state,
                "rerun": 0,
                "send_enter_after_changed_state": False,
                "log_stacktrace_on_fail": False,
                "queue_if_goto_state_in_another_thread": False,
                "ignore_exceptions": True,
            }
            self._queue_states.put(state_options)
            if self._thread_for_goto_state is None:
                thread = threading.Thread(
                    target=self._goto_state_thread,
                    name=f"GotoStateThread-{self.name}",
                )
                thread.daemon = True
                thread.start()
                self._thread_for_goto_state = thread

    def _goto_state_thread(self):
        while True:
            with self._goto_state_thread_manipulation_lock:
                try:
                    goto_data = self._queue_states.get(True, 0.01)
                except queue.Empty:
                    self._thread_for_goto_state = None
                    break
                self._goto_state_execute(**goto_data)

    def _goto_state_execute(
        self,
        dest_state,
        keep_state,
        timeout,
        rerun,
        send_enter_after_changed_state,
        log_stacktrace_on_fail,
        queue_if_goto_state_in_another_thread,
        ignore_exceptions=False,
        timeout_multiply=1.0,
    ):
        if (self._goto_state_in_production_mode and self._goto_state_lock.acquire(
                queue_if_goto_state_in_another_thread)) or (self._goto_state_in_production_mode is False):
            try:
                self._goto_state_to_run_in_try(
                    dest_state=dest_state,
                    keep_state=keep_state,
                    timeout=timeout,
                    rerun=rerun,
                    send_enter_after_changed_state=send_enter_after_changed_state,
                    log_stacktrace_on_fail=log_stacktrace_on_fail,
                    timeout_multiply=timeout_multiply,
                )
            except Exception as ex:
                if ignore_exceptions is False:
                    raise ex
            finally:
                if self._goto_state_in_production_mode:
                    self._goto_state_lock.release()
        else:
            self._log(
                logging.WARNING,
                f"{self.name}: Another thread in goto_state. Didn't try to go to '{dest_state}'.",
            )

    def _goto_state_to_run_in_try(
        self,
        dest_state,
        keep_state,
        timeout,
        rerun,
        send_enter_after_changed_state,
        log_stacktrace_on_fail,
        timeout_multiply,
    ):
        if self.current_state == dest_state:
            if keep_state:
                self._kept_state = dest_state
            return
        self._log(
            logging.DEBUG,
            f"Go to state '{dest_state}' from '{self.current_state}'",
        )

        is_dest_state = False
        is_timeout = False
        start_time = time.monotonic()
        final_timeout = timeout_multiply * timeout
        next_stage_timeout = final_timeout

        while (not is_dest_state) and (not is_timeout):
            next_state = self._get_next_state(dest_state)
            if self.current_state != dest_state:
                self._trigger_change_state(
                    next_state=next_state,
                    timeout=next_stage_timeout,
                    rerun=rerun,
                    send_enter_after_changed_state=send_enter_after_changed_state,
                    log_stacktrace_on_fail=log_stacktrace_on_fail,
                )

            if self.current_state == dest_state:
                is_dest_state = True

            if timeout > 0:
                next_stage_timeout = final_timeout - (time.monotonic() - start_time)
                if next_stage_timeout <= 0:
                    is_timeout = True
        if self._sleep_after_state_change is not None and self._sleep_after_state_change > 0:
            time.sleep(self._sleep_after_state_change)
        if keep_state:
            self._kept_state = dest_state
        self._warning_was_sent = False

    def _get_next_state(self, dest_state):
        next_state = None
        if self.current_state in self._state_hops.keys():
            if dest_state in self._state_hops[self.current_state].keys():
                next_state = self._state_hops[self.current_state][dest_state]

        if not next_state:  # direct transition without hops
            next_state = dest_state

        return next_state

    def _trigger_change_state(
        self,
        next_state,
        timeout,
        rerun,
        send_enter_after_changed_state,
        log_stacktrace_on_fail=True,
    ):
        self._log(
            logging.DEBUG,
            f"'{self.name}'. Changing state from '{self.current_state}' into '{next_state}'.",
        )
        change_state_method = None
        # all state triggers used by SM are methods with names starting from "GOTO_"
        # for e.g. GOTO_REMOTE, GOTO_CONNECTED
        for goto_method in self.goto_states_triggers:
            if f"GOTO_{next_state}" == goto_method:
                change_state_method = getattr(self, goto_method)

        if change_state_method:
            self._trigger_change_state_loop(
                rerun=rerun,
                next_state=next_state,
                change_state_method=change_state_method,
                timeout=timeout,
                log_stacktrace_on_fail=log_stacktrace_on_fail,
                send_enter_after_changed_state=send_enter_after_changed_state,
            )
        else:
            exc = DeviceFailure(
                device=self.__class__.__name__,
                message=f"{self.name}. Failed to change state from '{self.state}' to '{next_state}'. "
                "Either target state does not exist in SM or there is no direct/indirect transition "
                "towards target state. Try to change state machine definition. "
                f"Available states: {self.states}",
            )
            if log_stacktrace_on_fail:
                self._log(logging.ERROR, exc)
            raise exc

    def _trigger_change_state_loop(
        self,
        rerun,
        next_state,
        change_state_method,
        timeout,
        log_stacktrace_on_fail,
        send_enter_after_changed_state,
    ):
        entered_state = False
        retrying = 0
        while retrying <= rerun and (not entered_state) and (self.current_state is not next_state):
            try:
                change_state_method(self.current_state, next_state, timeout=timeout)
                entered_state = True
            # pylint: disable-next=unused-variable
            except Exception as ex:
                if self.current_state == next_state:
                    ex_traceback = traceback.format_exc()
                    msg = f"Method to change state failed but device '{self.name}' is in proper state '{self.current_state}'. Exception: {ex_traceback}"
                    self._log(logging.WARNING, msg=msg)
                elif retrying == rerun:
                    ex_traceback = traceback.format_exc()
                    exc = DeviceChangeStateFailure(
                        device=self.__class__.__name__,
                        exception=ex_traceback,
                        device_name=self.name,
                    )
                    self._log(
                        logging.WARNING,
                        msg=f"Cannot change state into '{next_state}' Current state '{self.current_state}'. After '{rerun}' rerun(s).",
                    )
                    if log_stacktrace_on_fail:
                        self._log(logging.ERROR, exc)
                    raise exc from ex
                else:
                    retrying += 1
                    self._log(
                        logging.DEBUG,
                        f"Cannot change state into '{next_state}'. Retrying '{retrying}' of '{rerun}' times.",
                    )
                    if send_enter_after_changed_state:
                        self._send_enter_after_changed_state()
        if self.current_state == next_state:
            self.io_connection.moler_connection.change_newline_seq(
                self._get_newline(state=next_state)
            )
            if send_enter_after_changed_state:
                self._send_enter_after_changed_state()
            self._log(
                logging.DEBUG,
                f"{self.name}: Successfully enter state '{next_state}'",
            )

    def on_connection_made(self, connection):
        self._set_state(TextualDevice.connected)

    def on_connection_lost(self, connection):
        self._set_state(TextualDevice.not_connected)

    @abc.abstractmethod
    def _get_packages_for_state(self, state, observer):
        """
        Returns list of packages (list of strings) for a given state
        :param state: state name
        :param observer: type of return packages - Device.events or Device.cmds
        :return: list of packages
        """
        return []  # Workaround for test_device.py test test_device_may_be_created_on_named_connection

    # Overload when more states
    def _get_available_states(self):
        """
        :return: List of all states for a device.
        """
        return self.states

    def _load_cmds_from_package(self, package_name):
        available_cmds = {}
        basic_module = importlib.import_module(package_name)
        try:
            mod_path = basic_module.__path__
        except AttributeError:
            module_available_cmds = self._load_cmds_from_module(
                module_name=package_name
            )
            available_cmds.update(module_available_cmds)
        else:
            # pylint: disable-next=unused-variable
            for importer, modname, is_pkg in pkgutil.iter_modules(mod_path):
                module_name = f"{package_name}.{modname}"
                module_available_cmds = self._load_cmds_from_module(module_name)
                available_cmds.update(module_available_cmds)

        return available_cmds

    def _load_cmds_from_module(self, module_name):
        available_cmds = {}

        module = importlib.import_module(module_name)
        for cmd_class_name, cmd_module_name in inspect.getmembers(
            module, inspect.isclass
        ):
            if cmd_module_name.__module__ == module_name:
                cmd_class_obj = getattr(module, cmd_class_name)
                if issubclass(
                    cmd_class_obj, ConnectionObserver
                ):  # module may contain other classes (f.ex. exceptions)
                    # like:  IpAddr --> ip_addr
                    cmd_name = cmd_class_obj.observer_name
                    # like:  IpAddr --> moler.cmd.unix.ip_addr.IpAddr
                    cmd_class_fullname = f"{module_name}.{cmd_class_name}"

                    available_cmds.update({cmd_name: cmd_class_fullname})
        return available_cmds

    def _get_observer_in_state(self, observer_name, observer_type, for_state, **kwargs):
        """Return Observable object assigned to observer_name of given device"""
        # TODO: return observer object wrapped in decorator mocking it's start()
        available_observer_names = []
        if not for_state:
            for_state = self.current_state
        if observer_type == TextualDevice.cmds:
            available_observer_names = self._cmdnames_available_in_state[for_state]
        elif observer_type == TextualDevice.events:
            available_observer_names = self._eventnames_available_in_state[for_state]
        if observer_name in available_observer_names:
            observer_params = dict(
                kwargs, connection=self.io_connection.moler_connection
            )
            observer = create_instance_from_class_fullname(
                class_fullname=available_observer_names[observer_name],
                constructor_parameters=observer_params,
            )
            return observer

        exc = DeviceFailure(
            device=self.__class__.__name__,
            message=f"Failed to create {observer_type}-object for '{observer_name}' {observer_type}."
                    f" '{observer_name}' {observer_type} is unknown for state '{for_state}' of device "
                    f"'{self.__class__.__name__}'. Available names: {available_observer_names}."
        )
        self._log(logging.ERROR, exc)
        raise exc

    def _create_cmd_instance(self, cmd_name, for_state, **kwargs):
        """
        CAUTION: it checks if cmd may be created in current_state of device
        """
        if for_state not in self._cmdnames_available_in_state:
            self._cmdnames_available_in_state[for_state] = None
        if self._cmdnames_available_in_state[for_state] is None:
            self._load_cmdnames_for_state(state=for_state)
        return self._get_observer_in_state(
            observer_name=cmd_name,
            observer_type=TextualDevice.cmds,
            for_state=for_state,
            **kwargs,
        )

    def _create_event_instance(self, event_name, for_state, **kwargs):
        """
        CAUTION: it checks if event may be created in current_state of device
        """
        if for_state not in self._eventnames_available_in_state:
            self._eventnames_available_in_state[for_state] = None
        if self._eventnames_available_in_state[for_state] is None:
            self._load_eventnames_for_state(state=for_state)
        return self._get_observer_in_state(
            observer_name=event_name,
            observer_type=TextualDevice.events,
            for_state=for_state,
            **kwargs,
        )

    def get_observer(
        self,
        observer_name,
        observer_type,
        observer_exception,
        check_state=True,
        for_state=None,
        **kwargs,
    ):
        if not for_state:
            for_state = self.current_state
        observer = None
        if observer_type == TextualDevice.cmds:
            observer = self._create_cmd_instance(
                observer_name, for_state=for_state, **kwargs
            )
        elif observer_type == TextualDevice.events:
            observer = self._create_event_instance(
                observer_name, for_state=for_state, **kwargs
            )

        if check_state:
            original_fun = observer._validate_start  # pylint: disable=protected-access
            creation_state = for_state

            @functools.wraps(observer._validate_start)  # pylint: disable=protected-access
            def validate_device_state_before_observer_start(*args, **kargs):
                current_state = self.current_state
                if current_state == creation_state:
                    ret = original_fun(*args, **kargs)
                    return ret
                else:
                    exc = observer_exception(observer, creation_state, current_state)
                    self._log(logging.ERROR, exc)
                    raise exc

            observer._validate_start = validate_device_state_before_observer_start  # pylint: disable=protected-access
        return observer

    def get_cmd(self, cmd_name, cmd_params=None, check_state=True, for_state=None):
        """
        Return instance of command connected with the device.

        :param cmd_name: name of commands, name of class (without package), for example "cd".
        :param cmd_params: dict with command parameters.
        :param check_state: if True then before execute of command the state of device will be check if the same
         as when command was created. If False the device state is not checked.
        :param for_state: if None then command object for current state is returned, otherwise object for for_state is
         returned.
        :return: Instance of command
        """
        cmd_params = copy_dict(cmd_params)
        if "prompt" not in cmd_params:
            cmd_params["prompt"] = self.get_prompt()
        cmd = self.get_observer(
            observer_name=cmd_name,
            observer_type=TextualDevice.cmds,
            observer_exception=CommandWrongState,
            check_state=check_state,
            for_state=for_state,
            **cmd_params,
        )
        from moler.cmd.commandtextualgeneric import CommandTextualGeneric
        assert isinstance(cmd, CommandTextualGeneric)
        return cmd

    def get_event(
        self, event_name, event_params=None, check_state=True, for_state=None
    ):
        """
        Return instance of event connected with the device.

        :param event_name: name of event, name of class (without package).
        :param event_params: dict with event parameters.
        :param check_state: if True then before execute of event the state of device will be check if the same
         as when event was created. If False the device state is not checked.
        :param for_state: if None then event object for current state is returned, otherwise object for for_state is
         returned.
        :return: Event object
        """
        event_params = copy_dict(event_params)
        event = self.get_observer(
            observer_name=event_name,
            observer_type=TextualDevice.events,
            observer_exception=EventWrongState,
            check_state=check_state,
            for_state=for_state,
            **event_params,
        )

        return event

    def run(self, cmd_name, **kwargs):
        """
        Wrapper for simple use:

        return ux.run('cd', path="/home/user/")

        Command/observer object is created locally
        """
        cmd = self.get_cmd(cmd_name=cmd_name, **kwargs)
        return cmd()

    def start(self, cmd_name, **kwargs):
        """
        Wrapper for simple use:

        localhost_ping = ux.start('ping', destination="localhost", options="-c 5")
        ...
        result = localhost_ping.await_done()

        result = await localhost_ping  # py3 notation

        Command/observer object is created locally
        """
        cmd = self.get_cmd(cmd_name=cmd_name, **kwargs)
        return cmd.start()

    def _collect_observer_for_state(self, observer_type, state):
        observer = {}

        for package_name in self._get_packages_for_state(
            state=state, observer=observer_type
        ):
            observer.update(self._load_cmds_from_package(package_name))

        return observer

    def _collect_cmds_for_state(self, state):
        cmds = self._collect_observer_for_state(
            observer_type=TextualDevice.cmds, state=state
        )

        return cmds

    def _collect_events_for_state(self, state):
        events = self._collect_observer_for_state(
            observer_type=TextualDevice.events, state=state
        )

        return events

    def _add_transitions(self, transitions: dict):
        self._update_dict(self._stored_transitions, transitions)

    def _send_transitions_to_sm(self, transitions: dict) -> None:
        for source_state in transitions.keys():
            for dest_state in transitions[source_state].keys():
                self._update_SM_states(dest_state)

                single_transition = [
                    {
                        "trigger": self.build_trigger_to_state(dest_state),
                        "source": source_state,
                        "dest": dest_state,
                        "prepare": transitions[source_state][dest_state]["action"],
                    },
                ]

                self.SM.add_transitions(single_transition)

    def _update_SM_states(self, state):
        if state not in self.states:
            self.SM.add_state(state)
            self.states.append(state)

    def exchange_io_connection(self, io_connection):
        self._close_connection(None, None, None)
        self.io_connection = io_connection
        self.io_connection.set_device(self)
        self.io_connection.open()
        self._set_state("UNIX_LOCAL")
        self._run_prompts_observers()

    # pylint: disable-next=unused-argument
    def _open_connection(self, source_state, dest_state, timeout):
        self.establish_connection()

    # pylint: disable-next=unused-argument
    def _close_connection(self, source_state, dest_state, timeout):
        self._stop_prompts_observers()
        self.io_connection.close()
        self._established = False

    def _prompts_observer_callback(self, event):
        occurrence = event.get_last_occurrence()
        state = occurrence["state"]
        line = occurrence["line"]
        matched = occurrence["matched"]
        if self._check_all_prompts_on_line and len(occurrence["list_matched"]) > 1:
            prompts = [{item["state"]: item["prompt_regex"]} for item in
                       occurrence["list_matched"]]
            self._log(
                level=logging.WARNING,
                msg=f"Prompts {prompts} match the same line '{line}'",
            )
            self._log(
                level=logging.ERROR,
                msg=f"More than 1 prompt matched the same line! '{occurrence}'.",
            )
            self.last_wrong_wait4_occurrence = occurrence
            # Ambiguous line does not identify the state - changing it here would race with state machine transitions.
            return
        msg = f"Callback for state {state} for line >>{line}<<, matched: '{matched}'."
        if self.current_state != state:
            self._log(level=logging.INFO, msg=msg)
            self._set_state(state)
        else:
            self._log(level=logging.DEBUG, msg=msg)

    def _get_for_state_to_run_prompts_observers(self):
        for_state = None
        if self.current_state == "NOT_CONNECTED":
            for state in self._state_hops:
                if state.find("UNIX") != -1 or state.find("LINUX") != -1:
                    for_state = state
                    break
            if for_state is None:
                # noinspection PyUnresolvedReferences
                for_state = self._state_hops.keys()[0]
        return for_state

    def _run_prompts_observers(self):
        self._validate_prompts_uniqueness()
        self._prepare_reverse_state_prompts_dict()

        for_state = self._get_for_state_to_run_prompts_observers()
        if self._prompts_event is not None:
            self._stop_prompts_observers()
        self._prompts_event = self.get_event(
            event_name="wait4prompts",
            event_params={
                "prompts": self._reverse_state_prompts_dict,
                "till_occurs_times": -1,
            },
            check_state=False,
            for_state=for_state,
        )

        self._prompts_event.add_event_occurred_callback(
            callback=self._prompts_observer_callback,
            callback_params={
                "event": self._prompts_event,
            },
        )
        self._prompts_event.check_against_all_prompts = self._check_all_prompts_on_line
        self._prompts_event.disable_log_occurrence()
        self._prompts_event.start()
        start_time = time.monotonic()
        while self._prompts_event.is_in_runner() is False:
            if time.monotonic() - start_time > 10:
                self._log(
                    logging.WARNING,
                    f"Cannot start prompts observers properly. Still not in runner after {time.monotonic() - start_time} seconds.",
                )
                break
            time.sleep(self._tick_to_check_runner)

    def _prepare_reverse_state_prompts_dict(self):
        for state in self._state_prompts.keys():
            prompt = self._state_prompts[state]
            self._reverse_state_prompts_dict[prompt] = state

    def _validate_prompts_uniqueness(self):
        prompts = {}
        error_message = ""

        for state in self._state_prompts.keys():
            prompt = self._state_prompts[state]

            if prompt not in prompts.keys():
                prompts[prompt] = state
            else:
                error_message += f"\n'{prompt}' -> '{prompts[prompt]}', '{state}'"

        if error_message:
            exc = DeviceFailure(
                device=self.__class__.__name__,
                message=f"Incorrect device configuration. The same prompts for states: {error_message}.",
            )
            self._log(logging.ERROR, exc)
            raise exc

    def _stop_prompts_observers(self):
        try:
            if self._prompts_event:
                event = self._prompts_event
                self._prompts_event = None
                event.cancel()
                start_stop_event = time.monotonic()
                while event.is_in_runner() is True:
                    if time.monotonic() - start_stop_event > 10:
                        self._log(
                            logging.WARNING,
                            f"Cannot stop prompts observers properly. Still in runner after {time.monotonic() - start_stop_event} seconds.",
                        )
                        break
                    time.sleep(self._tick_to_check_runner)
                event.remove_event_occurred_callback()
        except Exception:
            pass

    def build_trigger_to_state(self, state):
        trigger = f"GOTO_{state}"
        if trigger not in self.goto_states_triggers:
            self.goto_states_triggers += [trigger]
        return trigger

    def get_prompt(self):
        state = self.current_state
        prompt = self._default_prompt
        if state in self._state_prompts:
            prompt = self._state_prompts[state]
            if not hasattr(prompt, "match"):
                prompt = re.compile(prompt)
        return prompt

    def _configure_state_machine(self, sm_params):
        default_sm_configurations = self._get_default_sm_configuration()
        self._configurations = self._prepare_sm_configuration(
            default_sm_configurations, sm_params
        )

    def _prepare_sm_configuration(self, default_sm_configurations, sm_params):
        """
        Prepare SM configuration by update default SM configuration with SM params read from config dict/file
        :param default_sm_configurations: Default SM configuration for specific device
        :param sm_params: SM configuration read from dict/file
        :return: prepared SM configuration for specific device
        """
        sm_configuration = {}
        self._update_dict(sm_configuration, default_sm_configurations)
        self._update_dict(sm_configuration, sm_params)

        return sm_configuration

    def _update_dict(self, target_dict, expand_dict):
        update_dict(target_dict, expand_dict)

    def _get_default_sm_configuration(self):
        config = {TextualDevice.connection_hops: {}}

        return config

    def get_configurations(self, source_state, dest_state):
        if source_state and dest_state:
            return self._configurations[TextualDevice.connection_hops][source_state][
                dest_state
            ]

    def _validate_device_configuration(self):
        exception_message = ""
        configuration = self._configurations[TextualDevice.connection_hops]

        for source_state in configuration.keys():
            for dest_state in configuration[source_state].keys():
                if (
                    "required_command_params"
                    in configuration[source_state][dest_state].keys()
                ):
                    for required_command_param in configuration[source_state][
                        dest_state
                    ]["required_command_params"]:
                        if (
                            required_command_param
                            not in configuration[source_state][dest_state][
                                "command_params"
                            ]
                        ):
                            exception_message += f"\n'{required_command_param}' in 'command_params' in transition from '{source_state}' to '{dest_state}'"

        if exception_message:
            exc = DeviceFailure(
                device=self.__class__.__name__,
                message=f"Missing required parameter(s). There is no required parameter(s):{exception_message}",
            )
            self._log(logging.ERROR, exc)
            raise exc

    # pylint: disable-next=unused-argument
    def _send_enter_after_changed_state(self, *args, **kwargs):
        from moler.cmd.unix.enter import Enter

        try:
            cmd_enter = Enter(connection=self.io_connection.moler_connection)
            cmd_enter()
        except Exception as ex:
            self._log(
                logging.DEBUG, f"Cannot execute command 'enter' properly: {ex}"
            )

    def _get_newline(self, state=None):
        if not state:
            state = self.current_state
        if state and state in self._newline_chars:
            return self._newline_chars[state]
        return "\n"

    def _is_proxy_pc_in_sm_params(self, sm_params, proxy):
        """
        Check that specific SM state is inside sm configuration
        :param sm_params: sm configuration
        :param proxy: specific sm state
        :return: True when specific state exist, otherwise False
        """
        if proxy in sm_params:
            return True

        # pylint: disable-next=unused-variable
        for key, value in sm_params.items():
            if isinstance(value, dict):
                item = self._is_proxy_pc_in_sm_params(value, proxy)
                if item is not None:
                    return item

        return False
