# -*- coding: utf-8 -*-
"""
Sudo command module.
"""

__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'

import re

from moler.cmd.commandchangingprompt import CommandChangingPrompt
from moler.exceptions import CommandFailure
from moler.exceptions import ParsingDone
from moler.helpers import copy_dict, copy_list
from moler.helpers import create_object_from_name


class Sudo(CommandChangingPrompt):
    """Unix command sudo"""

    def __init__(self, connection, password=None, sudo_params=None, cmd_object=None, cmd_class_name=None,
                 cmd_params=None, prompt=None, newline_chars=None, runner=None, encrypt_password=True,
                 expected_prompt=None, set_timeout=None, set_prompt=None, target_newline="\n",
                 allowed_newline_after_prompt=False, prompt_after_login=None, repeat_password=True):
        """
        Constructs object for Unix command sudo.

        :param connection: Moler connection to device, terminal when command is executed.
        :param password: password for sudo or list of passwords.
        :param sudo_params: params for sudo (not for command for sudo)
        :param cmd_object: object of command. Pass this object or cmd_class_name.
        :param cmd_class_name: full (with package) class name. Pass this name or cmd_object.
        :param cmd_params: params for cmd_class_name. If cmd_object is passed this parameter is ignored.
        :param prompt: prompt (on system where command runs).
        :param newline_chars: Characters to split lines - list.
        :param runner: Runner to run command.
        :param encrypt_password: If True then * will be in logs when password is sent, otherwise plain text.
        :param set_timeout: Command to set timeout after telnet connects.
        :param set_prompt: Command to set prompt after telnet connects.
        :param target_newline: newline chars on remote system where ssh connects.
        :param allowed_newline_after_prompt: If True then newline chars may occur after expected (target) prompt.
        :param prompt_after_login: prompt after login before send export PS1. If you do not change prompt exporting PS1
         then leave it None.
        :param repeat_password: If True then repeat last password if no more provided. If False then exception is set.

        """
        if expected_prompt is None or expected_prompt == '':
            expected_prompt = prompt
        super(Sudo, self).__init__(connection=connection, prompt=prompt, newline_chars=newline_chars,
                                   runner=runner, expected_prompt=expected_prompt, set_timeout=set_timeout,
                                   set_prompt=set_prompt, target_newline=target_newline,
                                   allowed_newline_after_prompt=allowed_newline_after_prompt,
                                   prompt_after_login=prompt_after_login)

        if isinstance(password, str):
            self.password = [password]
        elif password is None:
            self.password = []
        else:
            self.password = copy_list(password, deep_copy=False)  # copy of list of passwords to modify
        self._last_password = ""
        self.cmd_object = cmd_object
        self.cmd_params = cmd_params
        self.cmd_class_name = cmd_class_name
        self.encrypt_password = encrypt_password
        self.sudo_params = sudo_params
        self.timeout_from_embedded_command = True  # Set True to set timeout from command or False to use timeout set in
        #  sudo command.
        self.repeat_password = repeat_password
        self._sent_password = False
        self._sent_command_string = False
        self.newline_seq = "\n"
        self._line_for_sudo = False
        self._command_output_started = False
        self.ret_required = False
        self._validated_embedded_parameters = False  # Validate parameters only once
        self._finish_on_final_prompt = False

    def build_command_string(self):
        """
        Builds command string from parameters passed to object.

        :return: String representation of command to send over connection to device.
        """
        self._build_command_object()
        cmd = "sudo"
        if self.sudo_params:
            cmd = f"{cmd} {self.sudo_params}"
        if self.cmd_object:
            cmd = f"{cmd} {self.cmd_object.command_string}"
        return cmd

    def on_new_line(self, line, is_full_line):
        """
        Put your parsing code here.

        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param is_full_line: True if line had new line chars, False otherwise.
        :return: None
        """
        try:
            self._parse_password(line)
            self._process_wrong_password(line)
            self._parse_command_not_found(line)
            self._parse_error(line)
        except ParsingDone:
            self._line_for_sudo = True
        if is_full_line:
            self._sent_password = False
        super(Sudo, self).on_new_line(line, is_full_line)

    # pylint: disable=keyword-arg-before-vararg
    def start(self, timeout=None, *args, **kwargs):
        """Start background execution of connection-observer."""
        if timeout is not None:
            self.timeout_from_embedded_command = False
        return super(Sudo, self).start(timeout=timeout, args=args, kwargs=kwargs)

    def _process_line_from_command(self, current_chunk, line, is_full_line):
        """
        Processes line from command.

        :param current_chunk: Chunk of line sent by connection.
        :param line: Line of output (current_chunk plus previous chunks of this line - if any) without newline char(s).
        :param is_full_line: True if line had newline char(s). False otherwise.
        :return: None
        """
        decoded_line = self._decode_line(line=line)
        self._line_for_sudo = False
        self.on_new_line(line=decoded_line, is_full_line=is_full_line)
        if self.cmd_object:
            if not self._line_for_sudo:
                if not self.done() or self._command_output_started:
                    self._command_output_started = True
                    embedded_command_done = self.cmd_object.done()
                    self._process_embedded_command(partial_data=current_chunk)
                    if not embedded_command_done and self.cmd_object.done():
                        # process again because prompt was sent
                        self.on_new_line(line=decoded_line, is_full_line=is_full_line)

    def _process_embedded_command(self, partial_data):
        """
        Processes embedded command, passes output from device to embedded command.

        :param partial_data: Line from device filtered by sudo, only for embedded command.
        :return: None
        """
        if self.cmd_object:
            if not self._sent_command_string:
                self._sent_command_string = True
                self.cmd_object.life_status._is_running = True  # pylint: disable=protected-access
                cs = f"{self.cmd_object.command_string}{self.newline_seq}"
                self.cmd_object.data_received(cs, self._last_recv_time_data_read_from_connection)

            prev_cmd_timeout = self.cmd_object.timeout
            self.cmd_object.data_received(partial_data, self._last_recv_time_data_read_from_connection)
            new_cmd_timeout = self.cmd_object.timeout
            if self.timeout_from_embedded_command and prev_cmd_timeout != new_cmd_timeout:
                timedelta = new_cmd_timeout - prev_cmd_timeout
                self.extend_timeout(timedelta=timedelta)
            self.current_ret = self.cmd_object.current_ret
            if self.cmd_object.done():
                try:
                    result = self.cmd_object.result()
                    if self._finish_on_final_prompt is False and self.done() is False:
                        self.set_result(result=result)
                except Exception as ex:
                    self.set_exception(ex)
                    self._finish_on_final_prompt = True

    # sudo: pwd: command not found
    _re_sudo_command_not_found = re.compile(r"sudo:.*command not found", re.I)

    def _parse_command_not_found(self, line):
        """
        Parses if command not found is found in line.

        :param line: Line from device.
        :return: None
        :raises: ParsingDone if regex matches the line.
        """
        if re.search(Sudo._re_sudo_command_not_found, line):
            self.set_exception(CommandFailure(self, f"Command not found in line '{line}'."))
            self._finish_on_final_prompt = True
            raise ParsingDone()

    # Sorry, try again.
    _re_sudo_sorry_try_again = re.compile(r"Sorry, try again.", re.I)

    def _get_wrong_password_regex(self):
        return Sudo._re_sudo_sorry_try_again

    def _process_wrong_password(self, line):
        """
        Parses line for wrong password from sudo.

        :param line: Line from device.
        :return: None
        :raises: ParsingDone if regex matches the line.
        """
        if re.search(self._get_wrong_password_regex(), line):
            if not self._command_output_started:
                if (len(self.password) == 0) and (self.repeat_password is False):
                    self.set_exception(CommandFailure(self, f"Command error password found in line '{line}'."))
                    self._finish_on_final_prompt = True
                    self._sent_password = False
                raise ParsingDone()

    # sudo: /usr/bin/sudo must be owned by uid 0 and have the setuid bit set
    _re_sudo_error = re.compile(r"sudo:.*must be owned by uid\s+\d+\s+and have the setuid bit set|usage: sudo|"
                                r"sudo: \d+ incorrect password attempt|sudo: not found", re.I)

    def _get_error_regex(self):
        return Sudo._re_sudo_error

    def _parse_error(self, line):
        """
        Parses if command not found is found in line.

        :param line: Line from device.
        :return: None
        :raises: ParsingDone if regex matches the line.
        """
        if re.search(self._get_error_regex(), line):
            self.set_exception(CommandFailure(self, f"Command su error found in line '{line}'."))
            self._finish_on_final_prompt = True
            raise ParsingDone()

    # [sudo] password for user:
    _re_sudo_password = re.compile(r"\[sudo\] password for.*:", re.I)

    def _get_password_regex(self):
        return Sudo._re_sudo_password

    def _parse_password(self, line):
        """
        Parses if sudo waits for password.

        :param line: Line from device.
        :return: None
        :raises: ParsingDone if regex matches the line.
        """
        if re.search(self._get_password_regex(), line):
            if not self._sent_password:
                try:
                    current_password = self.password.pop(0)
                    self._last_password = current_password
                    self._send(current_password, encrypt=self.encrypt_password)
                except IndexError:
                    if self.repeat_password:
                        self._send(f"{self._last_password}", encrypt=self.encrypt_password)
                    else:
                        self.set_exception(
                            CommandFailure(self, "Password was requested but no more passwords provided."))
                        self.break_cmd()
                        raise ParsingDone()  # pylint: disable=raise-missing-from

                self._sent_password = True
            raise ParsingDone()

    def _validate_start(self, *args, **kwargs):
        """
        Validates internal data before start.

        :param args: args passed to super _validate_start
        :param kwargs: kwargs passed to super _validate_start
        :return: None
        :raises: CommandFailure if error in command settings.
        """
        super(Sudo, self)._validate_start(*args, **kwargs)
        self._validate_passed_object_or_command_parameters()
        if self.cmd_object:
            self.ret_required = self.cmd_object.ret_required
            if self.timeout_from_embedded_command:
                self.timeout = self.cmd_object.timeout
        else:
            self.ret_required = False

    def _validate_passed_object_or_command_parameters(self):
        """
        Validates passed parameters to create embedded command object.

        :return: None
        :raise: CommandFailure if command parameters are wrong.
        """
        if self._validated_embedded_parameters:
            return  # Validate parameters only once
        if not self.cmd_class_name and not self.cmd_object and not self.sudo_params:
            # _validate_start is called before running command on connection, so we raise exception
            # instead of setting it
            raise CommandFailure(
                self,
                "Neither 'cmd_class_name' nor 'cmd_object' nor 'sudo_params' was provided to Sudo constructor."
                "Please specific parameter.")
        if self.cmd_object and self.cmd_class_name:
            # _validate_start is called before running command on connection, so we raise exception instead
            # of setting it
            raise CommandFailure(
                self,
                "Both 'cmd_object' and 'cmd_class_name' parameters provided. Please specify only one."
            )
        if self.cmd_object and self.cmd_object.done():
            # _validate_start is called before running command on connection, so we raise exception
            # instead of setting it
            raise CommandFailure(
                self,
                f"Not allowed to run again the embedded command (embedded command is done): {self.cmd_object}."
            )
        self._validated_embedded_parameters = True

    def _build_command_object(self):
        """
        Builds command object from passed parameters to sudo command.

        :return: None
        """
        self._validate_passed_object_or_command_parameters()
        if self.cmd_object:
            return
        elif self.cmd_class_name is not None:
            params = copy_dict(self.cmd_params)
            params["connection"] = self.connection
            params['prompt'] = self._re_prompt
            params["newline_chars"] = self._newline_chars
            self.cmd_object = create_object_from_name(self.cmd_class_name, params)
        if self.cmd_object is None:
            self._finish_on_final_prompt = True


