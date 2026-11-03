# -*- coding: utf-8 -*-
"""
External-IO connections.

The only 3 requirements for these connections is:
(1) store Moler's connection inside self.moler_connection attribute
(2) forward IO received data into self.moler_connection.data_received(data)
(3) provide Moler connection with method to send outgoing data:

  self.moler_connection.how2send = self.send

We want all connections of this subpackage to have
open()/close() API
even that for memory connection that may have no sense
but for majority (tcp, udp, ssh, process ...) it applies,
so lets have common API.
Moreover, we will map it to context manager API.

send()/receive() is required but we cant force naming here since
it's better to keep native/well-known naming of external-IO
(send/recv for socket, transport.write/data_received for asyncio, ...)
Specific external-IO implementation must do data-forwarding and
send-plugin as stated above.
NOTE: send/receive works on bytes since encoding/decoding
is responsibility of moler_connection

So, below class is not needed to work as base class. It may, but
rather it is generic template how to glue external-IO with Moler's connection.
"""

__author__ = "Grzegorz Latuszek, Marcin Usielski"
__copyright__ = "Copyright (C) 2018-2026, Nokia"
__email__ = "grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com"

import contextlib
import logging
from threading import Lock
from moler.connection import Connection
from typing import Callable, List
from datetime import datetime


class IOConnection:
    """External-IO connection."""

    def __init__(self, moler_connection: Connection):
        """
        Specific constructor of external-IO should store information
        how to establish connection (like host/port info)

        :param moler_connection: object of abstract class moler.connection.Connection
        """
        super(IOConnection, self).__init__()
        self._connect_subscribers: List[Callable] = []
        self._connect_subscribers_lock = Lock()
        self._disconnect_subscribers: List[Callable] = []
        self._disconnect_subscribers_lock = Lock()
        self.moler_connection: Connection = moler_connection
        self.__name: str = "UNNAMED_IO_CONNECTION"
        self.logger = logging.getLogger(f"moler.connection.{self.__name}.io")
        # plugin the way we output data to external world
        self.moler_connection.how2send = self.send

    @property
    def name(self) -> str:
        return self.__name

    @name.setter
    def name(self, value: str) -> None:
        self.__name = value
        self.logger = logging.getLogger(f"moler.connection.{self.__name}.io")

    def open(self) -> contextlib.closing:
        """
        Take 'how to establish connection' info from constructor
        and open that connection.

        Return context manager to allow for:  with connection.open() as conn:
        """
        self.moler_connection.open()
        return contextlib.closing(self)

    def close(self) -> None:
        """Close established connection."""

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # reraise exceptions if any

    def send(self, data: str) -> None:
        """
        Send data bytes over external-IO.

        Because of plugin done in constructor it will be called
        by moler_connection when it needs.
        """

    def receive(self) -> bytes:
        """
        Pull data bytes from external-IO:
            data = io_connection.receive()
        and then forward it to Moler's connection:
            self.moler_connection.data_received(data)
        """
        return b""

    def data_received(self, data: str, recv_time: datetime) -> None:
        """
        Having been given data bytes from external-IO:

        just forward it to Moler's connection:
        """
        self.moler_connection.data_received(data=data, recv_time=recv_time)

    def notify(self, callback: Callable, when: str) -> None:
        """
        Adds subscriber to list of functions to call
        :param callback: reference to function to call when connection is open/established
        :param when: connection state change
        :return: None
        """
        if when == "connection_made":
            self.subscribe_on_connection_made(subscriber=callback)
        elif when == "connection_lost":
            self.subscribe_on_connection_lost(subscriber=callback)

    def subscribe_on_connection_made(self, subscriber: Callable) -> None:
        """
        Adds subscriber to list of functions to call when connection is open/established (also reopen after close)
        :param subscriber: reference to function to call when connection is open/established
        :return: None
        """
        self._subscribe(
            self._connect_subscribers_lock, self._connect_subscribers, subscriber
        )

    def subscribe_on_connection_lost(self, subscriber: Callable) -> None:
        """
        Adds subscriber to list of functions to call when connection is closed/disconnected
        :param subscriber: reference to function to call when connection is closed/disconnected
        :return: None
        """
        self._subscribe(
            self._disconnect_subscribers_lock, self._disconnect_subscribers, subscriber
        )

    def unsubscribe_on_connection_made(self, subscriber: Callable) -> None:
        """
        Remove subscriber from list of functions to call when connection is open/established (also reopen after close)
        :param subscriber: reference to function registered by method subscribe_on_connection_made
        :return: None
        """
        self._unsubscribe(
            self._connect_subscribers_lock, self._connect_subscribers, subscriber
        )

    def unsubscribe_on_connection_lost(self, subscriber: Callable) -> None:
        """
        Remove subscriber from list of functions to call when connection is closed/disconnected
        :param subscriber: reference to function registered by method subscribe_on_connection_lost
        :return: None
        """
        self._unsubscribe(
            self._disconnect_subscribers_lock, self._disconnect_subscribers, subscriber
        )

    def disable_logging(self) -> None:
        """
        Disable logging incoming data.
        :return: None
        """
        self.moler_connection.disable_logging()

    def enable_logging(self) -> None:
        """
        Enable logging incoming data.
        :return: None
        """
        self.moler_connection.enable_logging()

    def _notify(self, lock: Lock, subscribers: List[Callable]) -> None:
        with lock:
            copied_subscribers = subscribers[:]
            for subscriber in copied_subscribers:
                subscriber(self)

    def _notify_on_connect(self) -> None:
        self.logger.info(
            msg=f"Connection to: '{self.name}' has been opened.",
            extra={"log_name": self.name},
        )
        self._notify(self._connect_subscribers_lock, self._connect_subscribers)

    def _notify_on_disconnect(self) -> None:
        self.logger.info(
            msg=f"Connection to: '{self.name}' has been closed.",
            extra={"log_name": self.name},
        )
        self._notify(self._disconnect_subscribers_lock, self._disconnect_subscribers)

    def _subscribe(self, lock: Lock, subscribers: List[Callable], subscriber: Callable) -> None:
        with lock:
            if subscriber not in subscribers:
                subscribers.append(subscriber)

    def _unsubscribe(self, lock: Lock, subscribers: List[Callable], subscriber: Callable) -> None:
        with lock:
            if subscriber in subscribers:
                subscribers.remove(subscriber)
