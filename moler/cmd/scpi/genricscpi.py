# -*- coding: utf-8 -*-
"""
SCPI generic module for commands in all states.
"""

import abc
from moler.cmd.commandtextualgeneric import CommandTextualGeneric

__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'


class GenericScpi(CommandTextualGeneric, metaclass=abc.ABCMeta):
    pass
