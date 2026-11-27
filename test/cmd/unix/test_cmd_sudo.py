# -*- coding: utf-8 -*-
"""
Testing of sudo command.
"""

__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'

from moler.cmd.unix.sudo import Sudo
from moler.cmd.unix.pwd import Pwd
from moler.cmd.unix.cp import Cp
from moler.cmd.unix.su import Su
from moler.cmd.unix.whoami import Whoami
from moler.exceptions import CommandTimeout
from moler.exceptions import CommandFailure
import pytest
from unittest import mock
import time
import datetime


def test_sudo_with_parameter_i(buffer_connection):
    command_output = """sudo -i
root@host#"""
    buffer_connection.remote_inject_response([command_output])
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass",
                    sudo_params='-i', prompt="moler_bash#", expected_prompt="root@host.*#")
    assert "sudo -i" == cmd_sudo.command_string
    cmd_sudo()


def test_sudo_with_wrong_command_parameters(buffer_connection):
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass",
                    cmd_class_name="moler.cmd.unix.telnet.Telnet", cmd_params={"login": "login"})
    with pytest.raises(TypeError):
        cmd_sudo(timeout=0.3)


def test_calling_by_command_class(buffer_connection, command_output_and_expected_result):
    command_output, expected_result = command_output_and_expected_result
    buffer_connection.remote_inject_response([command_output])

    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass",
                    cmd_class_name="moler.cmd.unix.pwd.Pwd")
    assert "sudo pwd" == cmd_sudo.command_string
    result = cmd_sudo()
    assert "sudo pwd" == cmd_sudo.command_string
    assert result == expected_result


def test_calling_by_command_object_su(buffer_connection):
    command_output = """sudo su
root@host#"""
    buffer_connection.remote_inject_response([command_output])

    cmd_su = Su(connection=buffer_connection.moler_connection, expected_prompt="root@host.*#")
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, cmd_object=cmd_su, expected_prompt="root@host.*#")
    assert "sudo su" == cmd_sudo.command_string
    cmd_sudo()


def test_calling_by_command_object(buffer_connection, command_output_and_expected_result):
    command_output, expected_result = command_output_and_expected_result
    buffer_connection.remote_inject_response([command_output])

    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    assert "sudo pwd" == cmd_sudo.command_string
    result = cmd_sudo()
    assert result == expected_result


def test_calling_by_command_object_without_slicing(buffer_connection, command_output_and_expected_result):
    command_output, expected_result = command_output_and_expected_result
    buffer_connection.remote_inject_response([command_output])

    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    cmd_sudo._max_index_from_end = 0
    cmd_sudo._max_index_from_beginning = 0
    assert "sudo pwd" == cmd_sudo.command_string
    result = cmd_sudo()
    assert result == expected_result


def test_failing_calling_twice_the_same_command_object(buffer_connection, command_output_and_expected_result):
    command_output, expected_result = command_output_and_expected_result
    buffer_connection.remote_inject_response([command_output])

    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    result = cmd_sudo()
    assert result == expected_result
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    with pytest.raises(CommandFailure):
        cmd_sudo()


def test_failing_calling_twice_the_same_command_object_failed(buffer_connection):
    from moler.cmd.unix.rm import Rm
    rm_output_denied = """rm important_file.txt
rm: cannot remove 'protected.txt': Permission denied
moler_bash#"""

    buffer_connection.remote_inject_response([rm_output_denied])

    cmd_rm = Rm(connection=buffer_connection.moler_connection, file="important_file.txt")
    with pytest.raises(CommandFailure):
        cmd_rm()
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_rm)
    with pytest.raises(CommandFailure) as exc:
        cmd_sudo()
    assert "Not allowed to run again" in str(exc.value)

def test_failing_with_timeout(buffer_connection, command_output_and_expected_result_timeout):
    command_output = command_output_and_expected_result_timeout
    buffer_connection.remote_inject_response([command_output])
    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    with pytest.raises(CommandTimeout):
        cmd_sudo(timeout=0.1)


