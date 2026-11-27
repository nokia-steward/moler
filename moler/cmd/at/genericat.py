# -*- coding: utf-8 -*-
"""
Common part for all commands.

AT commands specification:
google for: 3gpp specification 27.007
(always check against latest version of standard)
"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2020-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import re
import abc
from moler.cmd.commandtextualgeneric import CommandTextualGeneric
from moler.exceptions import CommandFailure
from moler.exceptions import ParsingDone


class GenericAtCommand(CommandTextualGeneric, metaclass=abc.ABCMeta):
    _re_default_at_prompt = re.compile(r'^\s*(OK|NO CARRIER|ERROR|\+CM[ES]\s+ERROR:\s*\S.+)\s*$')  # When user provides no prompt

    def __init__(self, connection, operation="execute", prompt=None, newline_chars=None, runner=None):
        """
        Create instance of At class - base class for all AT commands

        :param connection: connection used to send command and receive its output
        :param operation: "execute", "read", "test" (not all AT commands support all modes)
        :param prompt: prompt (on system where command runs).
        :param newline_chars: Characters to split lines - list.
        :param runner: Runner to run command.
        """
        if prompt is None:
            prompt = self._re_default_at_prompt
        self.operation = operation  # for 'read' command ends with '?', for 'test' ends with '=?'
        super(GenericAtCommand, self).__init__(connection=connection, prompt=prompt, newline_chars=newline_chars,
                                               runner=runner)
        if operation not in ["execute", "read", "test"]:
            raise CommandFailure(self, f"{operation} mode not supported")
        # TODO: do we have any way to stop AT cmd?
        self.terminating_timeout = 0  # no additional timeout for Ctrl-C..till..prompt (shutdown after cmd timeout)

    def on_new_line(self, line, is_full_line):
        """
        Method to parse command output. Will be called after line with command echo.
        Write your own implementation but don't forget to call on_new_line from base class

        :param line: Line to parse, new lines are trimmed
        :param is_full_line:  False for chunk of line; True on full line (NOTE: new line character removed)
        :return: None
        """
        if is_full_line:
            try:
                self._parse_error_response(line)
            except ParsingDone:
                pass
        return super(GenericAtCommand, self).on_new_line(line, is_full_line)

    def _is_at_cmd_echo(self, line):
        return self._regex_helper.search_compiled(self._cmd_escaped, line)

    _re_error = re.compile(r'^\s*(ERROR|NO CARRIER)\s*$')
    _re_cme_error = re.compile(r'^\+(?P<ERR_TYPE>CM[ES])\s+ERROR:\s*(?P<ERROR>\S.+)', flags=re.IGNORECASE)

    def _parse_error_response(self, line):
        """
        When command itself is invalid or cannot be performed for some reason,
        or mobile termination error reporting is disabled:
        at+cmd
        ERROR

        When command was not processed due to an error related to MT operation:
        at+cmd
        +CME ERROR: result code

        See https://www.smssolutions.net/tutorials/gsm/gsmerrorcodes/
        """
        if self._regex_helper.match_compiled(self._re_cme_error, line):
            error_type = self._regex_helper.group("ERR_TYPE")
            error_info = self._regex_helper.group("ERROR")
            self.set_exception(CommandFailure(self, f"{error_type} ERROR: {error_info}"))
            raise ParsingDone
        elif self._regex_helper.match_compiled(self._re_error, line):
            error_info = self._regex_helper.group(1)
            self.set_exception(CommandFailure(self, error_info))
            raise ParsingDone
