# -*- coding: utf-8 -*-
"""
Moler's device has 2 main responsibilities:
- be the factory that returns commands of that device
- be the state machine that controls which commands may run in given state
"""

__author__ = 'Michal Ernst, Grzegorz Latuszek, Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'michal.ernst@nokia.com, grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com'

import re
import six
import abc
import platform
import time

from moler.device.textualdevice import TextualDevice
from moler.device.unixlocal import UnixLocal
from moler.exceptions import MolerException
try:
    from moler.io.raw.terminal import ThreadedTerminal
    from moler.io.raw.terminal_no_fork import ThreadedTerminalNoFork
except ImportError:  # ThreadedTerminal won't load on Windows
    ThreadedTerminal = None
    ThreadedTerminalNoFork = None

from moler.events.shared.wait4 import Wait4
import inspect
import threading

# helper variables to improve readability of state machines
# f.ex. moler.device.textualdevice introduces state TextualDevice.not_connected = "NOT_CONNECTED"
NOT_CONNECTED = TextualDevice.not_connected
CONNECTION_HOPS = TextualDevice.connection_hops
UNIX_LOCAL = UnixLocal.unix_local
UNIX_LOCAL_ROOT = UnixLocal.unix_local_root
PROXY_PC = "PROXY_PC"


def want_local_unix_state(io_type=None, io_connection=None):
    """
    Check if device is intended to work with local machine or remote ones only.
    :return: True for local.
    """
    if io_type == "terminal":
        return True
    if (platform.system() != 'Windows') and isinstance(io_connection, (ThreadedTerminal, ThreadedTerminalNoFork)):
        return True
    else:  # all remote-access connections (tcp, udp, telnet, ssh); even connecting to localhost
        return False


