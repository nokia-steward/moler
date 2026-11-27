# -*- coding: utf-8 -*-
"""
Generic command class for commands change prompt
"""

__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'

import abc
import re

from moler.cmd.commandtextualgeneric import CommandTextualGeneric
from moler.exceptions import ParsingDone
from moler.helpers import regexp_without_anchors


class CommandChangingPrompt(CommandTextualGeneric, metaclass=abc.ABCMeta):
    """Base class for textual commands to change prompt."""

    def __init__(self, connection, prompt, expected_prompt, newline_chars=None, runner=None,
                 set_timeout=None, set_prompt=None, target_newline="\n", allowed_newline_after_prompt=False,
                 prompt_after_login=None):
        """
        Moler base class for commands that change prompt.

        :param connection: moler connection to device, terminal when command is executed.
        :param prompt: prompt on start system (where command starts).
        :param expected_prompt: prompt on server (where command connects).
        :param newline_chars: characters to split lines.
        :param runner: Runner to run command.
        :param set_timeout: Command to set timeout after telnet connects.
        :param set_prompt: Command to set prompt after telnet connects.
        :param target_newline: newline chars on remote system where ssh connects.
        :param allowed_newline_after_prompt: If True then newline chars may occur after expected (target) prompt.
        :param prompt_after_login: prompt after login before send export PS1. If you do not change prompt exporting PS1
         then leave it None.
        """
        super(CommandChangingPrompt, self).__init__(connection=connection, prompt=prompt, newline_chars=newline_chars,
                                                    runner=runner)

        # Parameters defined by calling the command
        self._re_expected_prompt = CommandTextualGeneric._calculate_prompt(expected_prompt)  # Expected prompt on device
        self._re_prompt_after_login = self._re_expected_prompt
        if prompt_after_login:
            self._re_prompt_after_login = CommandTextualGeneric._calculate_prompt(prompt_after_login)
        self.set_timeout = set_timeout
        self.set_prompt = set_prompt
        self.target_newline = target_newline
        self.allowed_newline_after_prompt = allowed_newline_after_prompt
        self.enter_on_prompt_without_anchors = True  # Set True to try to match prompt in line without ^ and $.
        self.check_echo_settings = True  # Set True to check if echo of commands to set prompt and timeout is matched.

        # Internal variables
        self._re_failure_exceptions_indication = None
        self._sent = False
        self._finish_on_final_prompt = True  # Set True to finish Moler command by this generic after prompt after
        # command output. False if you want to finish command in your class.

        self._re_expected_prompt_without_anchors = regexp_without_anchors(self._re_expected_prompt)
        self._re_prompt_after_login_without_anchors = regexp_without_anchors(self._re_prompt_after_login)
        self._re_timeout_echo = None
        self._re_prompt_echo = None
        if self.set_timeout:
            self._re_timeout_echo = re.compile(self._build_command_string_slice(self.set_timeout))
        if self.set_prompt:
            self._re_prompt_echo = re.compile(self._build_command_string_slice(self.set_prompt))
        self._commands_to_send_when_prompt = []
        self._commands_to_send_when_after_login_prompt = []
        if self.set_timeout:
            self._commands_to_send_when_after_login_prompt.append(self.set_timeout)
        if self.set_prompt:
            self._commands_to_send_when_after_login_prompt.append(self.set_prompt)
        self._commands_to_send_when_expected_prompt = []
        self._sent = False

    def __str__(self):
        """
        Return a string representation of the CommandChangingPrompt object.

        The string representation includes the base string representation
        obtained from the superclass, as well as the regular expressions
        for the expected prompt and the prompt after login.

        :return: A string representation of the CommandChangingPrompt object.
        """
        base_str = super(CommandChangingPrompt, self).__str__()
        expected_prompt = self._re_expected_prompt.pattern
        prompt_after_login = self._re_prompt_after_login.pattern
        # having expected prompt visible simplifies troubleshooting
        return f"{base_str[:-1]}, expected_prompt_regex:r'{expected_prompt}', prompt_after_login:r'{prompt_after_login}')"

    def on_new_line(self, line: str, is_full_line: bool) -> None:
        """
        Parses the output of the command.

        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param is_full_line: True if line had new line chars, False otherwise
        :return: None
        """
        try:
            self._detect_prompts_without_anchors(line, is_full_line)
            self._detect_final_prompt(line, is_full_line)
            self._detect_prompt_after_exception(line)
            self._send_commands_when_prompt(line)
            self._send_commands_when_after_login_prompt(line)
            self._send_commands_when_expected_prompt(line)
        except ParsingDone:
            pass
        if is_full_line:
            self._sent = False

    def _detect_prompts_without_anchors(self, line: str, is_full_line: bool):
        """
        Detects prompts without anchors in the provided line. If a prompt is detected, it sends an empty command to the device.
        This method is used to handle situations where the prompt may appear in the middle of the line, without the start and end anchors (^ and $).

        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param is_full_line: True if line had new line chars, False otherwise
        :return: None
        """
        if is_full_line or not self.enter_on_prompt_without_anchors or self._sent:
            return
        msg = None
        if self._is_prompt_without_anchors(line=line, prompt_without_anchors=self._re_prompt_after_login_without_anchors,
                                           prompt=self._re_prompt_after_login):
            msg = f"Candidate for prompt after login '{self._re_prompt_after_login.pattern}' " \
                  f"(used without anchors:'{self._re_prompt_after_login_without_anchors.pattern}') " \
                  f"in line '{line}'."
        elif self._is_prompt_without_anchors(line=line, prompt_without_anchors=self._re_expected_prompt_without_anchors,
                                             prompt=self._re_expected_prompt):
            msg = f"Candidate for expected prompt '{self._re_expected_prompt.pattern}' " \
                  f"(used without anchors:'{self._re_expected_prompt_without_anchors.pattern}') " \
                  f"in line '{line}'."
        if msg:
            self.logger.info(msg)
            raise ParsingDone()

    def _is_prompt_without_anchors(self, line: str, prompt_without_anchors, prompt) -> bool:
        """
        Checks if the provided line matches the prompt without anchors. If a match is found, it sends an empty command to the device.
        This method is used to handle situations where the prompt may appear in the middle of the line, without the start and end anchors (^ and $).

        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param prompt_without_anchors: Regular expression object representing the prompt without start and end anchors.
        :param prompt: Regular expression object representing the prompt with start and end anchors.
        :return: True if the line matches the prompt without anchors, False otherwise.
        """
        found = self._regex_helper.search_compiled(prompt, line)
        if not found:
            if self._regex_helper.search_compiled(
                    prompt_without_anchors, line):
                self._send("")
                return True
        return False

    def _send_commands_when_prompt(self, line: str) -> None:
        """
        Sends commands when start prompt is detected.

        :param line: Line from device.
        :return: None
        """
        self._parse_prompt_and_send_command(line=line, prompt=self._re_prompt,
                                            commands=self._commands_to_send_when_prompt)

    def _send_commands_when_after_login_prompt(self, line: str) -> None:
        """
        Sends commands when after login prompt is detected.

        :param line: Line from device.
        :return: None
        """
        self._parse_prompt_and_send_command(line=line, prompt=self._re_prompt_after_login,
                                            commands=self._commands_to_send_when_after_login_prompt)

    def _send_commands_when_expected_prompt(self, line: str) -> None:
        """
        Sends commands when final prompt is detected.

        :param line: Line from device.
        :return: None
        """
        self._parse_prompt_and_send_command(line=line, prompt=self._re_expected_prompt,
                                            commands=self._commands_to_send_when_expected_prompt)

    def _parse_prompt_and_send_command(self, line: str, prompt, commands: list) -> None:
        """
        Checks if the provided line matches the given prompt. If a match is found, it sends the first command from the commands list to the device.
        This method is used to handle situations where a specific prompt is detected and a corresponding command needs to be sent.

        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param prompt: Regular expression object representing the prompt to be matched.
        :param commands: List of commands to be sent when the prompt is detected. The first command in the list is sent and then removed from the list.
        :return: None
        """
        if self._sent:
            return
        if len(commands) > 0 and self._regex_helper.search_compiled(prompt, line):
            cmd = commands.pop(0)
            self._send(cmd)
            raise ParsingDone()

    def _detect_final_prompt(self, line: str, is_full_line: bool) -> None:
        """
        Checks if the provided line matches the expected final prompt. If a match is found and the line is a full line or
        newline characters are allowed after the prompt, it sets the result of the command and raises ParsingDone to stop further parsing.

        This method is used to handle situations where the final prompt is detected, indicating the end of the command execution.

        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param is_full_line: True if line had new line chars, False otherwise
        :return: None
        """
        if self._is_target_prompt(line) and (not is_full_line or self.allowed_newline_after_prompt):
            if self._sent is False and self._are_settings_needed() is False:
                if not self.done() and self._cmd_output_started:
                    if self._finish_on_final_prompt:
                        self.set_result(self.current_ret)
                    raise ParsingDone()

    def _are_settings_needed(self) -> bool:
        """
        Checks if there are any commands left to be sent when the expected or after login prompts are detected.

        This method is used to determine if there are any settings commands that still need to be sent to the device.
        If there are commands in either the `_commands_to_send_when_expected_prompt` or `_commands_to_send_when_after_login_prompt` lists,
        it returns True, indicating that settings commands are still needed. Otherwise, it returns False.

        :return: True if there are commands left to be sent when the expected or after login prompts are detected, False otherwise.
        """
        if len(self._commands_to_send_when_expected_prompt) > 0 or len(self._commands_to_send_when_after_login_prompt) > 0:
            return True
        return False

    def _detect_prompt_after_exception(self, line: str):
        """
        Detects start prompt.

        :param line: Line from device.
        :return: None but raises ParsingDone if detects start prompt and any exception
         was set.
        """
        if self._stored_exception and self._regex_helper.search_compiled(self._re_prompt, line):
            self._is_done = True
            raise ParsingDone()

    def _is_target_prompt(self, line: str) -> bool:
        """
        Checks if line contains prompt on target system.

        :param line: Line from device
        :return: True if line contains prompt on target device, False otherwise
        """
        found = self._regex_helper.search_compiled(self._re_expected_prompt, line)
        return found is not None

    def _send(self, command: str, newline: str = None, encrypt: bool = False):
        """
        Sends the provided command to the device. If a newline character is provided, it is appended to the command.
        If the encrypt flag is set to True, the command is encrypted before being sent.

        This method is used to send commands to the device during the execution of the command.

        :param command: The command to be sent to the device.
        :param newline: The newline character to be appended to the command. If None, the command is sent as is.
        :param encrypt: If True, the command is encrypted before being sent. Default is False.
        :return: None
        """
        self._sent = True
        if newline:
            self.connection.send(data=f"{command}{newline}", encrypt=encrypt)
        else:
            self.connection.sendline(data=command, encrypt=encrypt)

    @abc.abstractmethod
    def build_command_string(self) -> str:
        """
        Returns string with command constructed with parameters of object.

        :return:  String with command.
        """
