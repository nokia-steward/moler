# -*- coding: utf-8 -*-
"""
Connections related configuration
"""

__author__ = 'Grzegorz Latuszek, Michal Ernst, Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, michal.ernst@nokia.com, marcin.usielski@nokia.com'

import platform
from moler.exceptions import MolerException

default_variant = {}
named_connections = {}


def set_default_variant(io_type, variant):
    """Set variant to use as default when requesting 'io_type' connection"""
    default_variant[io_type] = variant


def define_connection(name, io_type, **constructor_kwargs):
    """
    Assign name to connection specification.

    You should provide name that is meaningful in context of your application.
    Let's say you have 3 servers hosting HTTP under 10.20.30.41 .. 43
    Then you may name/define your connections like::

        www_svr1  io_type=tcp, host=10.20.30.41, port=80
        www_svr2  io_type=tcp, host=10.20.30.42, port=80
        www_svr3  io_type=tcp, host=10.20.30.43, port=80

    Thanks to such naming you could establish connection to server like::

        svr1_conn = get_connection(name="www_svr_1")
        svr1_conn.open()
    """
    named_connections[name] = (io_type, constructor_kwargs)


def clear():
    """Cleanup configuration related to connections"""
    default_variant.clear()
    named_connections.clear()


def set_defaults():
    """Set defaults for connections configuration"""
    set_default_variant(io_type="terminal", variant="threaded")
    set_default_variant(io_type="sshshell", variant="threaded")


supported_unix_systems = ['Linux', "FreeBSD", "Darwin", "SunOS"]
supported_windows_systems = ['Windows']
supported_systems = supported_unix_systems + supported_windows_systems


def _running_on_supported_unix():
    return platform.system() in supported_unix_systems


def _running_on_supported_windows():
    return platform.system() in supported_windows_systems


def register_builtin_connections(connection_factory, moler_conn_class):
    _register_builtin_connections(connection_factory, moler_conn_class)  # unix & windows connections
    _register_python3_builtin_connections(connection_factory, moler_conn_class)

    if _running_on_supported_unix():
        _register_builtin_unix_connections(connection_factory, moler_conn_class)  # unix-only connections
        _register_builtin_py3_unix_connections(connection_factory, moler_conn_class)
    elif _running_on_supported_windows():
        pass  # placeholder for windows-only connections
    else:
        err_msg = f"Unsupported system {platform.system()} detected! Supported systems: {supported_systems}"
        raise MolerException(err_msg)


def mlr_conn_no_encoding(moler_conn_class, name):
    return moler_conn_class(name=name)


def mlr_conn_no_encoding_partial_clean_vt100(moler_conn_class, name):
    """Cleans some VT100 control-codes"""
    from moler.helpers import remove_text_formatting_codes
    from moler.helpers import remove_fill_spaces_right_codes
    from moler.helpers import remove_cursor_visibility_codes
    from moler.helpers import remove_window_title_codes
    from moler.helpers import remove_osc_codes
    from moler.helpers import remove_overwritten_left_write

    def vt100_cleaner(data):
        decoded = remove_overwritten_left_write(multiline=data)
        decoded = remove_text_formatting_codes(multiline=decoded)
        decoded = remove_fill_spaces_right_codes(multiline=decoded)
        decoded = remove_cursor_visibility_codes(multiline=decoded)
        decoded = remove_window_title_codes(multiline=decoded)
        decoded = remove_osc_codes(multiline=decoded)
        return decoded

    return moler_conn_class(name=name, decoder=vt100_cleaner)


def mlr_conn_utf8_with_clean_vt100(moler_conn_class, name):
    from moler.helpers import remove_all_known_special_chars

    def utf8decoder_with_vt100_cleaner(data):
        decoded = data.decode("utf-8")
        decoded = remove_all_known_special_chars(decoded)
        return decoded

    return moler_conn_class(name=name,
                            encoder=lambda data: data.encode("utf-8"),
                            decoder=utf8decoder_with_vt100_cleaner)


def mlr_conn_utf8(moler_conn_class, name):
    return moler_conn_class(encoder=lambda data: data.encode("utf-8"),
                            decoder=lambda data: data.decode("utf-8"),
                            name=name)


