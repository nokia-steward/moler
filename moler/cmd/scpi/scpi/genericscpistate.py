# -*- coding: utf-8 -*-
"""
SCPI generic module for commands in state SCPI.
"""

import abc
from moler.cmd.scpi.genricscpi import GenericScpi as DefaultGeneric

__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'


class GenericScpiState(DefaultGeneric, metaclass=abc.ABCMeta):
    def __init__(self, connection, prompt=None, newline_chars=None, runner=None):
        """
        Base class for Scpi commands in state SCPI.

        :param connection: connection to device.
        :param prompt: expected prompt sending by device after command execution. Maybe String or compiled re.
        :param newline_chars:  new line chars on device (a list).
        :param runner: runner to run command.
        """

        super(GenericScpiState, self).__init__(connection=connection, prompt=prompt, newline_chars=newline_chars,
                                               runner=runner)
