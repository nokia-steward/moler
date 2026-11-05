# -*- coding: utf-8 -*-
"""
External-IO connections based on Paramiko.

The only 3 requirements for these connections are:
(1) store Moler's connection inside self.moler_connection attribute
(2) plugin into Moler's connection the way IO outputs data to external world:

    self.moler_connection.how2send = self.send

(3) forward IO received data into self.moler_connection.data_received(data)
"""

__author__ = 'Grzegorz Latuszek, Marcin Usielski'
__copyright__ = 'Copyright (C) 2020-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com'

import socket
import threading
import contextlib
import paramiko
import time
import getpass
import logging
from moler.helpers import instance_id
from moler.util.loghelper import log_into_logger
from moler.util import tracked_thread

from moler.io.io_exceptions import ConnectionTimeout
from moler.io.io_exceptions import RemoteEndpointDisconnected
from moler.io.io_exceptions import RemoteEndpointNotConnected
from moler.io.io_connection import IOConnection
from moler.io.raw import TillDoneThread
import datetime


class SshShell:
    """
    Implementation of 'remote shell over Ssh' connection using python Paramiko module

    This connection is not intended for one-shot actions like execute_command of paramiko.
    Its purpose is to provide continuous stream of bytes from remote shell.
    Moreover, it works with Pty assigned to remote shell to enable interactive dialog
    like asking for login or password.
    """
    _channels_of_transport = {}  # key is instance_id(transport), value is list of channel IDs

    def __init__(self, host, port=22, username=None, login=None, password=None, receive_buffer_size=64 * 4096,
                 logger=None, existing_client=None):
        """
        Initialization of SshShell connection.

        :param host: host of ssh server where we want to connect
        :param port: port of ssh server
        :param username: username for password based login
        :param login: alternate naming for username param (as it is used by OpenSSH) for parity with Ssh command
        :param password: password for password based login
        :param receive_buffer_size:
        :param logger: logger to use (None means no logging)
        :param existing_client: (internal use) for reusing ssh transport of existing sshshell
        """
        super(SshShell, self).__init__()
        self.host = host
        self.port = port
        if (username is not None) and (login is not None):
            raise KeyError(f"Use either 'username' ({username}) or 'login' ({login}), not both")
        username = login if username is None else username
        self.username = getpass.getuser() if username is None else username
        self.password = password
        self.receive_buffer_size = receive_buffer_size
        self.logger = logger

        self.ssh_client = existing_client if existing_client else paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._shell_channel = None  # MOST IMPORTANT
        self.timeout = None
        self.await_ready_tick_resolution = 0.01

    @classmethod
    def from_sshshell(cls, sshshell, logger=None):
        """
        Build new sshshell based on existing one - it will reuse its transport

        No need to provide host, port and login credentials - they will be reused.
        You should use this constructor if you are connecting towards same host/port using same credentials.

        :param sshshell: existing connection to reuse it's ssh transport
        :param logger: new logger for new connection
        :return: instance of new sshshell connection with reused ssh transport
        """
        assert isinstance(sshshell, SshShell)
        assert issubclass(cls, SshShell)
        new_sshshell = cls(host=sshshell.host, port=sshshell.port,
                           username=sshshell.username, password=sshshell.password,
                           receive_buffer_size=sshshell.receive_buffer_size,
                           logger=logger, existing_client=sshshell.ssh_client)
        return new_sshshell

    @property
    def _ssh_transport(self):
        return self.ssh_client.get_transport()

    def _settimeout(self, timeout):
        if (self.timeout is None) or (timeout != self.timeout):
            if self._shell_channel:
                self._shell_channel.settimeout(timeout)
                self.timeout = timeout

    def open(self):
        """
        Open Ssh channel to remote shell.

        If SshShell was created with "reused ssh transport" then no new transport is created - just shell channel.
        (such connection establishment is quicker)
        Else - before creating channel we create ssh transport and perform full login with provided credentials.

        May be used as context manager: with connection.open():
        """
        if self._shell_channel is None:
            self._debug(f'connecting to {self}')

            transport = self.ssh_client.get_transport()
            if transport is None:
                self.ssh_client.connect(self.host, username=self.username, password=self.password)
                transport = self.ssh_client.get_transport()
                action = "established"
            else:
                action = "reusing"
            transport_info = f'local version = {transport.local_version}, remote version = {transport.remote_version}, using socket = {transport.sock}'
            self._debug(f'  {action} ssh transport to {self.host}:{self.port} |{transport}\n{transport_info}')
            self._shell_channel = self.ssh_client.invoke_shell()  # newly created channel will be connected to Pty
            self._remember_channel_of_transport(self._shell_channel)
            self._debug(f'  established shell ssh to {self.host}:{self.port} [channel {self._shell_channel.get_id()}] |{self._shell_channel}')
        self._info(f'connection {self} is open')
        return contextlib.closing(self)

    @classmethod
    def _remember_channel_of_transport(cls, channel):
        transport_id = instance_id(channel.get_transport())
        channel_id = channel.get_id()
        if transport_id in cls._channels_of_transport:
            cls._channels_of_transport[transport_id].append(channel_id)
        else:
            cls._channels_of_transport[transport_id] = [channel_id]

    @classmethod
    def _forget_channel_of_transport(cls, channel):
        transport_id = instance_id(channel.get_transport())
        channel_id = channel.get_id()
        if transport_id in cls._channels_of_transport:
            cls._channels_of_transport[transport_id].remove(channel_id)
            if len(cls._channels_of_transport[transport_id]) == 0:
                del cls._channels_of_transport[transport_id]

    @classmethod
    def _num_channels_of_transport(cls, transport):
        transport_id = instance_id(transport)
        if transport_id in cls._channels_of_transport:
            return len(cls._channels_of_transport[transport_id])
        return 0

    def close(self):
        """
        Close SshShell connection. Close channel of that connection.

        If SshShell was created with "reused ssh transport" then closing will close only ssh channel of remote shell.
        Ssh transport will be closed after it's last channel is closed.
        """
        if self._shell_channel is not None:
            self._debug(f'closing {self}')
        self._close()

    def _close(self):
        which_channel = ""
        if self._shell_channel is not None:
            which_channel = f"[channel {self._shell_channel.get_id()}] "
            self._shell_channel.close()
            time.sleep(0.05)  # give Paramiko threads time to catch correct value of status variables
            self._debug(f'  closed shell ssh to {self.host}:{self.port} {which_channel}|{self._shell_channel}')
            self._forget_channel_of_transport(self._shell_channel)
            self._shell_channel = None
        transport = self.ssh_client.get_transport()
        if transport is not None:
            if self._num_channels_of_transport(transport) == 0:
                self._debug(f'  closing ssh transport to {self.host}:{self.port} |{transport}')
                self.ssh_client.close()
        self._info(f'connection {self} {which_channel}is closed')

    def __enter__(self):
        """While working as context manager connection should auto-open if it's not open yet."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # reraise exceptions if any

    def __str__(self):
        if self._shell_channel:
            shell_channel_id = self._shell_channel.get_id()
            address = f'ssh://{self.username}@{self.host}:{self.port} [channel {shell_channel_id}]'
        else:
            address = f'ssh://{self.username}@{self.host}:{self.port}'
        return address

    def send(self, data, timeout=1):
        """
        Send data via SshShell connection.

        :param data: data
        :type data: bytes
        :param timeout: max time to spend on sending all data, default 1 sec
        :type timeout: float
        """
        if not self._shell_channel:
            msg = f"No shell channel for SshShell to '{self.username}@{self.host}'. Connection is already closed or never open. "
            self._info(msg)
            raise RemoteEndpointNotConnected(msg)
        assert timeout > 0.0
        try:
            self._send(data, timeout)
        except socket.error as socket_err:
            if "Socket is closed" in str(socket_err):
                self._close()
                info = f"{socket_err} during send msg '{data}' for SshShell to '{self.username}@{self.host}'"
                msg = f"Socket error: '{info}'"
                self._info(msg)
                raise RemoteEndpointDisconnected(msg) from socket_err
            else:
                raise  # let any other error be visible

    def _send(self, data, timeout=1.0):
        start_time = time.monotonic()
        nb_bytes_to_send = len(data)
        nb_bytes_sent = 0
        data2send = data
        while True:
            if self._shell_channel.send_ready():
                chunk_bytes_sent = self._shell_channel.send(data2send)
                nb_bytes_sent += chunk_bytes_sent
            else:
                time.sleep(self.await_ready_tick_resolution)
            if nb_bytes_sent >= nb_bytes_to_send:
                break
            if time.monotonic() - start_time >= timeout:
                send_status = f'[{nb_bytes_sent} of {nb_bytes_to_send} bytes] {data}'
                # don't want to show class name - just ssh address
                # want same output from any implementation of SshShell-connection
                info = f"Timeout (> {timeout:.3f} sec) on {self}, sent {send_status}"
                raise ConnectionTimeout(info)
            data2send = data[nb_bytes_sent:]

    def receive(self, timeout=30.0):
        """
        Receive data.

        :param timeout: max time to await for data, default 30 sec
        :type timeout: float
        """
        self._settimeout(timeout=timeout)
        data = self._recv()
        return data

    def _recv(self):
        """Receive data."""
        if not self._shell_channel:
            self._info(f"There is no shell channel for SshShell (already closed or never open) to '{self.username}@{self.host}'.")
            raise RemoteEndpointNotConnected()
        try:
            # ensure we will never block in channel.recv()
            if not self._shell_channel.gettimeout():
                self._shell_channel.settimeout(self.await_ready_tick_resolution)
            data = self._shell_channel.recv(self.receive_buffer_size)
        except socket.timeout as exc:
            # don't want to show class name - just ssh address
            # want same output from any implementation of SshShell-connection
            info = f"Timeout (> {self.timeout:.3f} sec) on {self}"
            raise ConnectionTimeout(info) from exc

        if not data:
            msg = f"No data received. Disconnected. shell ssh channel closed for {self}"
            self._info(msg)
            self._close()
            raise RemoteEndpointDisconnected(msg)

        return data

    def _debug(self, msg, levels_to_go_up=2):
        self._log(level=logging.DEBUG, msg=msg, levels_to_go_up=levels_to_go_up)

    def _info(self, msg, levels_to_go_up=2):
        self._log(level=logging.INFO, msg=msg, levels_to_go_up=levels_to_go_up)

    def _log(self, msg, level, levels_to_go_up=1):
        if self.logger:
            try:
                # levels_to_go_up=1 : extract caller info to log where _log() has been called from
                log_into_logger(logger=self.logger, level=level, msg=msg, levels_to_go_up=levels_to_go_up)
            except Exception as err:
                print(err)  # logging errors should not propagate


##################################################################################################################
# SshShell and ThreadedSshShell differ in API - ThreadedSshShell gets moler_connection
# It is intentional architecture decision: SshShell has much looser binding with moler.
# Thanks to this it's reuse possibility is wider.
# As a consequence ThreadedSshShell uses SshShell via composition.
#
# Moreover, SshShell is passive connection - needs pulling for data
#           and ThreadedSshShell is active connection - pushes data by itself (same model as asyncio, Twisted, etc)
###################################################################################################################


class ThreadedSshShell(IOConnection):
    """
    SshShell connection feeding Moler's connection inside dedicated thread.

    This is external-IO usable for Moler since it has it's own runner
    (thread) that can work in background and pull data from SshShell connection.
    """

    def __init__(self, moler_connection,
                 host, port=22, username=None, login=None, password=None,
                 receive_buffer_size=64 * 4096,
                 name=None,
                 logger_name="",
                 existing_client=None):
        """
        Initialization of SshShell-threaded connection.

        :param moler_connection: moler-dispatching-connection to use for data forwarding
        :param host: host of ssh server where we want to connect
        :param port: port of ssh server
        :param username: username for password based login
        :param login: alternate naming for username param (as it is used by OpenSSH) for parity with Ssh command
        :param password: password for password based login
        :param receive_buffer_size:
        :param name: name assigned to connection
        :param logger_name: take that logger from logging
        :param existing_client: (internal use) for reusing ssh transport of existing sshshell

        Logger is retrieved by logging.getLogger(logger_name)
        If logger_name == "" - take default logger "<moler-connection-logger>.io"
        If logger_name is None - don't use logging
        """
        if name:
            moler_connection.name = name
        super(ThreadedSshShell, self).__init__(moler_connection=moler_connection)
        self.logger = self._select_logger(logger_name, self.name, moler_connection)
        self.sshshell = SshShell(host=host, port=port, username=username, login=login, password=password,
                                 receive_buffer_size=receive_buffer_size,
                                 logger=self.logger, existing_client=existing_client)
        self.pulling_thread = None
        self.pulling_timeout = 0.1
        self._pulling_done = threading.Event()

    @classmethod
    def from_sshshell(cls, moler_connection, sshshell, name=None, logger_name=""):
        """
        Build new sshshell based on existing one - it will reuse its transport

        No need to provide host, port and login credentials - they will be reused.
        You should use this constructor if you are connecting towards same host/port using same credentials.

        :param moler_connection: moler-connection may not be reused; we need fresh one
        :param sshshell: existing connection to reuse it's ssh transport
        :param logger_name: new logger for new connection
        :return: instance of new sshshell connection with reused ssh transport
        """
        if isinstance(sshshell, ThreadedSshShell):
            sshshell = sshshell.sshshell
        assert isinstance(sshshell, SshShell)
        assert issubclass(cls, ThreadedSshShell)
        new_sshshell = cls(moler_connection=moler_connection, host=sshshell.host, port=sshshell.port,
                           username=sshshell.username, password=sshshell.password,
                           receive_buffer_size=sshshell.receive_buffer_size, name=name,
                           logger_name=logger_name, existing_client=sshshell.ssh_client)
        return new_sshshell

    @property
    def name(self):
        """Get name of connection"""
        return self.moler_connection.name

    @name.setter
    def name(self, value):
        """
        Set name of connection

        Io and embedded Moler's connection compose "one logical connection".

        If connection is using default logger ("moler.connection.<name>.io")
        then modify logger after connection name change.
        """
        was_using_default_logger = (self.logger is not None) and (self.logger.name == self._default_logger_name(self.name))
        self.moler_connection.name = value
        if was_using_default_logger:
            self.logger = logging.getLogger(self._default_logger_name(self.name))
            self.sshshell.logger = self.logger

    @staticmethod
    def _select_logger(logger_name, connection_name, moler_connection):
        if logger_name is None:
            return None  # don't use logging
        default_logger_name = ThreadedSshShell._default_logger_name(connection_name)
        if logger_name:
            name = logger_name
        else:
            # take it from moler_connection.logger and extend by ".io"
            if moler_connection.logger is None:
                name = default_logger_name
            else:
                name = f"{moler_connection.logger.name}.io"
        logger = logging.getLogger(name)
        if name and (name != default_logger_name):
            msg = f"using '{name}' logger - not default '{default_logger_name}'"
            logger.log(level=logging.WARNING, msg=msg)
        return logger

    @staticmethod
    def _default_logger_name(connection_name):
        return f"moler.connection.{connection_name}.io"

    @property
    def _ssh_transport(self):
        return self.sshshell._ssh_transport  # pylint: disable=protected-access

    @property
    def _shell_channel(self):
        return self.sshshell._shell_channel  # pylint: disable=protected-access

    def __str__(self):
        address = self.sshshell.__str__()
        return address

    def open(self):
        """
        Open Ssh channel to remote shell & start thread pulling data from it.

        If SshShell was created with "reused ssh transport" then no new transport is created - just shell channel.
        (such connection establishment is quicker)
        Else - before creating channel we create ssh transport and perform full login with provided credentials.

        May be used as context manager: with connection.open():
        """
        was_closed = self._shell_channel is None
        self.sshshell.open()
        is_open = self._shell_channel is not None
        if was_closed and is_open:
            self._notify_on_connect()
        if self.pulling_thread is None:
            # set reading timeout in same thread where we open shell and before starting pulling thread
            self.sshshell._settimeout(timeout=self.pulling_timeout)  # pylint: disable=protected-access
            self._pulling_done.clear()
            self.pulling_thread = TillDoneThread(target=self._pull_data,
                                                 done_event=self._pulling_done,
                                                 kwargs={'pulling_done': self._pulling_done})
            self.pulling_thread.start()
        return contextlib.closing(self)

    def close(self):
        """
        Close SshShell connection. Close channel of that connection & stop pulling thread.

        If SshShell was created with "reused ssh transport" then closing will close only ssh channel of remote shell.
        Ssh transport will be closed after it's last channel is closed.
        """
        self._pulling_done.set()
        if self.pulling_thread:
            self.pulling_thread.join()  # _pull_data will do self.sshshell.close()
            self.pulling_thread = None

    def send(self, data, timeout=1):
        """
        Send data via SshShell connection.

        :param data: data
        :type data: bytes
        :param timeout: max time to spend on sending all data, default 1 sec
        :type timeout: float
        """
        self.sshshell.send(data=data, timeout=timeout)

    def receive(self):
        """
        Pull data bytes from external-IO:

            data = io_connection.receive()

        data is intended to forward into Moler's connection:

            self.moler_connection.data_received(data)

        """
        data = self.sshshell._recv()  # pylint: disable=protected-access
        return data

    @tracked_thread.log_exit_exception
    def _pull_data(self, pulling_done):
        """Pull data from SshShell connection."""
        logging.getLogger("moler_threads").debug(f"ENTER {self}")
        heartbeat = tracked_thread.report_alive()
        already_notified = False
        while not pulling_done.is_set():
            if next(heartbeat):
                logging.getLogger("moler_threads").debug(f"ALIVE {self}")
            try:
                data = self.receive()
                if data:
                    self.data_received(data, datetime.datetime.now())  # (3)
            except ConnectionTimeout:
                continue
            except RemoteEndpointNotConnected:
                break
            except RemoteEndpointDisconnected:
                self._notify_on_disconnect()
                already_notified = True
                break
            except Exception as err:
                err_msg = f"Unexpected {err!r} during pulling for data in {self}"
                if self.sshshell.logger:
                    self.sshshell.logger.exception(err_msg)
                else:
                    print(f"ERROR: {err_msg}")
                break
        was_open = self._shell_channel is not None
        self.sshshell.close()
        is_closed = self._shell_channel is None
        if was_open and is_closed and (not already_notified):
            self._notify_on_disconnect()
        logging.getLogger("moler_threads").debug(f"EXIT  {self}")
