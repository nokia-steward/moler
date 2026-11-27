# -*- coding: utf-8 -*-
"""
Tee command module.
"""

__author__ = 'Marcin Usielski, Michal Ernst'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com, michal.ernst@nokia.com'

from moler.cmd.unix.genericunix import GenericUnixCommand
from moler.helpers import copy_list


class Tee(GenericUnixCommand):
    """Unix tee command"""

    def __init__(self, connection, path, content, border="END_OF_FILE", prompt=None, newline_chars=None, runner=None):
        """
        Unix tee command

        :param connection: Moler connection to device, terminal when command is executed.
        :param path: path to file to save.
        :param content: content of file. A string or list of strings.
        :param border: border string, to finish command output
        :param prompt: Prompt of the starting shell
        :param newline_chars: Characters to split lines - list.
        :param runner: Runner to run command.
        """
        super(Tee, self).__init__(connection=connection, prompt=prompt, newline_chars=newline_chars, runner=runner)
        self.ret_required = False
        self.path = path
        if isinstance(content, str):
            self._content = [content]
        else:
            self._content = copy_list(src=content)  # copy of list of content to modify
        self.border = border
        self.end_sent = False
        self._first_line_sent = False

    def build_command_string(self):
        """
        Builds command string from parameters passed to object.

        :return: String representation of command to send over connection to device.
        """
        cmd = f"tee {self.path} << {self.border}"
        return cmd

    def on_new_line(self, line, is_full_line):
        """
        Parses the output of the command.

        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param is_full_line: True if line had new line chars, False otherwise
        :return: None
        """
        self._send_content_first_line()
        if is_full_line:
            self._send_one_line()
        super(Tee, self).on_new_line(line=line, is_full_line=is_full_line)

    def _send_content_first_line(self):
        if not self._first_line_sent:
            self._send_one_line()
            self._first_line_sent = True

    def _send_one_line(self):
        try:
            line_to_save = self._content.pop(0)
            self.connection.sendline(line_to_save)
        except IndexError:
            if not self.end_sent:
                self.connection.sendline(self.border)
                self.end_sent = True


COMMAND_OUTPUT_string = """tee file.txt << END_OF_FILE
line 1
line 2
END_OF_FILE
moler-bash#"""

COMMAND_KWARGS_string = {
    "path": "file.txt",
    "content": "line 1\nline 2"
}

COMMAND_RESULT_string = {}

COMMAND_OUTPUT_list = """tee file.txt << END_OF_FILE
line a
line b
END_OF_FILE
moler-bash#"""

COMMAND_KWARGS_list = {
    "path": "file.txt",
    "content": ("line a", "line b")
}

COMMAND_RESULT_list = {}
