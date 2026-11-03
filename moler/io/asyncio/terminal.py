# -*- coding: utf-8 -*-
"""
External-IO connections based on asyncio.

The only 3 requirements for these connections are:
(1) store Moler's connection inside self.moler_connection attribute
(2) plugin into Moler's connection the way IO outputs data to external world:

    self.moler_connection.how2send = self.send

(3) forward IO received data into self.moler_connection.data_received(data)
"""

# Module heavily inspired by:
# https://github.com/osrf/osrf_pycommon/tree/master/osrf_pycommon/process_utils
# thanks William Woodall :-)

# pylint: skip-file

import re
import struct
import termios
import fcntl
import logging

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2018, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import asyncio
import os
import ctypes

from moler.asyncio_runner import get_asyncio_loop_thread, thread_secure_get_event_loop
from moler.io.io_connection import IOConnection
from moler.io.raw.opentty_retry import openpty_with_retry


class AsyncioTerminal(IOConnection):
    """Implementation of Terminal connection using asyncio."""
    def __init__(self, moler_connection, cmd=None, first_prompt=None, dimensions=(100, 300), logger=None):
        """Initialization of Terminal connection."""
        super(AsyncioTerminal, self).__init__(moler_connection=moler_connection)
        self.moler_connection.how2send = self.send  # need to map synchronous methods
        # TODO: do we want connection.name?
        self.name = moler_connection.name

        self.dimensions = dimensions
        if cmd is None:
            cmd = ['/bin/bash', '--init-file']
        self._cmd = self._build_bash_command(cmd)
        if first_prompt:
            self.prompt = first_prompt
        else:
            self.prompt = r'^moler_bash#'
        if logger:  # overwrite base class logger
            self.logger = logger

        self._shell_operable = None
        self._transport = None
        self._protocol = None  # derived from asyncio.SubprocessProtocol
        self.read_buffer = ''

    @staticmethod
    def _build_bash_command(bash_cmd):
        if bash_cmd[-1] == '--init-file':
            abs_path = os.path.dirname(__file__)
            init_file_path = os.path.join(abs_path, "..", "..", "config", "bash_config")
            bash_cmd.append(init_file_path)
        return bash_cmd

    async def open(self):
        """Open AsyncioTerminal connection & start running it inside asyncio loop."""
        ret = super(AsyncioTerminal, self).open()
        if not self._transport:
            self._shell_operable = asyncio.Future()
            # TODO: pass self.dimensions into pty construction
            transport, protocol = await start_subprocess_in_terminal(protocol_class=PtySubprocessProtocol,
                                                                     cmd=self._cmd, cwd=None,
                                                                     dimensions=self.dimensions)
            self._transport = transport
            self._protocol = protocol
            self._protocol.forward_data = self.data_received  # build forwarding path
            # TODO: do we want timeout here? wait(timeout=2)
            await self._shell_operable
        return ret

    async def close(self):
        """
        Close AsyncioTerminal connection.

        Connection should allow for calling close on closed/not-open connection.
        """
        if self._transport:
            self._protocol.pty_fd_transport.close()  # close pty
            self._transport.close()  # close subprocess
            await self._protocol.complete
            self._protocol = None
            self._transport = None
            self._notify_on_disconnect()

    def send(self, data):
        """Write data into AsyncioTerminal connection."""
        self._protocol.send(data)

    def data_received(self, data, recv_time):
        """
        Await initial prompt of started shell command.

        After that - do real forward
        """
        if not self._shell_operable.done():
            decoded_data = self.moler_connection.decode(data)
            self.logger.debug(f"<|{data}")
            assert isinstance(decoded_data, str)
            self.read_buffer += decoded_data
            if re.search(self.prompt, self.read_buffer, re.MULTILINE):
                self._notify_on_connect()
                self._shell_operable.set_result(True)  # makes Future done
                # TODO: should we remove initial prompt as it is inside raw.terminal?
                # TODO: that way (maybe) we won't see it in logs
                data_str = re.sub(self.prompt, '', self.read_buffer, re.MULTILINE)
                data = self.moler_connection.encode(data_str)
            else:
                return
        self.logger.debug(f"<|{data}")
        super(AsyncioTerminal, self).data_received(data, recv_time)

    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, value):
        self.__name = value
        self.logger = logging.getLogger(f"moler.connection.{self.__name}.io")

    def __str__(self):
        address = f'terminal:{self._cmd[0]}'
        return address

    def __repr__(self):
        address = f'terminal:{self._cmd}'
        return address