COMMAND_OUTPUT_whoami = """
user@client:~/moler$ sudo whoami
[sudo] password for user:
root
user@client:~/moler$ """

COMMAND_RESULT_whoami = {
    "USER": "root"
}

COMMAND_KWARGS_whoami = {
    "cmd_class_name": "moler.cmd.unix.whoami.Whoami",
    "password": "pass",
}

COMMAND_OUTPUT_dynamic_timeout = """
user@client:~/moler$ sudo nmap -sS -sV -p- -P0 -vvv --reason --webxml --min-rate 100 --max-rate 300 -oA ipv4 1.1.1.4 -PN
Starting Nmap 6.47 ( http://nmap.org ) at 2019-06-21 14:33 CEST

21 14:30:54.167 <|NSE: Loaded 29 scripts for scanning.
21 14:30:54.170 <|
                 |Initiating Parallel DNS resolution of 1 host. at 14:33

21 14:30:54.173 <|Completed Parallel DNS resolution of 1 host. at 14:33, 0.01s elapsed
                 |DNS resolution of 1 IPs took 0.01s. Mode: Async [#: 1, OK: 0, NX: 1, DR: 0, SF: 0, TR: 1, CN: 0]

21 14:30:54.189 <|Initiating SYN Stealth Scan at 14:33
                 |Scanning 1.1.1.4 [65535 ports]

21 14:30:54.395 <|Discovered open port 22/tcp on 1.1.1.4
                 |Discovered open port 80/tcp on 1.1.1.4
21 14:30:54.397 <|
                 |Discovered open port 443/tcp on 1.1.1.4

21 14:31:19.398 <|Increasing send delay for 10.83.182.11 from 0 to 5 due to 11 out of 33 dropped probes since last increase.

21 14:31:24.403 <|SYN Stealth Scan Timing: About 4.82% done; ETC: 14:43 (0:10:13 remaining)

21 14:31:24.405  |Extended timeout from 120.00 with delta 613.00 to 733.00
21 14:31:24.406  |Extended timeout from 120.00 with delta 613.00 to 733.00
21 14:31:45.896 <|Increasing send delay for 10.83.182.11 from 5 to 10 due to 11 out of 34 dropped probes since last increase.

21 14:31:54.237 <|SYN Stealth Scan Timing: About 5.32% done; ETC: 14:52 (0:18:05 remaining)

21 14:31:54.238  |Extended timeout from 733.00 with delta 1085.00 to 1818.00
21 14:31:54.239  |Extended timeout from 733.00 with delta 1085.00 to 1818.00
21 14:32:13.519 <|Increasing send delay for 10.83.182.11 from 10 to 20 due to 11 out of 32 dropped probes since last increase.

21 14:32:24.057 <|SYN Stealth Scan Timing: About 6.84% done; ETC: 14:55 (0:20:40 remaining)

21 14:32:24.058  |Extended timeout from 1818.00 with delta 1240.00 to 3058.00
21 14:32:24.059  |Extended timeout from 1818.00 with delta 1240.00 to 3058.00
21 14:32:42.300 <|Increasing send delay for 10.83.182.11 from 20 to 40 due to 11 out of 34 dropped probes since last increase.

21 14:32:53.886 <|SYN Stealth Scan Timing: About 8.35% done; ETC: 14:57 (0:22:08 remaining)

21 14:32:53.888  |Extended timeout from 3058.00 with delta 1328.00 to 4386.00
user@client:~/moler$ """

