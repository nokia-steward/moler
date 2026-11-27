# -*- coding: utf-8 -*-
"""
Testing ExitSerialProxy command.
"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2020-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import pytest
from unittest import mock


# -----------------------------------------------------

def test_command_prepares_correct_commandstring_to_send(buffer_connection):
    from moler.cmd.at import exit_serial_proxy

    exit = exit_serial_proxy.ExitSerialProxy(connection=buffer_connection.moler_connection,
                                             **exit_serial_proxy.COMMAND_KWARGS)
    assert exit.command_string == 'exit_serial_proxy'


def test_command_exits_python_interactive_shell(buffer_connection):
    from moler.cmd.at import exit_serial_proxy
    from moler.exceptions import ParsingDone

    exit = exit_serial_proxy.ExitSerialProxy(connection=buffer_connection.moler_connection,
                                             **exit_serial_proxy.COMMAND_KWARGS)
    with pytest.raises(ParsingDone):
        with mock.patch.object(buffer_connection.moler_connection, "send") as connection_send:
            exit._exit_from_python_shell(line=">>> ")
    connection_send.assert_called_once_with("exit()\n")


def test_calling_cmd_exit_serial_proxy_returns_expected_result(buffer_connection):
    from moler.cmd.at import exit_serial_proxy
    exit = exit_serial_proxy.ExitSerialProxy(connection=buffer_connection.moler_connection,
                                             **exit_serial_proxy.COMMAND_KWARGS)
    buffer_connection.remote_inject_response([exit_serial_proxy.COMMAND_OUTPUT])
    result = exit()
    assert result == exit_serial_proxy.COMMAND_RESULT


def test_command_processing_doesnt_stop_on_python_prompt(buffer_connection):
    from moler.cmd.at import exit_serial_proxy
    collected_lines = []

    def line_collector(self, line, is_full_line):
        collected_lines.append(line)
        if "user@PC10" in line:
            self.set_result(self.current_ret)

    exit = exit_serial_proxy.ExitSerialProxy(connection=buffer_connection.moler_connection,
                                             prompt=r">>> |user@PC10 ~")
    with mock.patch("moler.cmd.commandtextualgeneric.CommandTextualGeneric.on_new_line", line_collector):
        buffer_connection.remote_inject_response([exit_serial_proxy.COMMAND_OUTPUT])
        result = exit()
    assert "PC10  serial port COM11 closed" in collected_lines
    assert ">>> exit()" not in collected_lines
    assert "user@PC10 ~" in collected_lines
