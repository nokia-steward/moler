# -*- coding: utf-8 -*-
"""
Run script command
"""

__author__ = "Marcin Usielski"
__copyright__ = "Copyright (C) 2018-2026, Nokia"
__email__ = "marcin.usielski@nokia.com"


import re

from moler.cmd.unix.genericunix import GenericUnixCommand
from moler.exceptions import CommandFailure, ParsingDone
from moler.helpers import copy_list


class RunScript(GenericUnixCommand):
    def __init__(
        self,
        connection,
        script_command,
        error_regex=re.compile("error", re.IGNORECASE),
        prompt=None,
        newline_chars=None,
        runner=None,
        success_regex=None,
    ):
        """
        :param connection: Moler connection to device, terminal when command is executed.
        :param script_command: path to script to run.
        :param error_regex: Regex to detect error in script output. Regex or list of regex.
        :param prompt: prompt (on system where command runs).
        :param newline_chars: Characters to split lines - list.
        :param runner: Runner to run command.
        :param success_regex: Regex must be found in output to success command. Regex or list of regex.
        """
        super(RunScript, self).__init__(
            connection=connection,
            prompt=prompt,
            newline_chars=newline_chars,
            runner=runner,
        )
        self.script_command = script_command
        self.success_regexes = self._copy_list(success_regex)
        self.error_regexes = self._copy_list(error_regex)
        self.ret_required = False

    def build_command_string(self):
        """
        Builds command string from parameters passed to object.
        :return: String representation of command to send over connection to device.
        """
        return self.script_command

    def on_new_line(self, line, is_full_line):
        """
        Put your parsing code here.
        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param is_full_line: True if line had new line chars, False otherwise
        :return: None
        """
        try:
            self._find_error(line)
            self._find_success(line)
        except ParsingDone:
            pass
        return super(RunScript, self).on_new_line(line, is_full_line)

    def _find_success(self, line):
        for success_regex in self.success_regexes:
            if self._regex_helper.search_compiled(success_regex, line):
                self.success_regexes.remove(success_regex)
                raise ParsingDone()

    def _find_error(self, line):
        for error_regex in self.error_regexes:
            if self._regex_helper.search_compiled(error_regex, line):
                self.set_exception(
                    CommandFailure(
                        self,
                        f"Found error regex '{error_regex}' in line '{line}'",
                    )
                )
                raise ParsingDone()

    def _copy_list(self, src):
        if src is None:
            ret = []
        elif isinstance(src, str):
            ret = [src]
        elif isinstance(src, list) or isinstance(src, tuple):
            ret = copy_list(src, deep_copy=False)
        else:
            ret = [src]

        ret_val = [
            re.compile(val) if isinstance(val, str) else val for val in ret
        ]
        return ret_val

    @property
    def _is_done(self):
        return super(RunScript, self)._is_done

    @_is_done.setter
    def _is_done(self, value):
        if value is True and len(self.success_regexes) > 0:
            self._set_exception_without_done(
                CommandFailure(
                    self,
                    f"Not found all regex for success. Left: '{self.success_regexes}'.",
                )
            )
        super(RunScript, self.__class__)._is_done.fset(self, value)


COMMAND_OUTPUT = """
./myscript.sh
Output from script
moler_bash#"""

COMMAND_KWARGS = {"script_command": "./myscript.sh"}

COMMAND_RESULT = {}

COMMAND_OUTPUT_success = """
./myscript.sh
Output from script
Line 2
moler_bash#"""

COMMAND_KWARGS_success = {"script_command": "./myscript.sh", "success_regex": r"Line 2"}

COMMAND_RESULT_success = {}

COMMAND_OUTPUT_success_list = """
./myscript.sh
Output from script
Line 2
moler_bash#"""

COMMAND_KWARGS_success_list = {
    "script_command": "./myscript.sh",
    "success_regex": ("Output", re.compile("Line 2")),
}

COMMAND_RESULT_success_list = {}
