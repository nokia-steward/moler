# -*- coding: utf-8 -*-
"""
Generic juniperex module.
"""

import abc
from moler.cmd.commandtextualgeneric import CommandTextualGeneric

__author__ = 'Sylwester Golonka'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'sylwester.golonka@nokia.com'


class GenericJuniperEXCommand(CommandTextualGeneric, metaclass=abc.ABCMeta):
    """Genericjuniperexcommand command class."""