class AsyncioInThreadTerminal(IOConnection):
    """Implementation of Terminal connection using asyncio running in dedicated thread."""

    def __init__(self, moler_connection, cmd=None, first_prompt=None, dimensions=(100, 300), logger=None):
        """Initialization of Terminal connection."""
        self._async_terminal = AsyncioTerminal(moler_connection=moler_connection, cmd=cmd, first_prompt=first_prompt,
                                               dimensions=dimensions, logger=logger)
        super(AsyncioInThreadTerminal, self).__init__(moler_connection=moler_connection)

    def open(self):
        """Open TCP connection."""
        ret = super(AsyncioInThreadTerminal, self).open()
        thread4async = get_asyncio_loop_thread()
        thread4async.run_async_coroutine(self._async_terminal.open(), timeout=600.5)  # await initial prompt may be longer
        # no need for 'def send()' in this class since sending goes via moler connection
        # after open() here, moler connection will be bound to data path running inside dedicated thread
        # same for 'def data_received()' - will get data from self._async_terminal
        return ret

    def close(self):
        """
        Close TCP connection.

        Connection should allow for calling close on closed/not-open connection.
        """
        if self._async_terminal._transport:  # change it to coro is_open() checked inside async-thread
            # self._debug('closing {}'.format(self))
            thread4async = get_asyncio_loop_thread()
            thread4async.run_async_coroutine(self._async_terminal.close(), timeout=0.5)
        # self._debug('connection {} is closed'.format(self))

    def notify(self, callback, when):
        """
        Adds subscriber to list of functions to call
        :param callback: reference to function to call when connection is open/established
        :param when: connection state change
        :return: None
        """
        self._async_terminal.notify(callback, when)

    def unsubscribe_on_connection_made(self, subscriber):
        """
        Remove subscriber from list of functions to call when connection is open/established
        :param subscriber: reference to function registered by method notify
        :return: None
        """
        self._async_terminal.unsubscribe_on_connection_made(subscriber)

    def unsubscribe_on_connection_lost(self, subscriber):
        """
        Remove subscriber from list of functions to call when connection is closed/disconnected
        :param subscriber: reference to function registered by method notify
        :return: None
        """
        self._async_terminal.unsubscribe_on_connection_lost(subscriber)

    @property
    def name(self):
        return self._async_terminal.name

    @name.setter
    def name(self, value):
        self._async_terminal.name = value

    @property
    def logger(self):
        return self._async_terminal.logger

    @logger.setter
    def logger(self, value):
        self._async_terminal.logger = value


class PtySubprocessProtocol(asyncio.SubprocessProtocol):
    def __init__(self, pty_fd=None):
        self.transport = None
        self.pty_fd = pty_fd
        self.complete = asyncio.Future()
        super(PtySubprocessProtocol, self).__init__()
        self.forward_data = None  # expecting function like:   lambda data: ...

    def connection_made(self, transport):
        self.transport = transport

    # --- API of asyncio.SubprocessProtocol

    def pipe_data_received(self, fd, data):
        # This function is not called (since pty's are being used)
        super(PtySubprocessProtocol, self).pipe_data_received(fd, data)

    def pipe_connection_lost(self, fd, exc):
        """Called when a file descriptor associated with the child process is
        closed.

        fd is the int file descriptor that was closed.
        """
        super(PtySubprocessProtocol, self).pipe_connection_lost(fd, exc)

    def process_exited(self):
        """Called when subprocess has exited."""
        return_code = self.transport.get_returncode()
        self.complete.set_result(return_code)
        self.on_process_exited(return_code)

    # --- callbacks called by asyncio.SubprocessProtocol API

    def on_process_exited(self, return_code):
        msg = f"Exited with return code: {return_code}"
        print(msg)

    # --- callbacks called by PtyFdProtocol

    def on_pty_open(self):
        # mark that now we can use self.pty_fd
        pass

    def on_pty_close(self, exc):
        pass

    def data_received(self, data, recv_time):
        # Data has line endings intact, but is bytes in Python 3
        if self.forward_data:
            self.forward_data(data)
        else:
            pass  # TODO: just log it

    # --- utility API
    def send(self, data):  # this is external-io, data should already be bytes
        os.write(self.pty_fd, data)


async def start_reading_pty(protocol, pty_fd):
    """
    Make asyncio to read file descriptor of Pty

    :param protocol: protocol of subprocess speaking via Pty
    :param pty_fd: file descriptor of Pty (dialog with subprocess goes that way)
    :return:
    """
    loop, its_new = thread_secure_get_event_loop()

    # Create Protocol classes
    class PtyFdProtocol(asyncio.Protocol):
        def connection_made(self, transport):
            if hasattr(protocol, 'on_pty_open'):
                protocol.on_pty_open()

        def data_received(self, data, recv_time):
            if hasattr(protocol, 'data_received'):
                protocol.data_received(data)

        def connection_lost(self, exc):
            if hasattr(protocol, 'on_pty_close'):
                protocol.on_pty_close(exc)

    # Add the pty's to the read loop
    # Also store the transport, protocol tuple for each call to
    # connect_read_pipe, to prevent the destruction of the protocol
    # class instance, otherwise no data is received.
    fd_transport, fd_protocol = await loop.connect_read_pipe(PtyFdProtocol, os.fdopen(pty_fd, 'rb', 0))
    protocol.pty_fd_transport = fd_transport
    protocol.pty_fd_protocol = fd_protocol