def test_can_use_timeout_of_embedded_command(buffer_connection, command_output_and_expected_result_timeout):
    command_output = command_output_and_expected_result_timeout
    buffer_connection.remote_inject_response([command_output])
    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_pwd.timeout = 0.2
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    cmd_sudo.terminating_timeout = 0  # no additional timeout for Ctrl-C..till..prompt (shutdown after cmd timeout)
    start_time = time.monotonic()
    with pytest.raises(CommandTimeout):
        cmd_sudo()
    duration = time.monotonic() - start_time
    assert duration >= 0.2
    assert duration < 0.5


def test_can_ignore_timeout_of_embedded_command_if_direct_timeout_provided(buffer_connection,
                                                                           command_output_and_expected_result_timeout):
    command_output = command_output_and_expected_result_timeout
    buffer_connection.remote_inject_response([command_output])
    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_pwd.timeout = 0.8
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    cmd_sudo.terminating_timeout = 0  # no additional sudo timeout for Ctrl-C..till..prompt (shutdown after cmd timeout)
    start_time = time.monotonic()
    with pytest.raises(CommandTimeout):
        cmd_sudo(timeout=0.5)
    duration = time.monotonic() - start_time
    assert duration >= 0.5
    assert duration < 0.8


def test_command_not_found(buffer_connection, command_output_command_not_found):
    command_output = command_output_command_not_found
    buffer_connection.remote_inject_response([command_output])
    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    with pytest.raises(CommandFailure):
        cmd_sudo()


def test_no_parameters(buffer_connection):
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass")
    with pytest.raises(CommandFailure):
        cmd_sudo()


def test_no_parameters_command_string(buffer_connection):
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass")
    command_string = None
    assert command_string is None
    with pytest.raises(CommandFailure):
        command_string = cmd_sudo.command_string
    assert command_string is None


def test_failing_with_embedded_command_fails(buffer_connection, command_output_cp_fails):
    command_output = command_output_cp_fails
    buffer_connection.remote_inject_response([command_output])
    cmd_cp = Cp(connection=buffer_connection.moler_connection, src="src.txt", dst="dst.txt", prompt="user@host:")
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_cp)
    with pytest.raises(CommandFailure):
        abc = cmd_sudo()
        # `print`("abc '{}'".format(abc))


def test_failing_with_bit_fails(buffer_connection, command_output_cp_bit_fails):
    command_output = command_output_cp_bit_fails
    buffer_connection.remote_inject_response([command_output])
    cmd_cp = Cp(connection=buffer_connection.moler_connection, src="src.txt", dst="dst.txt")
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_cp)
    with pytest.raises(CommandFailure):
        cmd_sudo()


def test_failing_with_no_command_created(buffer_connection, command_output_cp_fails):
    command_output = command_output_cp_fails
    buffer_connection.remote_inject_response([command_output])
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass",
                    cmd_class_name="no_existing_package.NoExistingClass")
    with pytest.raises(ImportError):
        cmd_sudo()


def test_failing_with_both_parameters(buffer_connection, command_output_cp_fails):
    command_output = command_output_cp_fails
    buffer_connection.remote_inject_response([command_output])
    cmd_cp = Cp(connection=buffer_connection.moler_connection, src="src.txt", dst="dst.txt")
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, cmd_class_name="moler.cmd.unix.cp.Cp",
                    cmd_object=cmd_cp, password="pass")
    with pytest.raises(CommandFailure):
        cmd_sudo(timeout=0.2)


def test_failing_with_wrong_password(buffer_connection, command_output_password_fails):
    command_output = command_output_password_fails
    buffer_connection.remote_inject_response([command_output])
    cmd = Whoami(connection=buffer_connection.moler_connection)
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, cmd_object=cmd, password="pass",
                    repeat_password=False)
    with pytest.raises(CommandFailure):
        cmd_sudo(timeout=0.2)
    assert cmd_sudo._command_output_started is False