def _register_builtin_connections(connection_factory, moler_conn_class):
    from moler.io.raw.memory import ThreadedFifoBuffer
    from moler.io.raw.tcp import ThreadedTcp
    from moler.io.raw.sshshell import ThreadedSshShell

    def mem_thd_conn(name=None, echo=True, **kwargs):  # kwargs to pass  logger_name
        mlr_conn = mlr_conn_utf8(moler_conn_class, name=name)
        io_conn = ThreadedFifoBuffer(moler_connection=mlr_conn,
                                     echo=echo, name=name, *kwargs)
        return io_conn

    def tcp_thd_conn(port, host='localhost', name=None, **kwargs):  # kwargs to pass  receive_buffer_size and logger
        mlr_conn = mlr_conn_utf8(moler_conn_class, name=name)
        io_conn = ThreadedTcp(moler_connection=mlr_conn,
                              port=port, host=host, **kwargs)  # TODO: add name
        return io_conn

    def sshshell_thd_conn(host=None, port=None, username=None, login=None, password=None, name=None,
                          reuse_ssh_of_shell=None, **kwargs):
        mlr_conn = mlr_conn_utf8_with_clean_vt100(moler_conn_class, name=name)
        if reuse_ssh_of_shell:
            if not ((host is None) and (port is None) and (username is None) and (login is None) and (password is None)):
                incorrect_params = "host/port/username/login/password"
                when = "building sshshell reusing ssh of other sshshell"
                err_msg = f"Don't use {incorrect_params} when {when}"
                raise MolerException(err_msg)
            io_conn = ThreadedSshShell.from_sshshell(moler_connection=mlr_conn,  # TODO: add name
                                                     sshshell=reuse_ssh_of_shell,
                                                     **kwargs)  # logger_name
        else:
            if port is None:
                port = 22
            io_conn = ThreadedSshShell(moler_connection=mlr_conn,  # TODO: add name
                                       host=host, port=port,
                                       username=username, login=login, password=password,
                                       **kwargs)  # receive_buffer_size, logger_name, other login credentials
        return io_conn

    # TODO: unify passing logger to io_conn (logger/logger_name - see above comments)
    connection_factory.register_construction(io_type="memory",
                                             variant="threaded",
                                             constructor=mem_thd_conn)
    connection_factory.register_construction(io_type="tcp",
                                             variant="threaded",
                                             constructor=tcp_thd_conn)
    connection_factory.register_construction(io_type="sshshell",
                                             variant="threaded",
                                             constructor=sshshell_thd_conn)


def _register_python3_builtin_connections(connection_factory, moler_conn_class):
    from moler.io.asyncio.tcp import AsyncioTcp, AsyncioInThreadTcp

    def tcp_asyncio_conn(port, host='localhost', name=None, **kwargs):  # kwargs to pass  receive_buffer_size and logger
        mlr_conn = mlr_conn_utf8(moler_conn_class, name=name)
        io_conn = AsyncioTcp(moler_connection=mlr_conn,
                             port=port, host=host, **kwargs)  # TODO: add name
        return io_conn

    def tcp_asyncio_in_thrd_conn(port, host='localhost', name=None, **kwargs):  # kwargs to pass  receive_buffer_size and logger
        mlr_conn = mlr_conn_utf8(moler_conn_class, name=name)
        io_conn = AsyncioInThreadTcp(moler_connection=mlr_conn,
                                     port=port, host=host, **kwargs)  # TODO: add name
        return io_conn

    # TODO: unify passing logger to io_conn (logger/logger_name - see above comments)
    connection_factory.register_construction(io_type="tcp",
                                             variant="asyncio",
                                             constructor=tcp_asyncio_conn)
    connection_factory.register_construction(io_type="tcp",
                                             variant="asyncio-in-thread",
                                             constructor=tcp_asyncio_in_thrd_conn)


