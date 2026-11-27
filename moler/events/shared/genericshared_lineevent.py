# -*- coding: utf-8 -*-
"""
Generic Shared module
"""

__author__ = 'Michal Ernst'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'michal.ernst@nokia.com'

import abc
import datetime
from moler.events.lineevent import LineEvent
from moler.helpers import remove_all_known_special_chars


class GenericSharedLineEvent(LineEvent, metaclass=abc.ABCMeta):

    def _decode_line(self, line):
        """
        Decodes line if necessary. Put here code to remove colors from terminal etc.

        :param line: line from device to decode.
        :return: decoded line.
        """
        line = remove_all_known_special_chars(line)
        return line


EVENT_OUTPUT_single_pattern = """user@host01:~> TERM=xterm-mono telnet -4 host.domain.net 1500
Login:
Login:user
Password:
Last login: Thu Nov 23 10:38:16 2017 from 127.0.0.1
Have a lot of fun...
CLIENT5 [] has just connected!
host:~ #"""

EVENT_KWARGS_single_pattern = {
    "detect_patterns": [r'host:.*#'],
    "till_occurs_times": 1
}

EVENT_RESULT_single_pattern = [
    {
        'time': datetime.datetime(2019, 1, 14, 13, 12, 48, 224929),
        "groups": (),
        "named_groups": {},
        "matched": "host:~ #",
        'line': "host:~ #"
    }
]
