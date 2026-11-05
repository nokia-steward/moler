# -*- coding: utf-8 -*-

__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'


import pytest


def test_io_connection_unsubscribe_removes_subscribers(io_connection):
    def on_made(connection):
        pass

    def on_lost(connection):
        pass

    io_connection.notify(callback=on_made, when="connection_made")
    io_connection.notify(callback=on_lost, when="connection_lost")

    io_connection.unsubscribe_on_connection_made(subscriber=on_made)
    io_connection.unsubscribe_on_connection_lost(subscriber=on_lost)

    assert on_made not in io_connection._connect_subscribers
    assert on_lost not in io_connection._disconnect_subscribers


def test_io_connection_unsubscribe_of_not_subscribed_callback_is_ignored(io_connection):
    def callback(connection):
        pass

    io_connection.unsubscribe_on_connection_made(subscriber=callback)
    io_connection.unsubscribe_on_connection_lost(subscriber=callback)

    assert [] == io_connection._connect_subscribers
    assert [] == io_connection._disconnect_subscribers


def test_asyncio_in_thread_terminal_unsubscribes_from_inner_terminal():
    from moler.io.asyncio.terminal import AsyncioInThreadTerminal
    from moler.threaded_moler_connection import ThreadedMolerConnection

    terminal = AsyncioInThreadTerminal(moler_connection=ThreadedMolerConnection(name="asyncio_unsubscribe"))
    inner_terminal = terminal._async_terminal

    def on_made(connection):
        pass

    def on_lost(connection):
        pass

    terminal.notify(callback=on_made, when="connection_made")
    terminal.notify(callback=on_lost, when="connection_lost")
    assert on_made in inner_terminal._connect_subscribers
    assert on_lost in inner_terminal._disconnect_subscribers

    terminal.unsubscribe_on_connection_made(subscriber=on_made)
    terminal.unsubscribe_on_connection_lost(subscriber=on_lost)

    assert on_made not in inner_terminal._connect_subscribers
    assert on_lost not in inner_terminal._disconnect_subscribers


# --------------------------- resources ---------------------------


@pytest.fixture
def io_connection():
    from moler.io.raw.memory import ThreadedFifoBuffer
    from moler.threaded_moler_connection import ThreadedMolerConnection

    return ThreadedFifoBuffer(moler_connection=ThreadedMolerConnection(name="io_unsubscribe"))