def _register_builtin_unix_connections(connection_factory, moler_conn_class):
    from moler.io.raw.terminal import ThreadedTerminal
    from moler.io.raw.terminal_no_fork import ThreadedTerminalNoFork

    def terminal_thd_conn_mt(name=None):
        # ThreadedTerminal works on unicode so moler_connection must do no encoding
        # mlr_conn = mlr_conn_no_encoding(moler_conn_class, name=name)
        mlr_conn = mlr_conn_no_encoding_partial_clean_vt100(moler_conn_class, name=name)
        io_conn = ThreadedTerminal(moler_connection=mlr_conn)  # TODO: add name, logger
        return io_conn

    def terminal_thd_conn_st(name=None):
        # ThreadedTerminal works on unicode so moler_connection must do no encoding
        # mlr_conn = mlr_conn_no_encoding(moler_conn_class, name=name)
        from moler.moler_connection_for_single_thread_runner import MolerConnectionForSingleThreadRunner
        mlr_conn = mlr_conn_no_encoding_partial_clean_vt100(MolerConnectionForSingleThreadRunner, name=name)
        io_conn = ThreadedTerminal(moler_connection=mlr_conn)  # TODO: add name, logger
        return io_conn

    def terminal_nofork_thd_conn_mt(name=None):
        # ThreadedTerminal works on unicode so moler_connection must do no encoding
        # mlr_conn = mlr_conn_no_encoding(moler_conn_class, name=name)
        mlr_conn = mlr_conn_no_encoding_partial_clean_vt100(moler_conn_class, name=name)
        io_conn = ThreadedTerminalNoFork(moler_connection=mlr_conn)  # TODO: add name, logger
        return io_conn

    def terminal_nofork_thd_conn_st(name=None):
        # ThreadedTerminal works on unicode so moler_connection must do no encoding
        # mlr_conn = mlr_conn_no_encoding(moler_conn_class, name=name)
        from moler.moler_connection_for_single_thread_runner import MolerConnectionForSingleThreadRunner
        mlr_conn = mlr_conn_no_encoding_partial_clean_vt100(MolerConnectionForSingleThreadRunner, name=name)
        io_conn = ThreadedTerminalNoFork(moler_connection=mlr_conn)  # TODO: add name, logger
        return io_conn

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal_fork",
                                             variant="threaded",
                                             constructor=terminal_thd_conn_mt)

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal_fork",
                                             variant="multi-threaded",
                                             constructor=terminal_thd_conn_mt)

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal_fork",
                                             variant="single-threaded",
                                             constructor=terminal_thd_conn_st)

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal",
                                             variant="threaded",
                                             constructor=terminal_nofork_thd_conn_mt)

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal",
                                             variant="multi-threaded",
                                             constructor=terminal_nofork_thd_conn_mt)

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal",
                                             variant="single-threaded",
                                             constructor=terminal_nofork_thd_conn_st)

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal_no_fork",
                                             variant="threaded",
                                             constructor=terminal_nofork_thd_conn_mt)

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal_no_fork",
                                             variant="multi-threaded",
                                             constructor=terminal_nofork_thd_conn_mt)

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal_no_fork",
                                             variant="single-threaded",
                                             constructor=terminal_nofork_thd_conn_st)


def _register_builtin_py3_unix_connections(connection_factory, moler_conn_class):
    from moler.io.asyncio.terminal import AsyncioTerminal, AsyncioInThreadTerminal

    def terminal_asyncio_conn(name=None):
        mlr_conn = mlr_conn_utf8(moler_conn_class, name=name)
        io_conn = AsyncioTerminal(moler_connection=mlr_conn)  # TODO: add name, logger
        return io_conn

    def terminal_asyncio_in_thrd_conn(name=None):
        mlr_conn = mlr_conn_utf8(moler_conn_class, name=name)
        io_conn = AsyncioInThreadTerminal(moler_connection=mlr_conn)  # TODO: add name, logger
        return io_conn

    # TODO: unify passing logger to io_conn (logger/logger_name)
    connection_factory.register_construction(io_type="terminal",
                                             variant="asyncio",
                                             constructor=terminal_asyncio_conn)
    connection_factory.register_construction(io_type="terminal",
                                             variant="asyncio-in-thread",
                                             constructor=terminal_asyncio_in_thrd_conn)
