# -*- coding: utf-8 -*-
"""
One of Moler's goals is to be IO-agnostic.

So it can be used under twisted, asyncio, curio any any other IO system.

Moler's connection is very thin layer binding Moler's ConnectionObserver with external IO system.
Connection responsibilities:
- have a means for sending outgoing data via external IO
- have a means for receiving incoming data from external IO
- perform data encoding/decoding to let external IO use pure bytes
- have a means allowing multiple observers to get it's received data (data dispatching)
"""

__author__ = 'Grzegorz Latuszek, Marcin Usielski, Michal Ernst'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com, michal.ernst@nokia.com'

import logging

from moler.config.loggers import RAW_DATA, TRACE
from moler.exceptions import WrongUsage
from moler.helpers import instance_id
from moler.util.loghelper import log_into_logger


def identity_transformation(data):
    """Code. Default coder is no encoding/decoding."""
    return data


class AbstractMolerConnection:
    """Connection API required by ConnectionObservers."""

    def __init__(self, how2send=None, encoder=identity_transformation, decoder=identity_transformation,
                 name=None, newline='\n', logger_name=""):
        """
        Create Connection via registering external-IO.

        Logger is retrieved by logging.getLogger(logger_name)
        If logger_name == "" - take logger "moler.connection.<name>".
        If logger_name is None - don't use logging.
        :param how2send: any callable performing outgoing IO
        :param encoder: callable converting data to bytes
        :param decoder: callable restoring data from bytes
        :param name: name assigned to connection
        :param logger_name: take that logger from logging
        :param newline: new line character
        """
        super(AbstractMolerConnection, self).__init__()
        self.how2send = how2send or self._unknown_send
        self._encoder = encoder
        self._decoder = decoder
        self._name = self._use_or_generate_name(name)
        self.newline = newline
        self.data_logger = logging.getLogger(f'moler.{self.name}')
        self.logger = AbstractMolerConnection._select_logger(logger_name, self._name)
        self._is_open = True
        self._enabled_logging = True  # Set True to log incoming data. False to not log incoming data.

    @property
    def name(self):
        """Get name of connection."""
        return self._name

    @name.setter
    def name(self, value):
        """
        Set name of connection.

        If connection is using default logger ("moler.connection.<name>")
        then modify logger after connection name change.
        """
        if self._name == value:
            return
        self._log(level=TRACE, msg=f'changing name: {self._name} --> {value}', levels_to_go_up=2)
        if self._using_default_logger():
            self.logger = AbstractMolerConnection._select_logger(logger_name="", connection_name=value)
        self._name = value

    def set_data_logger(self, logger):
        """
        Set logger for data.

        :param logger: logger
        :return: None
        """
        self.data_logger = logger

    def __str__(self):
        """
        Return string representation of the object.

        :return String with representation of the object.
        """
        return f'{self.__class__.__name__}(id:{instance_id(self)})'

    def __repr__(self):
        """
        Return string representation (repr) of the object.

        :return String with representation of the object.
        """
        cmd_str = self.__str__()
        # sender_str = "<Don't know>"
        sender_str = "?"
        if self.how2send != self._unknown_send:
            sender_str = repr(self.how2send)
        # return f'{cmd_str[:-1]}, how2send {sender_str})'
        return f'{cmd_str}-->[{sender_str}]'

    def _use_or_generate_name(self, name):
        if name:
            return name  # use provided one
        return instance_id(self)  # generate

    @staticmethod
    def _select_logger(logger_name, connection_name):
        if logger_name is None:
            return None  # don't use logging
        default_logger_name = f"moler.connection.{connection_name}"
        name = logger_name or default_logger_name
        logger = logging.getLogger(name)

        if logger_name and (logger_name != default_logger_name):
            msg = f"using '{logger_name}' logger - not default '{default_logger_name}'"
            logger.log(level=logging.WARNING, msg=msg)
        return logger

    def _using_default_logger(self):
        if self.logger is None:
            return False
        return self.logger.name == f"moler.connection.{self._name}"

    @staticmethod
    def _strip_data(data):
        return data.strip() if isinstance(data, str) else data

    # TODO: should timeout be property of IO? We timeout whole connection-observer.
    # pylint: disable-next=unused-argument
    def send(self, data, timeout=30, encrypt=False, levels_to_go_up=2):
        """Outgoing-IO API: Send data over external-IO."""
        if not self.is_open():
            return
        msg = data
        if encrypt:
            length = len(data)
            msg = "*" * length

        self._log_data(msg=msg, level=logging.INFO,
                       extra={'transfer_direction': '>', 'encoder': lambda data: data.encode('utf-8')})
        self._log(level=logging.INFO,
                  msg=AbstractMolerConnection._strip_data(msg),
                  extra={
                      'transfer_direction': '>',
                      'log_name': self.name
                  },
                  levels_to_go_up=levels_to_go_up)

        encoded_msg = self.encode(msg)
        self._log_data(msg=encoded_msg, level=RAW_DATA,
                       extra={'transfer_direction': '>', 'encoder': lambda data: data.encode('utf-8')})

        encoded_data = self.encode(data)
        # noinspection PyArgumentList
        self.how2send(encoded_data)

    def change_newline_seq(self, newline_seq="\n"):
        r"""
        Change newline char(s).

        Useful when connect from one point to another if newline chars change (i.e. "\n", "\n").
        :param newline_seq: Sequence of chars to send as new line char(s)
        :return: None
        """
        if self.newline != newline_seq:
            characters = [ord(char) for char in self.newline]
            newline_old = "0x" + ''.join(f"'{a:02X}'" for a in characters)
            characters = [ord(char) for char in newline_seq]
            newline_new = "0x" + ''.join(f"'{a:02X}'" for a in characters)
            # 11 15:30:32.855 DEBUG        moler.connection.UnixRemote1    |changing newline seq old '0x'0D''0A'' -> new '0x'0A''
            self._log(logging.DEBUG, f"changing newline seq old '{newline_old}' -> new '{newline_new}'")
        self.newline = newline_seq

    def sendline(self, data, timeout=30, encrypt=False):
        """Outgoing-IO API: Send data line over external-IO."""
        line = data + self.newline
        self.send(data=line, timeout=timeout, encrypt=encrypt, levels_to_go_up=3)

    def data_received(self, data, recv_time):
        """Incoming-IO API: external-IO should call this method when data is received."""

    def encode(self, data):
        """Prepare data for Outgoing-IO."""
        encoded_data = self._encoder(data)
        return encoded_data

    def decode(self, data):
        """Process data from Incoming-IO."""
        decoded_data = self._decoder(data)
        return decoded_data

    def shutdown(self):
        """
        Close connection with notifying all observers about closing.

        :return: None
        """
        self._is_open = False

    def open(self):
        """
        Open connection. If implementation of MolerConnection does not do anything on open then does nothing.

        :return: None
        """
        self._is_open = True

    def is_open(self):
        """
        Call to check if connection is open.

        :return: True if connection is open, False otherwise.
        """
        return self._is_open

    def _unknown_send(self, data2send):
        err_msg = f"Can't send('{data2send}')"
        err_msg += "\nYou haven't installed sending method of external-IO system"
        err_msg += f"\n{{'Do it either during connection construction: {self.__class__.__name__}(how2send=external_io_send)}}'"
        err_msg += "\nor later via attribute direct set: connection.how2send = external_io_send"
        self._log(level=logging.ERROR, msg=err_msg)
        raise WrongUsage(err_msg)

    def _log_data(self, msg, level, extra=None):
        if not self._enabled_logging:
            return
        try:
            self.data_logger.log(level, msg, extra=extra)
        except Exception as err:
            print(err)  # logging errors should not propagate

    def _log(self, level, msg, extra=None, levels_to_go_up=1):
        if not self._enabled_logging:
            return
        if self.logger:
            extra_params = {
                'log_name': self.name
            }

            if extra:
                extra_params.update(extra)
            try:
                # levels_to_go_up=1 : extract caller info to log where _log() has been called from
                log_into_logger(logger=self.logger, level=level, msg=msg, extra=extra_params,
                                levels_to_go_up=levels_to_go_up)
            except Exception as err:
                print(err)  # logging errors should not propagate

    def disable_logging(self):
        """
        Disable logging incoming data.

        :return: None
        """
        if self._enabled_logging:
            msg = "Logging incoming data disabled at user request."
            self._log_data(level=logging.WARN, msg=msg)
            self._log(level=logging.WARN, msg=msg)
        self._enabled_logging = False

    def enable_logging(self):
        """
        Enable logging incoming data.

        :return: None
        """
        if not self._enabled_logging:
            self._enabled_logging = True
            msg = "Logging incoming data enabled at user request."
            self._log_data(level=logging.INFO, msg=msg)
            self._log(level=logging.INFO, msg=msg)

    def get_runner(self):
        """
        Get runner instance for the connection.

        :return: Runner instance or None if runner is not provided by connection.
        """
        return None