COMMAND_RESULT_dynamic_timeout = {
    'SYN_STEALTH_SCAN': {
        'DONE': '8.35',
        'ETC': '14:57',
        'REMAINING': '0:22:08'
    }
}

COMMAND_KWARGS_dynamic_timeout = {
    'cmd_class_name': r'moler.cmd.unix.nmap.Nmap',
    'password': r'pass',
    'cmd_params': {
        'options': r'-sS -sV -p- -P0 -vvv --reason --webxml --min-rate 100 --max-rate 300 -oA ipv4',
        'ip': r'1.1.1.4',
        'is_ping': False
    }
}

COMMAND_OUTPUT_ls = """
user@client:~/moler$ sudo ls -l
[sudo] password for user:
total 8
drwxr-xr-x  2 root root    4096 Sep 25  2014 bin
drwxr-xr-x  5 root root    4096 Mar 20  2015 btslog2
-rw-r--r--  1 root root      51 Dec 15 10:48 getfzmip.txt
-rw-r--r--  1 root root      24 Dec 15 10:48 getfzmip.txt-old.20171215-104858.txt
lrwxrwxrwx  1 root root       4 Mar 20  2015 bcn -> /bcn
lrwxrwxrwx  1 root root      10 Mar 20  2015 logsremote -> /mnt/logs/
user@client:~/moler$ """