@six.add_metaclass(abc.ABCMeta)
class ProxyPc2(UnixLocal):

    def __init__(self, sm_params, name=None, io_connection=None, io_type=None, variant=None, io_constructor_kwargs=None,
                 initial_state=None, lazy_cmds_events=False):
        """
        Create Unix device communicating over io_connection.

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
        self._detecting_prompt_cmd = "echo DETECTING PROMPT"
        self.__prompt_detected = False
        self._use_local_unix_state = want_local_unix_state(io_type, io_connection)
        base_state = UNIX_LOCAL if self._use_local_unix_state else NOT_CONNECTED
        self._use_proxy_pc = self._should_use_proxy_pc(sm_params, PROXY_PC)
        base_or_final_state = PROXY_PC if self._use_proxy_pc else base_state
        initial_state = initial_state if initial_state is not None else base_or_final_state
        super(ProxyPc2, self).__init__(name=name, io_connection=io_connection,
                                       io_type=io_type, variant=variant,
                                       io_constructor_kwargs=io_constructor_kwargs,
                                       sm_params=sm_params, initial_state=initial_state,
                                       lazy_cmds_events=lazy_cmds_events)
        self._prompt_detector_timeout = 3.9
        self._after_open_prompt_detector = None
        self._warn_about_temporary_life_of_class()

    @property
    def _prompt_detected(self):
        """
        Get prompt detected.
        :return: bool value.
        """
        return self.__prompt_detected

    @_prompt_detected.setter
    def _prompt_detected(self, value):
        """
        Set prompt detected.
        :param value: bool value.
        :return: None
        """
        frame = inspect.currentframe().f_back
        caller = frame.f_code.co_name
        msg = f"Setter _prompt_detected: {self.__prompt_detected} -> {value} called by {caller}"
        self.logger.debug(msg)
        self.__prompt_detected = value

    def _warn_about_temporary_life_of_class(self):
        what = "experimental/temporary implementation of device utilizing sshshell connection"
        temporary_classname = self.__class__.__name__
        target_classname = temporary_classname[:-1]
        merge_info = "Its functionality will be merged"
        future_change = f"{merge_info} into {target_classname} device in the distant future and {temporary_classname} will be removed"
        warn_msg = f"Class {temporary_classname} is an {what}. {future_change}."
        self.logger.warning(warn_msg)

    def _should_use_proxy_pc(self, sm_params, proxy):
        proxy_in_config = self._is_proxy_pc_in_sm_params(sm_params, proxy)
        if (not proxy_in_config) and (not self._use_local_unix_state) and (self.__class__.__name__ == 'ProxyPc2'):
            return True  # ProxyPc is target of connection open
        return proxy_in_config

    def goto_state(self, state, *args, **kwargs):
        """Goes to specific state."""
        if ((state == UNIX_LOCAL) or (state == UNIX_LOCAL_ROOT)) and (not self._use_local_unix_state):
            used_io = f"{self.io_connection.__class__.__name__} {self.io_connection}"
            msg = f"Device {self} has no {UNIX_LOCAL}/{UNIX_LOCAL_ROOT} states"
            why = f"since it uses following io: {used_io}"
            fix = 'You need io of type "terminal" to have unix-local states'
            err_msg = f"{msg} {why}. {fix}."
            raise ValueError(err_msg)
        super(ProxyPc2, self).goto_state(state=state, *args, **kwargs)

    def _get_default_sm_configuration(self):
        """
        Create State Machine default configuration.
        :return: default sm configuration.
        """
        config = {}
        if self._use_local_unix_state:
            config = super(ProxyPc2, self)._get_default_sm_configuration()

        if self._use_proxy_pc:
            default_config = self._get_default_sm_configuration_with_proxy_pc()
        else:
            default_config = self._get_default_sm_configuration_without_proxy_pc()
        self._update_dict(config, default_config)
        return config

    def _get_default_sm_configuration_with_proxy_pc(self):
        """
        Return State Machine default configuration with proxy_pc state.
        :return: default sm configuration with proxy_pc state.
        """
        if self._use_local_unix_state:
            config = {
                CONNECTION_HOPS: {
                    UNIX_LOCAL: {  # from
                        PROXY_PC: {  # to
                            "execute_command": "ssh",  # using command
                            "command_params": {  # with parameters
                                "target_newline": "\n"
                            },
                            "required_command_params": [
                                "host",
                                "login",
                                "password",
                                "expected_prompt"
                            ]
                        },
                    },
                    PROXY_PC: {  # from
                        UNIX_LOCAL: {  # to
                            "execute_command": "exit",  # using command
                            "command_params": {  # with parameters
                                "target_newline": "\n",
                                "expected_prompt": r'^moler_bash#',
                            },
                            "required_command_params": [
                            ]
                        }
                    },
                }
            }
        else:
            config = {}  # no config needed, will open connection to directly jump NOT_CONNECTED -> PROXY_PC
        return config

    def _get_default_sm_configuration_without_proxy_pc(self):
        """
        Return State Machine default configuration without proxy_pc state.
        :return: default sm configuration without proxy_pc state.
        """
        config = {}
        return config

    def _prepare_transitions(self):
        """
        Prepare transitions to change states.
        :return: None
        """
        if self._use_local_unix_state:
            super(ProxyPc2, self)._prepare_transitions()

        if self._use_proxy_pc:
            transitions = self._prepare_transitions_with_proxy_pc()
        else:
            transitions = self._prepare_transitions_without_proxy_pc()
        self._add_transitions(transitions=transitions)

    def _prepare_transitions_with_proxy_pc(self):
        """
        Prepare transitions to change states with proxy_pc state.
        :return: transitions with proxy_pc state.
        """
        if self._use_local_unix_state:
            transitions = {
                UNIX_LOCAL: {
                    PROXY_PC: {
                        "action": [
                            "_execute_command_to_change_state"
                        ],
                    }
                },
                PROXY_PC: {
                    UNIX_LOCAL: {
                        "action": [
                            "_execute_command_to_change_state"
                        ],
                    },
                },
            }
        else:  # directly from NOT_CONNECTED to PROXY_PC
            transitions = {
                NOT_CONNECTED: {
                    PROXY_PC: {
                        "action": [
                            "_open_connection"
                        ],
                    }
                },
                PROXY_PC: {
                    NOT_CONNECTED: {
                        "action": [
                            "_close_connection"
                        ],
                    },
                },
            }
        return transitions

    def _prepare_transitions_without_proxy_pc(self):
        """
        Prepare transitions to change states without proxy_pc state.
        :return: transitions without proxy_pc state.
        """
        transitions = {}
        return transitions

    def on_connection_made(self, connection):
        """
        Execute action when connection made.
        :param connection: device connection.
        :return: None
        """
        self.logger.info(f"Connection made: {connection}")
        if self._use_local_unix_state:
            super(ProxyPc2, self).on_connection_made(connection)
            self._prompt_detected = True  # prompt defined in SM
        else:
            self._prompt_detected = False  # prompt not defined in SM
            self._set_state(PROXY_PC)
            self._detect_after_open_prompt(self._set_after_open_prompt)

    def on_connection_lost(self, connection):
        """
        Execute action when connection lost.
        :param connection: device connection.
        :return: None
        """
        self.logger.info(f"Connection lost: {connection}")
        self._set_state(NOT_CONNECTED)

    def _detect_after_open_prompt(self, set_callback):
        current_thread = threading.current_thread()
        self.logger.info(f"Command to detect prompt will be sent. Callback: {set_callback} Current thread: {current_thread.name}, ID: {current_thread.ident}")
        self._prompt_detected = False
        self._after_open_prompt_detector = Wait4(
            detect_patterns=[rf'^(.+){self._detecting_prompt_cmd}'],
            connection=self.io_connection.moler_connection,
            till_occurs_times=2
        )
        detector = self._after_open_prompt_detector
        detector.add_event_occurred_callback(callback=set_callback,
                                             callback_params={"event": detector})
        detector.start(timeout=self._prompt_detector_timeout)
        self.logger.info("Prompt detector started")
        self.io_connection.moler_connection.sendline("")
        self.io_connection.moler_connection.sendline(self._detecting_prompt_cmd)
        self.io_connection.moler_connection.sendline("")
        self.io_connection.moler_connection.sendline(self._detecting_prompt_cmd)

    def _set_after_open_prompt(self, event):
        current_thread = threading.current_thread()
        occurrence = event.get_last_occurrence()
        prompt = occurrence['groups'][0].rstrip()
        state = self._get_current_state()
        self.logger.debug(f"ProxyPc2 for state '{state}' new prompt '{prompt}' reverse_state_prompts_dict: '{self._reverse_state_prompts_dict}' Current thread: {current_thread.name}, ID: {current_thread.ident}.")
        with self._state_prompts_lock:
            old_prompt = self._state_prompts.get(state, None)
            prompt = re.escape(prompt)
            self._state_prompts[state] = prompt
            if old_prompt is not None and prompt != old_prompt:
                self.logger.info(f"Different prompt candidates: '{old_prompt}' -> '{prompt}' for state {state}.")
            self.logger.debug(f"New prompts: {self._state_prompts}")
            self._prepare_reverse_state_prompts_dict()
            self.logger.debug(f"After prepare_reverse_state_prompts_dict: {self._reverse_state_prompts_dict}")
            if self._prompts_event is not None:
                self.logger.debug("prompts event is not none")
                self._prompts_event.change_prompts(prompts=self._reverse_state_prompts_dict)
            self._prompt_detected = True

    def _prepare_state_prompts(self):
        """
        Prepare textual prompt for each state.
        :return: None
        """
        if self._use_local_unix_state:
            super(ProxyPc2, self)._prepare_state_prompts()

        if self._use_proxy_pc:
            state_prompts = self._prepare_state_prompts_with_proxy_pc()
        else:
            state_prompts = self._prepare_state_prompts_without_proxy_pc()

        self._update_dict(self._state_prompts, state_prompts)

    def _prepare_state_prompts_with_proxy_pc(self):
        """
        Prepare textual prompt for each state for State Machine with proxy_pc state.
        :return: textual prompt for each state with proxy_pc state.
        """
        state_prompts = {}
        if self._use_local_unix_state:
            state_prompts = {
                PROXY_PC:
                    self._configurations[CONNECTION_HOPS][UNIX_LOCAL][PROXY_PC]["command_params"]["expected_prompt"],
                UNIX_LOCAL:
                    self._configurations[CONNECTION_HOPS][PROXY_PC][UNIX_LOCAL]["command_params"]["expected_prompt"],
            }
        # else detects prompt after establishing connection: _detect_after_open_prompt() & _set_after_open_prompt()
        return state_prompts

    def _prepare_state_prompts_without_proxy_pc(self):
        """
        Prepare textual prompt for each state for State Machine without proxy_pc state.
        :return: textual prompt for each state without proxy_pc state.
        """
        state_prompts = {}
        return state_prompts

    def _prepare_newline_chars(self):
        """
        Prepare newline char for each state.
        :return: None
        """
        if self._use_local_unix_state:
            super(ProxyPc2, self)._prepare_newline_chars()

        if self._use_proxy_pc:
            newline_chars = self._prepare_newline_chars_with_proxy_pc()
        else:
            newline_chars = self._prepare_newline_chars_without_proxy_pc()

        self._update_dict(self._newline_chars, newline_chars)

    def _prepare_newline_chars_with_proxy_pc(self):
        """
        Prepare newline char for each state for State Machine with proxy_pc state.
        :return: newline char for each state with proxy_pc state.
        """
        newline_chars = {}
        if self._use_local_unix_state:
            newline_chars = {
                PROXY_PC:
                    self._configurations[CONNECTION_HOPS][UNIX_LOCAL][PROXY_PC]["command_params"]["target_newline"],
                UNIX_LOCAL:
                    self._configurations[CONNECTION_HOPS][PROXY_PC][UNIX_LOCAL]["command_params"]["target_newline"],
            }
        return newline_chars

    def _prepare_newline_chars_without_proxy_pc(self):
        """
        Prepare newline char for each state for State Machine without proxy_pc state.
        :return: newline char for each state without proxy_pc state.
        """
        newline_chars = {}
        return newline_chars

    def _prepare_state_hops(self):
        """
        Prepare hops for non direct transitions between states.
        :return: None
        """
        if self._use_local_unix_state:
            super(ProxyPc2, self)._prepare_state_hops()

        if self._use_proxy_pc:
            state_hops = self._prepare_state_hops_with_proxy_pc()
        else:
            state_hops = self._prepare_state_hops_without_proxy_pc()

        self._update_dict(self._state_hops, state_hops)

    def _prepare_state_hops_with_proxy_pc(self):
        """
        Prepare non direct transitions for each state for State Machine with proxy_pc state.
        :return: non direct transitions for each state with proxy_pc state.
        """
        state_hops = {}
        if self._use_local_unix_state:
            state_hops = {
                NOT_CONNECTED: {
                    PROXY_PC: UNIX_LOCAL,
                },
                UNIX_LOCAL_ROOT: {
                    PROXY_PC: UNIX_LOCAL,
                },
                PROXY_PC: {
                    NOT_CONNECTED: UNIX_LOCAL,
                    UNIX_LOCAL_ROOT: UNIX_LOCAL,
                },
            }
        return state_hops

    def _prepare_state_hops_without_proxy_pc(self):
        """
        Prepare non direct transitions for each state for State Machine without proxy_pc state.
        :return: non direct transitions for each state without proxy_pc state.
        """
        state_hops = {}
        return state_hops

    def _get_packages_for_state(self, state, observer):
        """
        Get available packages contain cmds and events for each state.
        :param state: device state.
        :param observer: observer type, available: cmd, events
        :return: available cmds or events for specific device state.
        """
        available = []
        if self._use_local_unix_state:
            available = super(ProxyPc2, self)._get_packages_for_state(state, observer)

        if not available:
            if state == PROXY_PC:
                available = {TextualDevice.cmds: ['moler.cmd.unix'],
                             TextualDevice.events: ['moler.events.shared', 'moler.events.unix']}
            if available:
                return available[observer]

        return available

    def get_cmd(self, cmd_name, cmd_params=None, check_state=True, for_state=None):
        """
        Returns instance of command connected with the device.

        :param cmd_name: name of commands, name of class (without package), for example "cd".
        :param cmd_params: dict with command parameters.
        :param check_state: if True then before execute of command the state of device will be check if the same
         as when command was created. If False the device state is not checked.
        :param for_state: if None then command object for current state is returned, otherwise object for for_state is
         returned.
        :return: Instance of command
        """
        if not self._prompt_detected:
            self._detect_prompt_get_cmd()
        return super(ProxyPc2, self).get_cmd(cmd_name=cmd_name, cmd_params=cmd_params,
                                             check_state=check_state,
                                             for_state=for_state)

    def _detect_prompt_get_cmd(self):
        self.logger.debug("get_cmd was called but prompt has not been detected yet.")
        if self._after_open_prompt_detector is None or self._after_open_prompt_detector.running() is not True:
            self.logger.debug("_detect_prompt_get_cmd after_open_prompt_detector is not running! Let's run it.")
            self._detect_after_open_prompt(self._set_after_open_prompt)
        try:
            self._after_open_prompt_detector.await_done(timeout=self._prompt_detector_timeout)
        except MolerException:
            self.logger.info(f"Timeout for prompt detector {self._after_open_prompt_detector}.")

        self._after_open_prompt_detector.cancel()
        self._after_open_prompt_detector = None
        self.logger.debug("SET self._after_open_prompt_detector = None")
        if not self._prompt_detected:
            msg = f"Device {self.public_name} cannot detect prompt!"
            self.logger.warning(msg)
            raise MolerException(msg)
        self.io_connection.moler_connection.sendline("")
        if self._sleep_after_state_change is not None and self._sleep_after_state_change > 0:
            self.logger.info(f"Sleep after prompt detection for {self._sleep_after_state_change:.2f} seconds.")
            time.sleep(self._sleep_after_state_change)
