# -*- coding: utf-8 -*-
"""
Command is a type of ConnectionObserver.
Additionally:
- it starts by sending command string over connection - starting CMD(*)
- it focuses on parsing the output caused by that CMD
- it stores string starting that CMD inside .command_string attribute

(*) we use naming CMD to differentiate from Command class naming:
- CMD - command started on some device like 'ls -l' that has its own output
- Command - Python code automating its startup/parsing/completion
"""

__author__ = 'Grzegorz Latuszek, Marcin Usielski, Michal Ernst'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com, michal.ernst@nokia.com'

from abc import ABCMeta

from typing import Optional

from moler.connection_observer import ConnectionObserver
from moler.exceptions import NoCommandStringProvided
from moler.helpers import instance_id
from moler.abstract_moler_connection import AbstractMolerConnection
from moler.runner import ConnectionObserverRunner


# pylint: disable=W0223
class Command(ConnectionObserver, metaclass=ABCMeta):
    def __init__(self, connection: Optional[AbstractMolerConnection] = None, runner: Optional[ConnectionObserverRunner] = None):
        """
        Create instance of Command class
        :param connection: connection used to start CMD and receive its output
        """
        super(Command, self).__init__(connection=connection, runner=runner)
        self.command_string: Optional[str] = None
        self.cmd_name: str = Command.observer_name

    def __str__(self):
        cmd_str = self.command_string if self.command_string else '<EMPTY COMMAND STRING>'
        if cmd_str[-1] == '\n':
            cmd_str = f"{cmd_str[:-1]}<\\n>"
        return f'{self.__class__.__name__}("{cmd_str}", id:{instance_id(self)})'

    def _validate_start(self, *args, **kwargs) -> None:
        # check base class invariants first
        super(Command, self)._validate_start(*args, **kwargs)
        # then what is needed for command
        if self.command_string is None:
            # no chance to start CMD
            raise NoCommandStringProvided(self)

    def get_long_desc(self) -> str:
        return f"Command {self.__class__.__module__}.{self}"

    def get_short_desc(self) -> str:
        return f"Command {self.__class__.__module__}.{self.__class__.__name__}(id:{instance_id(self)})"

    def is_command(self) -> bool:
        """
        :return: True if instance of ConnectionObserver is a command. False if not a command.
        """
        return True

    def send_command(self) -> None:
        """
        Sends command string over connection.

        :return: None
        """
        self.connection.sendline(self.command_string)
