# -*- coding: utf-8 -*-
"""
Testing factory responsible for returning "requested" connection
"""

__author__ = 'Grzegorz Latuszek, Michal Ernst'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, michal.ernst@nokia.com'

import pytest
from unittest import mock


def test_missing_constructor_raises_KeyError():
    from moler.connection_factory import ConnectionFactory
    with pytest.raises(KeyError) as err:
        ConnectionFactory.get_connection(io_type='memory', variant='superquick')
    assert "No constructor registered for [('memory', 'superquick')] connection" in str(err.value)


def test_user_is_informed_about_terminal_io_unavailable_on_windows():
    from moler.connection_factory import get_connection
    with mock.patch("moler.connection_factory.platform.system", return_value='Windows'):
        with pytest.raises(AttributeError) as err:
            get_connection(io_type='terminal', variant='threaded')
    assert "No 'terminal' connection available on Windows (try using 'sshshell' connection instead)" in str(err.value)


def test_factory_has_buildin_constructors_active_by_default():
    from moler.connection_factory import get_connection

    conn = get_connection(io_type='memory', variant='threaded')
    assert conn.__module__ == 'moler.io.raw.memory'
    assert conn.__class__.__name__ == 'ThreadedFifoBuffer'

    conn = get_connection(io_type='tcp', variant='threaded', host='localhost', port=2345)
    assert conn.__module__ == 'moler.io.raw.tcp'
    assert conn.__class__.__name__ == 'ThreadedTcp'

    conn = get_connection(io_type='sshshell', variant='threaded',
                          host='localhost', port=2345, login='vagrant', password='vagrant')
    assert conn.__module__ == 'moler.io.raw.sshshell'
    assert conn.__class__.__name__ == 'ThreadedSshShell'


def test_correct_call_of_sshshell_construction_based_on_existing_sshshell_connection():
    from moler.connection_factory import get_connection
    from moler.exceptions import MolerException

    existing_conn = get_connection(io_type='sshshell', variant='threaded',
                          host='localhost', port=2345, login='vagrant', password='vagrant')
    with pytest.raises(MolerException) as err:
        get_connection(io_type='sshshell', variant='threaded',
                       reuse_ssh_of_shell=existing_conn,
                       port=2345, login='vagrant', password='vagrant')
    assert "Don't use host/port/username/login/password when building sshshell reusing ssh of other sshshell" in str(err.value)
    conn_reusing_ssh_transport = get_connection(io_type='sshshell', variant='threaded',
                                                reuse_ssh_of_shell=existing_conn)
    assert conn_reusing_ssh_transport.__class__.__name__ == 'ThreadedSshShell'


def test_returned_connections_have_moler_integrated_connection(builtin_variant,
                                                               builtin_io_type_example):
    from moler.connection_factory import get_connection

    io_type, kwargs = builtin_io_type_example
    conn = get_connection(io_type=io_type, variant=builtin_variant, **kwargs)
    assert hasattr(conn, 'moler_connection')
    assert conn.moler_connection.how2send != conn.moler_connection._unknown_send


def test_registered_constructor_must_be_callable():
    from moler.connection_factory import ConnectionFactory
    with pytest.raises(ValueError) as err:
        ConnectionFactory.register_construction(io_type='memory',
                                                variant='superquick',
                                                constructor=[1, 2])
    assert "constructor must be callable not" in str(err.value)


def test_can_plugin_alternative_connection_instead_of_builtin_one(builtin_connection_factories):
    from moler.connection_factory import ConnectionFactory, get_connection
    from moler.threaded_moler_connection import ThreadedMolerConnection

    class DummyTcpConnection(object):
        def __init__(self, host, port):
            self.moler_connection = ThreadedMolerConnection(how2send=self.send)

        def send(self, data):
            pass

    ConnectionFactory.register_construction(io_type='tcp', variant='threaded',
                                            constructor=DummyTcpConnection)
    conn = get_connection(io_type='tcp', variant='threaded',
                          host='localhost', port=2345)
    assert conn.__class__.__name__ == 'DummyTcpConnection'


# --------------------------- resources ---------------------------


@pytest.fixture(params=['threaded'])
def builtin_variant(request):
    return request.param


@pytest.fixture(params=['memory', 'tcp'])
def builtin_io_type_example(request):
    kwargs = {}
    if request.param == 'tcp':
        kwargs = {'host': 'localhost', 'port': 2345}
    return request.param, kwargs


@pytest.fixture
def builtin_connection_factories():
    import moler.connection  # installs builtin ones
    import moler.config.connections as connection_cfg
    yield
    # restore since tests may overwrite builtins
    connection_cfg.register_builtin_connections(moler.connection_factory.ConnectionFactory,
                                                moler.threaded_moler_connection.ThreadedMolerConnection)
