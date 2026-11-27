# -*- coding: utf-8 -*-
"""
Testing serial 2 stdin/stdout proxy

"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2020-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import importlib
import time
import serial

import pytest
from unittest import mock


# -------------- IOSerial


def test_constructing_ioserial_doesnt_open_serial_connection():
    from moler.util import moler_serial_proxy

    proxy = moler_serial_proxy.IOSerial(port="COM5")
    assert proxy._serial_connection is None


def test_opening_ioserial_correctly_constructs_serial_connection():
    from moler.util import moler_serial_proxy
    with mock.patch("moler.util.moler_serial_proxy.serial.Serial") as serial_conn:
        io = moler_serial_proxy.IOSerial(port="COM5")
        io.open()
    serial_conn.assert_called_once_with(port="COM5",
                                        baudrate=115200,
                                        stopbits=serial.STOPBITS_ONE,
                                        parity=serial.PARITY_NONE,
                                        timeout=2,
                                        xonxoff=1)


def test_closing_ioserial_correctly_closes_serial_connection(serial_connection_of_ioserial):
    from moler.util import moler_serial_proxy

    io = moler_serial_proxy.IOSerial(port="COM5")
    io.open()
    io.close()
    serial_connection_of_ioserial.close.assert_called_once_with()


def test_can_use_ioserial_as_context_manager(serial_connection_of_ioserial):
    from moler.util.moler_serial_proxy import IOSerial
    with mock.patch.object(IOSerial, "open") as io_open:
        with mock.patch.object(IOSerial, "close") as io_close:

            with IOSerial(port="COM5"):  # IOSerial may work as context manager
                io_open.assert_called_once_with()
            io_close.assert_called_once_with()

    with mock.patch.object(IOSerial, "close") as proxy_close:

        with IOSerial(port="COM5").open():  # and IOSerial.open() may work same
            pass
        proxy_close.assert_called_once_with()


def test_ioserial_can_send_data_towards_serial_connection(serial_connection_of_ioserial):
    from moler.util.moler_serial_proxy import IOSerial

    with IOSerial(port="COM5") as io:
        io.send(cmd=b'AT')  # data is sent as-is without any line ending added

    serial_connection_of_ioserial.write.assert_called_once_with(b'AT')
    serial_connection_of_ioserial.flush.assert_called_once_with()


def test_ioserial_can_send_data_with_line_ending_towards_serial_connection(serial_connection_of_ioserial):
    from moler.util.moler_serial_proxy import IOSerial

    with IOSerial(port="COM5") as io:
        io.send(cmd=b'AT\r\n')  # if you want line ending - add it

    serial_connection_of_ioserial.write.assert_called_once_with(b'AT\r\n')
    serial_connection_of_ioserial.flush.assert_called_once_with()


# def test_ioserial_can_read_data_from_serial_connection(serial_connection_of_ioserial):
#     from moler.util.moler_serial_proxy import IOSerial
#
#     serial_connection_of_ioserial.read.return_value = "AT\r\nOK\r\n"
#
#     with IOSerial(port="COM5") as proxy:
#         response = proxy.read()  #TODO: refactor - it comes from reading thread
#
#     assert response == "AT\r\nOK\r\n"


# -------------- AtConsoleProxy


def test_constructing_proxy_creates_underlying_ioserial():
    from moler.util import moler_serial_proxy
    with mock.patch("moler.util.moler_serial_proxy.IOSerial.__init__", return_value=None) as serial_io:
        moler_serial_proxy.AtConsoleProxy(port="COM5")
    serial_io.assert_called_once_with(port="COM5", baudrate=115200, stopbits=1, parity='N', timeout=2, xonxoff=1)


def test_opening_proxy_opens_underlying_ioserial():
    from moler.util import moler_serial_proxy

    with mock.patch("moler.util.moler_serial_proxy.IOSerial.open") as serial_io_open:
        with mock.patch("moler.util.moler_serial_proxy.AtConsoleProxy._apply_initial_configuration"):
            mocked_thread = mock.MagicMock()
            mocked_thread.connect = mock.MagicMock()
            mocked_thread.connect.return_value = (None, None)
            with mock.patch("moler.util.moler_serial_proxy.serial.threaded.ReaderThread",
                            return_value=mocked_thread):

                proxy = moler_serial_proxy.AtConsoleProxy(port="COM5")
                proxy.open()
    serial_io_open.assert_called_once_with()


def test_closing_proxy_closes_underlying_ioserial(serial_connection_of_ioserial):
    from moler.util import moler_serial_proxy
    with mock.patch("moler.util.moler_serial_proxy.AtConsoleProxy._apply_initial_configuration"):

        proxy = moler_serial_proxy.AtConsoleProxy(port="COM5")
        proxy.open()
        proxy.close()
    serial_connection_of_ioserial.close.assert_called_once_with()


def test_can_use_proxy_as_context_manager(serial_connection_of_ioserial):
    from moler.util.moler_serial_proxy import AtConsoleProxy
    with mock.patch("moler.util.moler_serial_proxy.AtConsoleProxy._apply_initial_configuration"):

        with mock.patch.object(AtConsoleProxy, "open") as proxy_open:
            with AtConsoleProxy(port="COM5"):  # AtConsoleProxy may work as context manager
                proxy_open.assert_called_once_with()

        mocked_thread = mock.MagicMock()
        mocked_thread.connect = mock.MagicMock()
        mocked_thread.connect.return_value = (None, None)
        with mock.patch("moler.util.moler_serial_proxy.serial.threaded.ReaderThread",
                        return_value=mocked_thread):
            with mock.patch.object(AtConsoleProxy, "close") as proxy_close:
                with AtConsoleProxy(port="COM5"):  # AtConsoleProxy may work as context manager
                    proxy_open.assert_called_once_with()
                proxy_close.assert_called_once_with()

            with mock.patch.object(AtConsoleProxy, "close") as proxy_close:
                with AtConsoleProxy(port="COM5").open():  # and AtConsoleProxy.open() may work same
                    pass
                proxy_close.assert_called_once_with()


def test_sending_over_proxy_sends_over_underlying_ioserial(serial_connection_of_ioserial):
    from moler.util.moler_serial_proxy import AtConsoleProxy

    with mock.patch("moler.util.moler_serial_proxy.AtConsoleProxy._apply_initial_configuration"):
        with AtConsoleProxy(port="COM5") as proxy:
            proxy.send(cmd='AT')

    serial_connection_of_ioserial.write.assert_called_once_with(b'AT\r\n')


def test_opening_proxy_activates_at_echo_and_detailed_error_status(serial_connection_of_ioserial):
    from moler.util import moler_serial_proxy

    with mock.patch("moler.util.moler_serial_proxy.AtToStdout.await_response_event", return_value=True):
        io = moler_serial_proxy.AtConsoleProxy(port="COM5")
        with io.open():
            pass
        assert serial_connection_of_ioserial.write.mock_calls == [mock.call(b'ATE1\r\n'),
                                                                  mock.call(b'AT+CMEE=1\r\n'),
                                                                  mock.call(b'AT+CMEE=2\r\n'),
                                                                  mock.call(b'ATE0\r\n'),]


# def test_reading_proxy_reads_data_from_underlying_ioserial(serial_connection_of_ioserial):
#     from moler.util.moler_serial_proxy import AtConsoleProxy
#     with mock.patch.object(serial_connection_of_ioserial, "read") as serial_io_read:
#         serial_io_read.return_value = "AT\r\nOK\r\n"
#
#         with AtConsoleProxy(port="COM5") as proxy:
#             response = proxy.read()  # TODO: need reworking - now uses reading thread
#
#         assert response == ['AT', 'OK']


# ----------------------------------- resources

@pytest.fixture
def serial_connection_of_ioserial():
    from serial import Serial
    with mock.patch("moler.util.moler_serial_proxy.serial.Serial") as serial_conn:  # mocking class
        # serial_conn.return_value = mock.Mock(spec=Serial)  # return value from Serial() is instance of Serial
        serial_conn.return_value = mock.Mock()  # return value from Serial() is instance of Serial
        serial_conn.return_value.is_open = True
        serial_conn.return_value.read = lambda s: ""
        serial_conn.return_value.in_waiting = 0
        serial_conn.return_value.close = mock.Mock()
        serial_conn.return_value.write = mock.Mock()
        yield serial_conn.return_value  # returning instance that will be used by calling class