def open_terminal(dimensions):
    """
    Open pseudo-Terminal and configure it's dimensions

    :param dimensions: terminal dimensions (rows, columns)
    :return: (master, slave) file descriptors of Pty
    """
    master, slave = openpty_with_retry()
    _setwinsize(master, dimensions[0], dimensions[1])  # without this you get newline after each character
    _setwinsize(slave, dimensions[0], dimensions[1])
    return master, slave


def _setwinsize(fd, rows, cols):
    # Some very old platforms have a bug that causes the value for
    # termios.TIOCSWINSZ to be truncated. There was a hack here to work
    # around this, but it caused problems with newer platforms so has been
    # removed. For details see https://github.com/pexpect/pexpect/issues/39
    TIOCSWINSZ = getattr(termios, 'TIOCSWINSZ', -2146929561)
    # Note, assume ws_xpixel and ws_ypixel are zero.
    s = struct.pack('HHHH', rows, cols, 0, 0)
    fcntl.ioctl(fd, TIOCSWINSZ, s)


async def start_subprocess_in_terminal(protocol_class, cmd=None, cwd=None, env=None, dimensions=(100, 300)):
    """
    Start subprocess that will run cmd inside terminal.

    Some commands run differently when they detect "I'm running at terminal"
    (stdin/stdout/stderr are bound to terminal device)
    They assume human interaction so, for example they display "Password:" prompt.

    :param protocol_class:
    :param cmd: command to be run at terminal
    :param cwd: working directory when to start that command
    :param env: environment for command
    :param dimensions: terminal dimensions (rows, columns)
    :return:
    """
    loop, its_new = thread_secure_get_event_loop()
    # Create the PTY's
    # slave is used by cmd(bash) running in subprocess
    # master is used in client code to read/write into subprocess
    # moreover, inside subprocess we redirect stderr into stdout
    master, slave = open_terminal(dimensions)

    def protocol_factory():
        return protocol_class(master)

    # bash requires stdin and preexec_fn as follows
    # otherwise we get error like:
    #   bash: cannot set terminal process group (10790): Inappropriate ioctl for device
    #   bash: no job control in this shell

    # Start the subprocess (without shell since our cmd is shell - bash as default)
    libc = ctypes.CDLL('libc.so.6')

    transport, protocol = await loop.subprocess_exec(protocol_factory, *cmd, cwd=cwd, env=env,
                                                     stdin=slave, stdout=slave, stderr=slave,
                                                     close_fds=False, preexec_fn=libc.setsid)
    # Close our copy of slave,
    # the child's copy of the slave remain open until it terminates
    os.close(slave)

    await start_reading_pty(protocol=protocol, pty_fd=master)

    # Return the protocol and transport
    return transport, protocol


async def terminal_io_test():
    from moler.threaded_moler_connection import ThreadedMolerConnection

    received_data = []

    moler_conn = ThreadedMolerConnection(encoder=lambda data: data.encode("utf-8"),
                                         decoder=lambda data: data.decode("utf-8"))
    terminal = AsyncioTerminal(moler_connection=moler_conn)
    cmds = ['pwd', 'ssh demo@test.rebex.net', 'password', 'ls\r', 'exit\r']
    cmd_idx = [0]

    def data_observer(data):
        print(data)
        received_data.append(data)
        print(received_data)

        if cmd_idx[0] < len(cmds):
            cmd2send = cmds[cmd_idx[0]]
            if (cmd2send == 'password') and ('Password' not in data):
                return
            moler_conn.send(data=f"{cmd2send}\n")
            cmd_idx[0] += 1

    moler_conn.subscribe(data_observer, None)

    await terminal.open()
    await asyncio.sleep(10)
    await terminal.close()
    print("end of test")


async def run_command(cmd, cwd):

    def create_protocol(pty_fd):
        return PtySubprocessProtocol(pty_fd=pty_fd)

    transport, protocol = await start_subprocess_in_terminal(protocol_class=create_protocol, cmd=cmd, cwd=cwd)
    returncode = await protocol.complete
    return returncode


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    loop.run_until_complete(terminal_io_test())
    loop.close()
    print("ls done")
