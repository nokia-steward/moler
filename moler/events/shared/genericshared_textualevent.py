# -*- coding: utf-8 -*-
"""
Generic Shared module
"""

__author__ = 'Michal Ernst'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'michal.ernst@nokia.com'

import abc
from moler.events.textualevent import TextualEvent
from moler.helpers import remove_all_known_special_chars


class GenericSharedTextualEvent(TextualEvent, metaclass=abc.ABCMeta):

    def _decode_line(self, line):
        """
        Decodes line if necessary. Put here code to remove colors from terminal etc.

        :param line: line from device to decode.
        :return: decoded line.
        """
        line = remove_all_known_special_chars(line)
        return line
