# -*- coding: utf-8 -*-
"""
Generic Unix/Linux module
"""

__author__ = 'Marcin Usielski', 'Jakub Kochaniak'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com', 'jakub.kochaniak@nokia.com'

import re
import abc
from typing import Optional, Union, Pattern, Sequence
from moler.abstract_moler_connection import AbstractMolerConnection
from moler.runner import ConnectionObserverRunner
from moler.cmd.commandtextualgeneric import CommandTextualGeneric
from moler.exceptions import ParsingDone, WrongUsage
from moler.helpers import remove_all_known_special_chars

cmd_failure_causes = ['not found',
                      'No such file or directory',
                      'running it may require superuser privileges',
                      'Cannot find device',
                      'Input/output error',
                      ]
r_cmd_failure_cause_alternatives = "|".join(cmd_failure_causes)


class GenericUnixCommand(CommandTextualGeneric, metaclass=abc.ABCMeta):
    """GenericUnixCommand is a base class for Unix/Linux commands."""
    # _re_fail = re.compile(r_cmd_failure_cause_alternatives, re.IGNORECASE)

    _whole_timeout_action = 'c'

    def __init__(self, connection: Optional[AbstractMolerConnection], prompt: Optional[Union[str, Pattern]] = None,
                 newline_chars: Optional[Sequence[str]] = None, runner: Optional[ConnectionObserverRunner] = None):
        """
        :param connection: Moler connection to device, terminal when command is executed.
        :param prompt: prompt (on system where command runs).
        :param newline_chars: Characters to split lines - list.
        :param runner: Runner to run command.
        """
        super(GenericUnixCommand, self).__init__(connection=connection, prompt=prompt, newline_chars=newline_chars,
                                                 runner=runner)
        self.remove_all_known_special_chars_from_terminal_output = True
        self.re_fail = re.compile(r_cmd_failure_cause_alternatives, re.IGNORECASE)

        self._ctrl_z_sent = False
        self._kill_ctrl_z_sent = False
        self._kill_ctrl_z_job_done = False
        self._instance_timeout_action = None

    def _decode_line(self, line: str) -> str:
        """
        Method to delete new line chars and other chars we don not need to parse in on_new_line (color escape character)

        :param line: Line with special chars, raw string from device
        :return: line without special chars.
        """
        if self.remove_all_known_special_chars_from_terminal_output:
            line = remove_all_known_special_chars(line)
        return line

    def on_new_line(self, line: str, is_full_line: bool) -> None:
        if self._ctrl_z_sent and is_full_line:
            try:
                self._parse_control_z(line=line)
            except ParsingDone:
                pass
        return super(GenericUnixCommand, self).on_new_line(line, is_full_line)

    def on_timeout(self) -> None:
        """
        Callback called by framework when timeout occurs.

        :return: None
        """
        if self.get_timeout_action() == 'z':
            self.connection.send("\x1A")  # ctrl+z
            self._ctrl_z_sent = True
            self._log_timeout()
        else:
            super(GenericUnixCommand, self).on_timeout()

    def set_timeout_action(self, action: str, all_instances: bool = False) -> str:
        """
        Set the timeout action for the command.

        Parameters:
        :param action (str): The timeout action to be set. Valid values are 'z' and 'c'.
        :param all_instances (bool): If True, sets the timeout action for all instances of the command.

        :return: str: The current timeout action.

        """
        allowed_actions = ('c', 'z')
        if action is None and all_instances is False:
            self._instance_timeout_action = None
        elif action in allowed_actions:
            if all_instances:
                GenericUnixCommand._whole_timeout_action = action
            else:
                self._instance_timeout_action = action
        else:
            raise WrongUsage(f"Passed action: '{action}' and value for all_instances: '{all_instances}'."
                             f" Allowed action: {allowed_actions} or None with all_instances=False.")
        return self.get_timeout_action()

    def get_timeout_action(self) -> str:
        """
        Return the timeout action for the command.

        If the instance-specific timeout action is not set, it returns the default
        timeout action defined in the GenericUnixCommand class.

        returns: timeout action for the command.
        """
        if self._instance_timeout_action is None:
            return GenericUnixCommand._whole_timeout_action
        return self._instance_timeout_action

    def is_end_of_cmd_output(self, line: str) -> bool:
        """
        Checks if end of command is reached.

        :param line: Line from device.
        :return: True if end of command is reached, False otherwise.
        """
        if not self._kill_ctrl_z_job_done and self._ctrl_z_sent:
            return False
        return super(GenericUnixCommand, self).is_end_of_cmd_output(line=line)

    # [2]+  Stopped
    _re_ctrl_z_stopped = re.compile(r"\[(?P<JOB_ID>\d+)\]\+\s+Stopped")

    # -bash: wait: %2: no such job
    _re_kill_no_job = re.compile(r"\:\s+\%\d+\s?\:\s+no such job")

    def _parse_control_z(self, line: str) -> None:
        """
        Parse line that is control+z.

        :param line: Line from device.
        :return: None
        """
        if self._ctrl_z_sent and not self._kill_ctrl_z_job_done and self._regex_helper.search_compiled(
            GenericUnixCommand._re_ctrl_z_stopped, line
        ):
            job_id = self._regex_helper.group("JOB_ID")
            self.connection.sendline(f"kill %{job_id}; wait %{job_id}")
            self._kill_ctrl_z_sent = True
            raise ParsingDone()

        if self._kill_ctrl_z_sent and self._regex_helper.search_compiled(GenericUnixCommand._re_kill_no_job, line):
            self._kill_ctrl_z_job_done = True
            raise ParsingDone()
