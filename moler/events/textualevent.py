# -*- coding: utf-8 -*-

__author__ = 'Marcin Usielski, Michal Ernst'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com, michal.ernst@nokia.com'

import abc
import logging
from moler.event import Event
from moler.cmd import RegexHelper


class TextualEvent(Event, metaclass=abc.ABCMeta):
    _default_newline_chars = ("\n", "\r")  # New line chars on device, not system with script!

    def __init__(self, connection=None, till_occurs_times=-1, runner=None):
        super(TextualEvent, self).__init__(connection=connection, runner=runner, till_occurs_times=till_occurs_times)
        self._last_not_full_line = None
        self._newline_chars = TextualEvent._default_newline_chars
        self._regex_helper = RegexHelper()  # Object to regular expression matching
        self._paused = False
        self._ignore_unicode_errors = True  # If True then UnicodeDecodeError will be logged not raised in data_received
        self._last_recv_time_data_read_from_connection = None  # Time moment when data was really received from
        # connection (not when was passed to event).  Time is given as datetime.datetime instance
        self._reverse_order: bool = False  # Order of processing lines in data_received
        # method. False to process from the last line, True from the newest.
        self._break_processing_when_found: bool = False  # Flag to break processing
        # line when the first line is found.

    def event_occurred(self, event_data):
        self._consume_already_parsed_fragment()
        super(TextualEvent, self).event_occurred(event_data)

    @abc.abstractmethod
    def on_new_line(self, line, is_full_line):
        """
        Method to parse output from device.
        Write your own implementation to do something useful
        :param line: Line to parse, new lines are trimmed
        :param is_full_line: True if new line character was removed from line, False otherwise
        :return: None
        """

    def data_received(self, data, recv_time):
        """
        Called by framework when any data are sent by device.

        :param data: List of strings sent by device.
        :param recv_time: time stamp with the moment when the data was read from connection.
        :return: None
        """
        if not self._paused:
            self._last_recv_time_data_read_from_connection = recv_time
            try:
                lines = data.splitlines(True)
                processed = []
                for current_chunk in lines:
                    line, is_full_line = self._update_from_cached_incomplete_line(current_chunk=current_chunk)
                    processed.append((current_chunk, line, is_full_line))
                if self._reverse_order:
                    processed.reverse()
                for data in processed:
                    current_chunk, line, is_full_line = data
                    self._last_chunk_matched = False
                    if not self.done():
                        self._process_line_from_output(line=line, current_chunk=current_chunk,
                                                       is_full_line=is_full_line)
                        if self._paused:
                            self._last_not_full_line = None
                            break
                        if self._last_chunk_matched and self._break_processing_when_found:
                            break
            except UnicodeDecodeError as ex:
                if self._ignore_unicode_errors:
                    self._log(lvl=logging.WARNING,
                              msg=f"Processing data from '{self}' with unicode problem: '{ex}'.")
                else:
                    raise ex

    # pylint: disable-next=unused-argument
    def _process_line_from_output(self, current_chunk, line, is_full_line):
        """
        Processes line from connection (device) output.

        :param current_chunk: Chunk of line sent by connection.
        :param line: Line of output (current_chunk plus previous chunks of this line - if any) without newline char(s).
        :param is_full_line: True if line had newline char(s). False otherwise.
        :return: None
        """
        decoded_line = self._decode_line(line=line)
        self.on_new_line(line=decoded_line, is_full_line=is_full_line)

    def _update_from_cached_incomplete_line(self, current_chunk):
        """
        Concatenates (if necessary) previous chunk(s) of line and current.

        :param current_chunk: line from connection (full line or incomplete one).
        :return: Concatenated (if necessary) line from connection without newline char(s). Flag: True if line had
         newline char(s), False otherwise.
        """
        line = current_chunk
        if self._last_not_full_line is not None:
            line = f"{self._last_not_full_line}{line}"
            self._last_not_full_line = None
        is_full_line = self.is_new_line(line)
        if is_full_line:
            line = self._strip_new_lines_chars(line)
        else:
            self._last_not_full_line = line
        return line, is_full_line

    def is_new_line(self, line):
        """
        Method to check if line has chars of new line at the right side
        :param line: String to check
        :return: True if any new line char was found, False otherwise
        """
        if line.endswith(self._newline_chars):
            return True
        return False

    def _strip_new_lines_chars(self, line):
        """
        :param line: line from device
        :return: line without new lines chars
        """
        for char in self._newline_chars:
            line = line.rstrip(char)
        return line

    def _consume_already_parsed_fragment(self):
        """
        Clear already parsed fragment of line to not parse it twice when another fragment appears on device.
        :return: None
        """
        self._last_not_full_line = None

    def _decode_line(self, line):
        """
        Decodes line if necessary. Put here code to remove colors from terminal etc.

        :param line: line from device to decode.
        :return: decoded line.
        """
        return line

    def pause(self):
        """
        Pauses the event. Do not process till resume.

        :return: None
        """
        self._paused = True
        self._last_not_full_line = None

    def resume(self):
        """
        Resumes processing output from connection by the event.

        :return: None
        """
        self._paused = False