def test_sudo_forwards_nonsudo_specific_connection_data_into_embedded_command(buffer_connection):
    command_output_chunks = ["user@client:~/moler$ sudo pwd",  # sudo specific - command echo
                             "\r\n",
                             "[sudo] password for user:",  # sudo specific - should not be forwarded
                             "\r\n",
                             "/home/user/moler",  # pwd first chunk
                             "\r\n",
                             "user@host:~/moler$"]
    buffer_connection.remote_inject_response(command_output_chunks)
    on_new_line_params = []
    original_on_new_line = Pwd.on_new_line

    def pwd_on_new_line(self, line, is_full_line):
        on_new_line_params.append((line, is_full_line))
        original_on_new_line(self, line, is_full_line)

    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd)
    with mock.patch.object(Pwd, "on_new_line", pwd_on_new_line):
        cmd_sudo()
    assert on_new_line_params == [("/home/user/moler", False),
                                  ("/home/user/moler", True),
                                  ("user@host:~/moler$", False)]


def test_wrong_password_repeat_password(buffer_connection):
    output1 = "sudo pwd\n"
    output2 = "[sudo] password for john: "
    output3 = "*****\n"
    output4 = "Sorry, try again.\n"
    output5 = "[sudo] password for john: "
    output6 = "*****\n"
    output7 = "/home/moler\n"
    output8 = "user@host:~/moler$"

    cmd_pwd = Pwd(connection=buffer_connection.moler_connection)
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection, password="pass", cmd_object=cmd_pwd,
                    repeat_password=True)
    cmd_sudo.start(timeout=4)
    time.sleep(0.1)
    buffer_connection.moler_connection.data_received(output1.encode("utf-8"), datetime.datetime.now())
    outputs = [output2, output3, output4, output5, output6, output7, output8]
    for output in outputs:
        buffer_connection.moler_connection.data_received(output.encode("utf-8"), datetime.datetime.now())
        time.sleep(0.1)
    cmd_sudo.await_done()


def test_set_prompt(buffer_connection):
    output1 = 'sudo ip netns exec NH123 bash -c "su - john"'
    output2 = "\n"
    output3 = "john@7-7-johncomp123:~$ "
    output4 = "\njohn@7-7-johncomp123:~$ \n"
    output5 = "export PS1=\"johnNamespace:\\W\\$\"\n"
    output6 = "johnNamespace:~$ \n"
    output7 = "\n"
    output8 = "johnNamespace:~$ "
    export_cmd = r'export PS1="johnNamespace:\W\$"'
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection,
                    sudo_params='ip netns exec NH123 bash -c \"su - john\"',
                    prompt=r'john@.*(\$|#|>)\s+', expected_prompt= r'^johnNamespace.*',
                    prompt_after_login=r'john@.*(\$|#|>)\s+',
                    set_prompt=export_cmd,
                    repeat_password=True)
    assert cmd_sudo.command_string == output1
    cmd_sudo.start(timeout=4)
    time.sleep(0.1)
    buffer_connection.moler_connection.data_received(output1.encode("utf-8"), datetime.datetime.now())
    buffer_connection.moler_connection.data_received("\n".encode("utf-8"), datetime.datetime.now())
    time.sleep(0.1)
    assert cmd_sudo._cmd_output_started is True
    assert export_cmd in cmd_sudo._commands_to_send_when_after_login_prompt
    outputs = [output2, output3, output4, output5, output6, output7, output8]
    for output in outputs:
        buffer_connection.moler_connection.data_received(output.encode("utf-8"), datetime.datetime.now())
        time.sleep(0.1)
    assert export_cmd not in cmd_sudo._commands_to_send_when_after_login_prompt
    cmd_sudo.await_done()
    assert export_cmd not in cmd_sudo._commands_to_send_when_after_login_prompt


