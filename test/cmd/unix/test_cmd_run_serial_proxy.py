# -*- coding: utf-8 -*-
"""
RunSerialProxy command test module.
"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2020-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import pytest
from unittest import mock
import time
from moler.exceptions import CommandFailure
from moler.cmd.unix.run_serial_proxy import RunSerialProxy


def test_command_prepares_correct_commandstring_to_send(buffer_connection):
    cmd = RunSerialProxy(connection=buffer_connection.moler_connection, serial_devname="COM5")
    assert "python -i moler_serial_proxy.py COM5" == cmd.command_string


def test_calling_cmd_run_serial_proxy_returns_expected_result(buffer_connection):
    from moler.cmd.unix import run_serial_proxy
    run = run_serial_proxy.RunSerialProxy(connection=buffer_connection.moler_connection,
                                           **run_serial_proxy.COMMAND_KWARGS)
    buffer_connection.remote_inject_response([run_serial_proxy.COMMAND_OUTPUT])
    result = run()
    assert result == run_serial_proxy.COMMAND_RESULT


def test_command_quickly_fails_on_error_in_proxy(buffer_connection, command_output_from_failed_python_code):
    from moler.cmd.unix import run_serial_proxy
    run = run_serial_proxy.RunSerialProxy(connection=buffer_connection.moler_connection,
                                          prompt="image9|>>>", serial_devname="COM5")
    buffer_connection.remote_inject_response([command_output_from_failed_python_code])
    start_time = time.monotonic()
    with pytest.raises(CommandFailure):
        run()
    assert (time.monotonic() - start_time) < 0.8


def test_command_exits_python_interactive_shell(buffer_connection):
    from moler.cmd.unix import run_serial_proxy
    from moler.exceptions import ParsingDone

    run = run_serial_proxy.RunSerialProxy(connection=buffer_connection.moler_connection,
                                          serial_devname="COM5")
    with pytest.raises(ParsingDone):
        with mock.patch.object(buffer_connection.moler_connection, "send") as connection_send:
            run._exit_from_python_shell(line=">>> ")
    connection_send.assert_called_once_with("exit()\n")


failed_pycode = r"""python -i moler_serial_proxy.py COM5
starting COM5 proxy at image9 ...
Traceback (most recent call last):
  File "moler_serial_proxy.py", line 159, in <module>
    with AtConsoleProxy(port=options.serial_devname, verbose=options.verbose) as proxy:
  File "moler_serial_proxy.py", line 63, in __init__
    self._serial_io = IOSerial(port=port)
  File "moler_serial_proxy.py", line 17, in __init__
    self.timeout = timeout2
NameError: global name 'timeout2' is not defined
>>>"""

serial_dev_in_use = r"""python -i moler_serial_proxy.py COM5
user-lab0@10.83.179.159's password:
starting COM5 proxy at PC11 ...
PC11  opening serial port COM5
Traceback (most recent call last):
  File "moler_serial_proxy.py", line 159, in <module>
    with AtConsoleProxy(port=options.serial_devname, verbose=options.verbose) as proxy:
  File "moler_serial_proxy.py", line 85, in __enter__
    self.open()
  File "moler_serial_proxy.py", line 73, in open
    self._serial_io.open()
  File "moler_serial_proxy.py", line 33, in open
    xonxoff=self.xonxoff)
  File "C:\Python27\lib\site-packages\serial\serialwin32.py", line 31, in __init__
    super(Serial, self).__init__(*args, **kwargs)
  File "C:\Python27\lib\site-packages\serial\serialutil.py", line 240, in __init__
    self.open()
  File "C:\Python27\lib\site-packages\serial\serialwin32.py", line 62, in open
    raise SerialException("could not open port {!r}: {!r}".format(self.portstr, ctypes.WinError()))
serial.serialutil.SerialException: could not open port 'COM5': WindowsError(32, 'The process cannot access the file because it is being used by another process.')
>>>"""

no_proxy = r"""python -i moler_serial_proxy.py COM5
C:\Python27\python.exe: can't open file 'moler_serial_proxy.py': [Errno 2] No such file or directory
image9$"""


@pytest.fixture(params=['serial port in use', 'python code failure', 'no proxy on remote'])
def command_output_from_failed_python_code(request):
    if request.param == 'serial port in use':
        return serial_dev_in_use
    elif request.param == 'no proxy on remote':
        return no_proxy
    return failed_pycode
