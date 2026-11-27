"""
Generic for adb commands.
"""

__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2022-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'

import abc

from moler.cmd.commandtextualgeneric import CommandTextualGeneric


class GenericAdbCommand(CommandTextualGeneric, metaclass=abc.ABCMeta):
    pass
