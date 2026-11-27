# -*- coding: utf-8 -*-

__author__ = "Marcin Usielski, Tomasz Krol"
__copyright__ = "Copyright (C) 2018-2026, Nokia"
__email__ = "marcin.usielski@nokia.com, tomasz.krol@nokia.com"

import abc
import datetime
import re

from moler.events.textualevent import TextualEvent
from moler.exceptions import NoDetectPatternProvided, WrongUsage
from moler.helpers import convert_to_number, copy_list, instance_id


class LineEvent(TextualEvent, metaclass=abc.ABCMeta):
    def __init__(
        self,
        detect_patterns,
        connection=None,
        till_occurs_times=-1,
        match="any",
        runner=None,
    ):
        super(LineEvent, self).__init__(
            connection=connection, runner=runner, till_occurs_times=till_occurs_times
        )
        self.detect_patterns = copy_list(detect_patterns)
        self.process_full_lines_only = False
        self.match = match
        self.convert_string_to_number = True
        self.copy_compiled_patterns = []
        self._current_ret = []
        self._prepare_parameters()

    def __str__(self):
        return f"{self.__class__.__name__}({self.detect_patterns}, id:{instance_id(self)})"

    # pylint: disable=keyword-arg-before-vararg
    def start(self, timeout=None, *args, **kwargs):
        """Start background execution of command."""

        self._validate_start(*args, **kwargs)
        ret = super(LineEvent, self).start(timeout, *args, **kwargs)
        self.life_status._is_running = True  # pylint: disable=protected-access

        return ret

    def _validate_start(self, *args, **kwargs):
        # check base class invariants first
        super(LineEvent, self)._validate_start(*args, **kwargs)
        # then what is needed for command
        if not self.detect_patterns:
            # no chance to start CMD
            raise NoDetectPatternProvided(self)

    def on_new_line(self, line, is_full_line):
        if is_full_line or not self.process_full_lines_only:
            self._parse_line(line=line)

    def compile_patterns(self, patterns):
        compiled_patterns = []
        for pattern in patterns:
            if not hasattr(pattern, "match"):  # Not compiled regexp
                pattern = re.compile(pattern)
            compiled_patterns.append(pattern)
        return compiled_patterns

    def _convert_string_to_number(self, value):
        if self.convert_string_to_number:
            value = convert_to_number(value)
        return value

    def get_long_desc(self):
        return f"Event {self.__class__.__module__}.{str(self)}"

    def get_short_desc(self):
        return f"Event {self.__class__.__module__}.{str(self)}"

    def _get_parser(self):
        parsers = {
            "any": self._catch_any,
            "all": self._catch_all,
            "sequence": self._catch_sequence,
        }
        if self.match in parsers:
            return parsers[self.match]
        else:
            self.set_exception(
                WrongUsage(
                    f"'{self.match}' is not supported. Possible choices: 'any', 'all' or 'sequence'"
                )
            )

    def _prepare_parameters(self):
        self.parser = self._get_parser()
        self.compiled_patterns = self.compile_patterns(self.detect_patterns)

        if self.match in ["all", "sequence"]:
            self._prepare_new_cycle_parameters()

    def _parse_line(self, line):
        self.parser(line=line)

    def _set_current_ret(self, line, match):
        current_ret = self._prepare_current_ret(line, match)

        if self._is_single_cycle_finished():
            if self.match == "any":
                self.event_occurred(event_data=current_ret)
            else:
                self._current_ret.append(current_ret)
                self.event_occurred(event_data=self._current_ret)
        else:
            self._current_ret.append(current_ret)

    def _prepare_current_ret(self, line, match):
        current_ret = {}
        current_ret["line"] = line
        current_ret["time"] = self._last_recv_time_data_read_from_connection

        group_dict = match.groupdict()
        for named_group in match.groupdict():
            group_dict[named_group] = self._convert_string_to_number(
                group_dict[named_group]
            )

        current_ret["named_groups"] = group_dict

        groups = tuple()
        for value in match.groups():
            groups = groups + (self._convert_string_to_number(value),)

        current_ret["groups"] = groups

        current_ret["matched"] = self._convert_string_to_number(match.group(0))

        return current_ret

    def _catch_any(self, line):
        for pattern in self.compiled_patterns:
            match = re.search(pattern, line)
            if match:
                self._set_current_ret(line=line, match=match)
                return

    def _catch_all(self, line):
        for index, pattern in enumerate(self.copy_compiled_patterns):
            match = re.search(pattern, line)
            if match:
                del self.copy_compiled_patterns[index]
                self._set_current_ret(line=line, match=match)
                if self._is_single_cycle_finished():
                    self._prepare_new_cycle_parameters()
                return

    def _catch_sequence(self, line):
        if self.copy_compiled_patterns:
            pattern = self.copy_compiled_patterns[0]
            match = re.search(pattern, line)
            if match:
                del self.copy_compiled_patterns[0]
                self._set_current_ret(line=line, match=match)
                if self._is_single_cycle_finished():
                    self._prepare_new_cycle_parameters()

    def _prepare_new_cycle_parameters(self):
        self.copy_compiled_patterns = copy_list(self.compiled_patterns)
        self._current_ret = []

    def _is_single_cycle_finished(self):
        if hasattr(self, "copy_compiled_patterns") and len(self.copy_compiled_patterns):
            return False
        else:
            return True


EVENT_OUTPUT_single_pattern = """
user@host01:~> TERM=xterm-mono telnet -4 host.domain.net 1500
Login:
Login:user
Password:
Last login: Thu Nov 23 10:38:16 2017 from 127.0.0.1
Have a lot of fun...
CLIENT5 [] has just connected!
host:~ #"""

EVENT_KWARGS_single_pattern = {"detect_patterns": [r"host:.*#"], "till_occurs_times": 1}

EVENT_RESULT_single_pattern = [
    {
        "time": datetime.datetime(2019, 1, 14, 13, 12, 48, 224929),
        "groups": (),
        "named_groups": {},
        "matched": "host:~ #",
        "line": "host:~ #",
    }
]

EVENT_OUTPUT_patterns_list = """
user@host01:~> TERM=xterm-mono telnet -4 host.domain.net 1500
Login:
Login:user
Password:
Last login: Thu Nov 23 10:38:16 2017 from 127.0.0.1
Have a lot of fun...
CLIENT5 [] has just connected!
host:~ #"""

EVENT_KWARGS_patterns_list = {
    "detect_patterns": ["Last login", r"host:.*#"],
    "till_occurs_times": 2,
}

EVENT_RESULT_patterns_list = [
    {
        "time": datetime.datetime(2019, 1, 14, 13, 12, 48, 224929),
        "groups": (),
        "named_groups": {},
        "matched": "Last login",
        "line": "Last login: Thu Nov 23 10:38:16 2017 from 127.0.0.1",
    },
    {
        "time": datetime.datetime(2019, 1, 14, 13, 12, 48, 224929),
        "groups": (),
        "named_groups": {},
        "matched": "host:~ #",
        "line": "host:~ #",
    },
]
