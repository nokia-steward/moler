# -*- coding: utf-8 -*-
"""
External-IO connections based on memory buffer.

The only 3 requirements for these connections are:
(1) store Moler's connection inside self.moler_connection attribute
(2) plugin into Moler's connection the way IO outputs data to external world:

    self.moler_connection.how2send = self.send

(3) forward IO received data into self.moler_connection.data_received(data)

Logging inside ext-IO is mainly focused on connection establishment/close/drop.
Data transfer aspects of connection are logged by embedded Moler's connection.
"""

__author__ = 'Grzegorz Latuszek, Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com'

import threading
import time
import logging
import datetime
from queue import Queue, Empty

from moler.io.io_connection import IOConnection
from moler.io.raw import TillDoneThread
from moler.config.loggers import TRACE
from moler.util import tracked_thread


class FifoBuffer(IOConnection):
    r"""
    FIFO-in-memory.::

        inject             |\
                 +---------+ \  read
        write    +---------+ /
                           |/

    Usable for unit tests (manually inject what is expected).
    """
    def __init__(self, moler_connection, echo=True, name=None, logger_name=""):
        """
        Initialization of FIFO-in-memory connection.

        :param moler_connection: Moler's connection to join with
        :param echo: do we want echo of written data
        :param name: name assigned to connection
        :param logger_name: take that logger from logging

        Logger is retrieved by logging.getLogger(logger_name)
        If logger_name == "" - take logger "<moler-connection-logger>.io"
        If logger_name is None - don't use logging
        """
        super(FifoBuffer, self).__init__(moler_connection=moler_connection)
        if name:
            self._name = name
            self.moler_connection.name = name
        else:
            self._name = moler_connection.name
        self.echo = echo
        self.logger = self._select_logger(logger_name, self._name, moler_connection)
        self.buffer = bytearray()
        self.deferred_injections = []

    @property
    def name(self):
        """Get name of connection"""
        return self._name

    @name.setter
    def name(self, value):
        """
        Set name of connection

        Moreover, overwrite name of embedded Moler's connection
        since the two compose "one logical connection".

        If connection is using default logger ("moler.connection.<name>.io")
        then modify logger after connection name change.
        """
        self._log(msg=f'changing name: {self._name} --> {value}', level=TRACE)
        self.moler_connection.name = value
        if self._using_default_logger():
            self.logger = self._select_logger(logger_name="",
                                              connection_name=value,
                                              moler_connection=self.moler_connection)
        self._name = value

    @staticmethod
    def _select_logger(logger_name, connection_name, moler_connection):
        if logger_name is None:
            return None  # don't use logging
        default_logger_name = f"moler.connection.{connection_name}.io"
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

    def _using_default_logger(self):
        if self.logger is None:
            return False
        return self.logger.name == f"moler.connection.{self._name}.io"

    def inject(self, input_bytes, delay=0.0):
        """
        Add bytes to FIFO with injection-delay before each data

        :param input_bytes: iterable of bytes to inject
        :param delay: delay before each inject
        :return: None
        """
        for data in input_bytes:
            if delay:
                time.sleep(delay)
            self._inject(data)

    def inject_response(self, input_bytes, delay=0.0):
        """
        Injection is activated by nearest write()

        :param input_bytes: iterable of bytes to inject
        :param delay: delay before each inject
        :return: None
        """
        for data in input_bytes:
            self.deferred_injections.append((data, delay))

    def _inject(self, data):
        """Add bytes to end of buffer"""
        if hasattr(data, '__iter__') or hasattr(data, '__getitem__'):
            self.buffer.extend(data)
        else:
            self.buffer.append(data)

    def _inject_deferred(self):
        if self.deferred_injections:
            for data, delay in self.deferred_injections:
                if delay:
                    time.sleep(delay)
                self._inject(data)
            self.deferred_injections = []

    def write(self, input_bytes):
        """
        What is written to connection comes back on read()
        only if we simulate echo service of remote end.
        """
        if self.echo:
            self.inject([input_bytes])
        self._inject_deferred()

    send = write  # just alias to make base class happy :-)

    def read(self, bufsize=None):
        """Remove bytes from front of buffer"""
        if bufsize is None:
            size2read = len(self.buffer)
        elif len(self.buffer) >= bufsize:
            size2read = bufsize
        else:
            size2read = len(self.buffer)
        if size2read > 0:
            data = self.buffer[:size2read]
            self.buffer = self.buffer[size2read:]
            self.data_received(data, recv_time=datetime.datetime.now())
            return data
        else:
            return b''

    receive = read  # just alias to make base class happy :-)

    def __str__(self):
        return f'{self._name}:FIFO-in-memory'

    def _log(self, msg, level, extra=None):
        if self.logger:
            self.logger.log(level, msg, extra=extra)


class ThreadedFifoBuffer(FifoBuffer):
    """
    FIFO-in-memory connection inside dedicated thread.

    This is external-IO usable for Moler since it has it's own runner
    (thread) that can work in background and pull data from FIFO-mem connection.
    Usable for integration tests.
    """

    def __init__(self, moler_connection, echo=True, name=None, logger_name=""):
        """Initialization of FIFO-mem-threaded connection."""
        super(ThreadedFifoBuffer, self).__init__(moler_connection=moler_connection,
                                                 echo=echo,
                                                 name=name,
                                                 logger_name=logger_name)
        self.pulling_thread = None
        self.injections = Queue()

    def open(self):
        """Start thread pulling data from FIFO buffer."""
        ret = super(ThreadedFifoBuffer, self).open()
        done = threading.Event()
        if self.pulling_thread is None:
            self.pulling_thread = TillDoneThread(target=self.pull_data,
                                                 done_event=done,
                                                 kwargs={'pulling_done': done})
            self.pulling_thread.start()
            self._log(msg=f"open {self}", level=logging.INFO)
            self._notify_on_connect()
            self.moler_connection.open()
        return ret

    def close(self):
        """Stop pulling thread."""
        if self.pulling_thread:
            self.pulling_thread.join()
            self.pulling_thread = None
        super(ThreadedFifoBuffer, self).close()
        self._log(msg=f"closed {self}", level=logging.INFO)
        self._notify_on_disconnect()
        self.moler_connection.shutdown()

    def inject(self, input_bytes, delay=0.0):
        """
        Add bytes to end of buffer

        :param input_bytes: iterable of bytes to inject
        :param delay: delay before each inject
        :return: None
        """
        for data in input_bytes:
            self.injections.put((data, delay))
        if not delay:
            time.sleep(0.05)  # give subsequent read() a chance to get data

    def _inject_deferred(self):
        if self.deferred_injections:
            for data, delay in self.deferred_injections:
                self.injections.put((data, delay))
            self.deferred_injections = []
            time.sleep(0.05)  # give subsequent read() a chance to get data

    @tracked_thread.log_exit_exception
    def pull_data(self, pulling_done):
        """Pull data from FIFO buffer."""
        logging.getLogger("moler_threads").debug(f"ENTER {self}")
        heartbeat = tracked_thread.report_alive()
        while not pulling_done.is_set():
            if next(heartbeat):
                logging.getLogger("moler_threads").debug(f"ALIVE {self}")
            self.read()  # internally forwards to embedded Moler connection
            try:
                data, delay = self.injections.get_nowait()
                if delay:
                    time.sleep(delay)
                self._inject(data)
                self.injections.task_done()
            except Empty:
                time.sleep(0.01)  # give FIFO chance to get data
        logging.getLogger("moler_threads").debug(f"EXIT  {self}")
