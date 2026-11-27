# -*- coding: utf-8 -*-
"""
Generic Juniper module
"""

__author__ = 'Michal Ernst'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'michal.ernst@nokia.com'

import abc

from moler.events.textualevent import TextualEvent


class GenericJuniperEvent(TextualEvent, metaclass=abc.ABCMeta):
    pass
