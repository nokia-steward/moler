# -*- coding: utf-8 -*-
"""
Generic Juniper_Ex module
"""

__author__ = 'Michal Ernst'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'michal.ernst@nokia.com'

import abc
import datetime
from moler.events.lineevent import LineEvent


class GenericJuniperExLineEvent(LineEvent, metaclass=abc.ABCMeta):
    pass


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