def test_set_prompt_timeout(buffer_connection):
    output1 = 'sudo ip netns exec NH123 bash -c "su - john"'
    output2 = "\n"
    output3 = "john@7-7-johncomp123:~$ "
    output4 = "\njohn@7-7-johncomp123:~$ \n"
    output5 = "export PS1=\"johnNamespace:\\W\\$\"\n"
    export_cmd = r'export PS1="johnNamespace:\W\$"'
    cmd_sudo = Sudo(connection=buffer_connection.moler_connection,
                    sudo_params='ip netns exec NH123 bash -c \"su - john\"',
                    prompt=r'john@.*(\$|#|>)\s+', expected_prompt= r'^johnNamespace.*',
                    prompt_after_login=r'john@.*(\$|#|>)\s+',
                    set_prompt=export_cmd,
                    repeat_password=True)
    assert cmd_sudo.command_string == output1
    cmd_sudo.start(timeout=4)
    time.sleep(0.1)
    buffer_connection.moler_connection.data_received(output1.encode("utf-8"), datetime.datetime.now())
    buffer_connection.moler_connection.data_received("\n".encode("utf-8"), datetime.datetime.now())
    time.sleep(0.1)
    assert cmd_sudo._cmd_output_started is True
    assert export_cmd in cmd_sudo._commands_to_send_when_after_login_prompt
    outputs = [output2, output3, output4, output5]
    for output in outputs:
        buffer_connection.moler_connection.data_received(output.encode("utf-8"), datetime.datetime.now())
        time.sleep(0.1)
    assert export_cmd not in cmd_sudo._commands_to_send_when_after_login_prompt
    with pytest.raises(CommandTimeout):
        cmd_sudo.await_done(timeout=0.2)
    assert export_cmd not in cmd_sudo._commands_to_send_when_after_login_prompt


def test_set_prompt_do_not_check_echo(buffer_connection):
    output1 = 'sudo ip netns exec NH123 bash -c "su - john"'
    output2 = "\n"
    output3 = "john@7-7-johncomp123:~$ "
    output4 = "\njohn@7-7-johncomp123:~$ \n"
    output5 = "johnNamespace:~$ "

    cmd_sudo = Sudo(connection=buffer_connection.moler_connection,
                    sudo_params='ip netns exec NH123 bash -c \"su - john\"',
                    prompt=r'john@.*(\$|#|>)\s+', expected_prompt= r'^johnNamespace.*',
                    prompt_after_login=r'john@.*(\$|#|>)\s+',
                    set_prompt=r'export PS1="johnNamespace:\W\$"',
                    repeat_password=True)
    cmd_sudo.check_echo_settings = False
    assert cmd_sudo.command_string == output1
    cmd_sudo.start(timeout=4)
    time.sleep(0.1)
    buffer_connection.moler_connection.data_received(output1.encode("utf-8"), datetime.datetime.now())
    buffer_connection.moler_connection.data_received("\n".encode("utf-8"), datetime.datetime.now())
    time.sleep(0.1)
    assert cmd_sudo._cmd_output_started is True
    assert r'export PS1="johnNamespace:\W\$"' in cmd_sudo._commands_to_send_when_after_login_prompt
    outputs = [output2, output3, output4, output5]
    for output in outputs:
        buffer_connection.moler_connection.data_received(output.encode("utf-8"), datetime.datetime.now())
        time.sleep(0.1)

    assert r'export PS1="johnNamespace:\W\$"' not in cmd_sudo._commands_to_send_when_after_login_prompt
    cmd_sudo.await_done()


@pytest.fixture()
def command_output_and_expected_result():
    output = """user@client:~/moler$ sudo pwd
[sudo] password for user:
/home/user/moler
user@host:~/moler$ """
    result = {
        'current_path': 'moler',
        'full_path': '/home/user/moler',
        'path_to_current': '/home/user'
    }
    return output, result


@pytest.fixture()
def command_output_and_expected_result_timeout():
    output = """user@client:~/moler$ sudo pwd
[sudo] password for user:
/home/user/moler
"""
    return output


@pytest.fixture()
def command_output_cp_fails():
    output = """sudo cp src.txt dst.txt
[sudo] password for user:
cp: cannot access
user@host:~/moler$ """
    return output


@pytest.fixture()
def command_output_cp_bit_fails():
    output = """sudo cp src.txt dst.txt
sudo: /usr/bin/sudo must be owned by uid 0 and have the setuid bit set
user@host:~/moler$ """
    return output


@pytest.fixture()
def command_output_password_fails():
    output = """sudo whoami
[sudo] password for john:
Sorry, try again.
[sudo] password for john:
Sorry, try again.
[sudo] password for john:
Sorry, try again.
sudo: 3 incorrect password attempts
[login]$ """
    return output



@pytest.fixture()
def command_output_command_not_found():
    output = """sudo pwd
[sudo] password for john:
sudo: pwd: command not found
user@host:~/moler$ """
    return output