COMMAND_RESULT_ls = {
    "total": {
        "raw": "8",
        "bytes": 8,
    },

    "files": {
        "bin": {"permissions": "drwxr-xr-x", "hard_links_count": 2, "owner": "root", "group": "root",
                "size_bytes": 4096, "size_raw": "4096", "date": "Sep 25  2014", "name": "bin", },
        "btslog2": {"permissions": "drwxr-xr-x", "hard_links_count": 5, "owner": "root", "group": "root",
                    "size_bytes": 4096, "size_raw": "4096", "date": "Mar 20  2015", "name": "btslog2", },
        "getfzmip.txt": {"permissions": "-rw-r--r--", "hard_links_count": 1, "owner": "root", "group": "root",
                         "size_bytes": 51, "size_raw": "51", "date": "Dec 15 10:48", "name": "getfzmip.txt", },
        "getfzmip.txt-old.20171215-104858.txt": {"permissions": "-rw-r--r--", "hard_links_count": 1,
                                                 "owner": "root",
                                                 "group": "root", "size_bytes": 24, "size_raw": "24",
                                                 "date": "Dec 15 10:48",
                                                 "name": "getfzmip.txt-old.20171215-104858.txt", },
        "bcn": {"permissions": "lrwxrwxrwx", "hard_links_count": 1, "owner": "root", "group": "root",
                "size_bytes": 4,
                "size_raw": "4", "date": "Mar 20  2015", "name": "bcn", "link": "/bcn"},
        "logsremote": {"permissions": "lrwxrwxrwx", "hard_links_count": 1, "owner": "root", "group": "root",
                       "size_bytes": 10, "size_raw": "10", "date": "Mar 20  2015", "name": "logsremote",
                       "link": "/mnt/logs/"},
    },
}

