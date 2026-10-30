# -*- coding: utf-8 -*-
__author__ = "Michal Ernst, Marcin Usielski, Tomasz Krol"
__copyright__ = "Copyright (C) 2018-2026, Nokia"
__email__ = "michal.ernst@nokia.com, marcin.usielski@nokia.com, tomasz.krol@nokia.com"

import codecs
import contextlib
import re
import select
import datetime
import logging
import threading
import time
import warnings

from ptyprocess import PtyProcessUnicode  # Unix-only

from moler.io.io_connection import IOConnection
from moler.io.raw import TillDoneThread
from moler.helpers import remove_all_known_special_chars
from moler.helpers import all_chars_to_hex
from moler.helpers import non_printable_chars_to_hex
from moler.util import tracked_thread
from moler.connection import Connection
from typing import Tuple, List


class ThreadedTerminal(IOConnection):
    """
    Works on Unix (like Linux) systems only!

    ThreadedTerminal is shell working under Pty

    .. deprecated::
        Use :class:`moler.io.raw.terminal_no_fork.ThreadedTerminalNoFork` instead.
    """

    def __init__(
        self,
        moler_connection: Connection,
        cmd: str = "/bin/bash",
        select_timeout: float = 0.002,
        read_buffer_size: int = 4096,
        first_prompt: str = r"[%$#\]]+",
        target_prompt: str = r"moler_bash#",
        set_prompt_cmd: str = 'unset PROMPT_COMMAND; export PS1="moler_bash# "\n',
        dimensions: Tuple[int, int] = (100, 300),
        terminal_delayafterclose: float = 0.2,
    ):
        """# TODO: # 'export PS1="moler_bash\\$ "\n'  would give moler_bash# for root and moler_bash$ for user
        :param moler_connection: Moler's connection to join with
        :param cmd: command to run terminal
        :param select_timeout: timeout for reading data from terminal
        :param read_buffer_size: buffer for reading data from terminal
        :param first_prompt: default terminal prompt on host where Moler is starting
        :param target_prompt: new prompt which will be set on terminal
        :param set_prompt_cmd: command to change prompt with new line char on the end of string
        :param dimensions: dimensions of the psuedoterminal
        :param terminal_delayafterclose: delay for checking if terminal was properly closed
        """
        deprecation_msg = (
            "ThreadedTerminal is deprecated and will be removed in a future release."
            " Use ThreadedTerminalNoFork (moler.io.raw.terminal_no_fork) instead."
        )
        warnings.warn(deprecation_msg, DeprecationWarning, stacklevel=2)
        super().__init__(moler_connection=moler_connection)
        self.logger.warning(deprecation_msg)
        self.debug_hex_on_non_printable_chars = (
            False  # Set True to log incoming non printable chars as hex.
        )
        self.debug_hex_on_all_chars = False  # Set True to log incoming data as hex.
        self._terminal = None
        self._shell_operable: threading.Event = threading.Event()
        self._export_sent = False
        self.pulling_thread = None
        self.read_buffer: str = ""

        self._select_timeout = select_timeout
        self._read_buffer_size = read_buffer_size
        self.dimensions = dimensions
        self.first_prompt = first_prompt
        self.target_prompt = target_prompt
        self._cmd = [cmd]
        self.set_prompt_cmd = set_prompt_cmd
        self._re_set_prompt_cmd = re.sub(
            "['\"].*['\"]", "", self.set_prompt_cmd.strip()
        )
        self._terminal_delayafterclose = terminal_delayafterclose

    def open(self) -> contextlib.closing:
        """Open ThreadedTerminal connection & start thread pulling data from it."""
        ret = super().open()

        if not self._terminal:
            self.moler_connection.open()
            self._terminal = PtyProcessUnicode.spawn(
                self._cmd, dimensions=self.dimensions
            )
            assert self._terminal is not None
            self._terminal.delayafterclose = self._terminal_delayafterclose
            # need to not replace not unicode data instead of raise exception
            self._terminal.decoder = codecs.getincrementaldecoder("utf-8")(
                errors="replace"
            )

            done = threading.Event()
            self.pulling_thread = TillDoneThread(
                target=self.pull_data, done_event=done, kwargs={"pulling_done": done}
            )
            self.pulling_thread.start()
            retry = 0
            is_operable = False

            timeout = 4 * 60
            start_time = time.monotonic()

            while (time.monotonic() - start_time <= timeout) and (not is_operable):
                is_operable = self._shell_operable.wait(timeout=1)
                if not is_operable:
                    buff = self.read_buffer.encode("UTF-8", "replace")
                    self.logger.warning(
                        f"Terminal open but not fully operable yet. Try {retry} after {time.monotonic() - start_time:.2f} s\nREAD_BUFFER: '{buff}'"
                    )
                    self._terminal.write("\n")
                    retry += 1

        return ret

    def close(self) -> None:
        """Close ThreadedTerminal connection & stop pulling thread."""
        if self.pulling_thread:
            self.pulling_thread.join()
        self.moler_connection.shutdown()
        super().close()

        if self._terminal and self._terminal.isalive():
            self._notify_on_disconnect()
            try:
                self._terminal.close(force=True)
            except Exception as ex:
                self.logger.warning(f"Exception while closing terminal: {ex}")
        self._terminal = None
        self._shell_operable.clear()
        self._export_sent = False
        self.pulling_thread = None
        self.read_buffer = ""

    def send(self, data: str) -> None:
        """Write data into ThreadedTerminal connection."""
        if self._terminal:
            self._terminal.write(data)

    def _log_debug_incoming_data(self, data: str) -> None:
        """
        Debug incoming data.
        :param data: incoming data to debug
        :return: None
        """
        if self.debug_hex_on_all_chars:
            self.logger.debug(f"incoming data: '{all_chars_to_hex(data)}'.")
        if self.debug_hex_on_non_printable_chars:
            self.logger.debug(f"incoming data: '{non_printable_chars_to_hex(data)}'.")

    @tracked_thread.log_exit_exception
    def pull_data(self, pulling_done: threading.Event) -> None:
        """Pull data from ThreadedTerminal connection."""
        logging.getLogger("moler_threads").debug(f"ENTER {self}")
        heartbeat: bool = tracked_thread.report_alive()
        reads: List[int] = []

        while not pulling_done.is_set():
            assert self._terminal is not None
            if next(heartbeat):
                logging.getLogger("moler_threads").debug(f"ALIVE {self}")
            try:
                reads, _, _ = select.select(
                    [self._terminal.fd], [], [], self._select_timeout
                )
            except ValueError as exc:
                self.logger.warning(f"'{exc.__class__}: {exc}'")
                self._notify_on_disconnect()
                pulling_done.set()

            if self._terminal.fd in reads:
                try:
                    data = self._terminal.read(self._read_buffer_size)
                    self._log_debug_incoming_data(data)

                    if self._shell_operable.is_set():
                        self.data_received(data=data, recv_time=datetime.datetime.now())
                    else:
                        self._verify_shell_is_operable(data)
                except EOFError:
                    self._notify_on_disconnect()
                    pulling_done.set()
        logging.getLogger("moler_threads").debug(f"EXIT  {self}")

    def _verify_shell_is_operable(self, data: str) -> None:
        self.read_buffer = self.read_buffer + data
        lines = self.read_buffer.splitlines()

        for line in lines:
            line = remove_all_known_special_chars(line)
            if not re.search(self._re_set_prompt_cmd, line) and re.search(
                self.target_prompt, line
            ):
                self._notify_on_connect()
                self._shell_operable.set()
                self.data_received(data=self.read_buffer, recv_time=datetime.datetime.now())
            elif not self._export_sent and re.search(
                self.first_prompt, self.read_buffer, re.MULTILINE
            ):
                self.send(self.set_prompt_cmd)
                self._export_sent = True