COMMAND_KWARGS_ls = {
    "cmd_class_name": "moler.cmd.unix.ls.Ls",
    "cmd_params": {"options": "-l"},
    "password": "pass",
}

COMMAND_OUTPUT_ifconfigdown = """
moler_bash# sudo ifconfig lo down
moler_bash#"""

COMMAND_RESULT_ifconfigdown = {}

COMMAND_KWARGS_ifconfigdown = {
    "cmd_class_name": "moler.cmd.unix.ifconfig.Ifconfig",
    "password": ["pass"],
    "cmd_params": {"options": "lo down"},
}

COMMAND_OUTPUT_i = """
moler_bash# sudo -i
root@host#"""

COMMAND_RESULT_i = {}

COMMAND_KWARGS_i = {
    'sudo_params': '-i', 'expected_prompt': "root@host.*#"
}

COMMAND_OUTPUT_su = """
moler_bash# sudo su
root@host#"""

COMMAND_RESULT_su = {}

COMMAND_KWARGS_su = {
    'expected_prompt': r"root@host.*#",
    'cmd_class_name': 'moler.cmd.unix.su.Su',
    'cmd_params': {  # params for su
        'expected_prompt': r"root@host.*#"
    }
}

COMMAND_OUTPUT_sudo_su_pwd = """user@host$ sudo su -c 'pwd -P'
/home/auto/inv
user@host$"""

COMMAND_KWARGS_sudo_su_pwd = {
    'cmd_class_name': 'moler.cmd.unix.su.Su',  # su as parameter of sudo
    'cmd_params': {  # parameters for sudo
        'cmd_class_name': 'moler.cmd.unix.pwd.Pwd',  # pwd as parameter for sudo
        'cmd_params': {'options': '-P'}  # parameters for pwd
    }
}

COMMAND_RESULT_sudo_su_pwd = {'full_path': '/home/auto/inv', 'path_to_current': '/home/auto', 'current_path': 'inv'}

COMMAND_OUTPUT_reboot = """sudo reboot
Connection to 192.168.255.179 closed by remote host.
"""

COMMAND_KWARGS_reboot = {
    'cmd_class_name': 'moler.cmd.unix.reboot.Reboot',  # reboot as parameter of sudo
}

COMMAND_RESULT_reboot = {
    'RESULT': 'Connection to 192.168.255.179 closed by remote host.'
}
