# -*- coding: utf-8 -*-
"""
SCP command module.
"""

import re

from moler.cmd.unix.genericunix import GenericUnixCommand
from moler.exceptions import CommandFailure, ParsingDone

__author__ = "Sylwester Golonka, Marcin Usielski, Michal Ernst"
__copyright__ = "Copyright (C) 2018-2026, Nokia"
__email__ = (
    "sylwester.golonka@nokia.com, marcin.usielski@nokia.com, michal.ernst@nokia.com"
)


class Scp(GenericUnixCommand):
    def __init__(
        self,
        connection,
        source,
        dest,
        password="",
        options="",
        prompt=None,
        newline_chars=None,
        known_hosts_on_failure="keygen",
        encrypt_password=True,
        runner=None,
        repeat_password=True,
    ):
        """
        Represents Unix command scp.

        :param connection: moler connection to device, terminal when command is executed
        :param source: path to source
        :param dest: path to destination
        :param password: scp password or list of passwords for multi passwords connection
        :param prompt: prompt (on system where command runs).
        :param newline_chars: characters to split lines
        :param known_hosts_on_failure: "rm" or "keygen" how to deal with error. If empty then scp fails.
        :param encrypt_password: If True then * will be in logs when password is sent, otherwise plain text
        :param runner: Runner to run command
        :param repeat_password: If True then repeat last password if no more provided. If False then exception is set.
        """
        super(Scp, self).__init__(
            connection=connection,
            prompt=prompt,
            newline_chars=newline_chars,
            runner=runner,
        )
        self.source = source
        self.dest = dest
        self.options = options
        self.known_hosts_on_failure = known_hosts_on_failure
        self.encrypt_password = encrypt_password
        self.ret_required = True
        # Internal variables
        self._sent_password = False
        self._sent_continue_connecting = False
        self._hosts_file = ""
        if isinstance(password, str):
            self._passwords = [password]
        else:
            self._passwords = list(password)  # copy of list of passwords to modify
        self.repeat_password = repeat_password
        self._last_password = ""

    def build_command_string(self):
        """
        Builds command string from parameters passed to object.

        :return: String representation of command to send over connection to device.
        """
        cmd = "scp"
        if self.options:
            cmd = f"{cmd} {self.options} {self.source} {self.dest}"
        else:
            cmd = f"{cmd} {self.source} {self.dest}"
        return cmd

    def on_new_line(self, line, is_full_line):
        """
        Put your parsing code here.

        :param line: Line to process, can be only part of line. New line chars are removed from line.
        :param is_full_line: True if line had new line chars, False otherwise.
        :return: None
        """
        try:
            self._know_hosts_verification(line)
            self._parse_success(line)
            self._push_yes_if_needed(line)
            self._parse_sent_password(line)
            self._parse_failed(line)
            self._get_hosts_file_if_displayed(line)
        except ParsingDone:
            pass
        if is_full_line:
            self._sent_password = False  # Clear flag for multi passwords connections
        return super(Scp, self).on_new_line(line, is_full_line)

    _re_parse_success = re.compile(r"^(?P<FILENAME>\S+)\s+.*\d+%.*")

    def _parse_success(self, line):
        """
        Parses line if success.

        :param line: Line from device.
        :return: None
        :raises ParsingDone: if matches success.
        """
        if self._regex_helper.search_compiled(Scp._re_parse_success, line):
            if "FILE_NAMES" not in self.current_ret.keys():
                self.current_ret["FILE_NAMES"] = []

            self.current_ret["FILE_NAMES"].append(self._regex_helper.group("FILENAME"))
            raise ParsingDone()

    _re_parse_failed = re.compile(
        r'cannot access|Could not|no such|denied|not a regular file|Is a directory|No route to host|"'
        r"lost connection|Not a directory",
        re.IGNORECASE,
    )

    def _parse_failed(self, line):
        """
        Parses line if failed.

        :param line: Line from device.
        :return: None
        :raises ParsingDone: if matches fail.
        """
        if self._regex_helper.search_compiled(Scp._re_parse_failed, line):
            self.set_exception(
                CommandFailure(self, f"Command failed in line >>{line}<<.")
            )
            raise ParsingDone()

    _re_parse_permission_denied = re.compile(
        r"Permission denied, please try again|Permission denied \(publickey,password\)"
    )

    def _parse_sent_password(self, line):
        """
        Sends password if necessary.

        :param line: Line from device.
        :return: None
        :raises  ParsingDone: if password was sent.
        """
        if (not self._sent_password) and self._is_password_requested(line):
            try:
                pwd = self._passwords.pop(0)
                self._last_password = pwd
                self.connection.sendline(pwd, encrypt=self.encrypt_password)
            except IndexError:
                if self.repeat_password:
                    self.connection.sendline(
                        self._last_password, encrypt=self.encrypt_password
                    )
                else:
                    self.set_exception(
                        CommandFailure(
                            self,
                            "Password was requested but no more passwords provided.",
                        )
                    )
                    self.break_cmd()
            self._sent_password = True
            raise ParsingDone()

    _re_password = re.compile(r"password:", re.IGNORECASE)

    def _is_password_requested(self, line):
        """
        Parses line if password is requested.

        :param line: Line from device.
        :return: Match object if matches, otherwise None.
        """
        return self._regex_helper.search_compiled(Scp._re_password, line)

    def _push_yes_if_needed(self, line):
        """
        Sends yes to device if needed.

        :param line: Line from device.
        :return: None
        :raises ParsingDone: if line handled by this method.
        """
        if (not self._sent_continue_connecting) and self._parse_continue_connecting(
            line
        ):
            self.connection.sendline("yes")
            self._sent_continue_connecting = True
            raise ParsingDone()

    _re_continue_connecting = re.compile(
        r"\(y/n\)|\(yes/no.*\)\?|'yes' or 'no':", re.IGNORECASE
    )

    def _parse_continue_connecting(self, line):
        """
        Parses continue connecting.

        :param line: Line from device.
        :return: Match object if matches, None otherwise.
        """
        return self._regex_helper.search_compiled(Scp._re_continue_connecting, line)

    _re_host_key = re.compile(
        r"Add correct host key in (?P<PATH>\S+) to get rid of this message",
        re.IGNORECASE,
    )

    def _get_hosts_file_if_displayed(self, line):
        """
        Parses hosts file.

        :param line: Line from device.
        :return: None
        :raises ParsingDone: if line handled by this method.

        """
        if (
            self.known_hosts_on_failure is not None
        ) and self._regex_helper.search_compiled(Scp._re_host_key, line):
            self._hosts_file = self._regex_helper.group("PATH")
            raise ParsingDone()

    _re_id_dsa = re.compile("id_dsa:", re.IGNORECASE)

    _re_host_key_verification_failure = re.compile(r"Host key verification failed.")

    def _know_hosts_verification(self, line):
        """
        Parses host key verification.

        :param line: Line from device.
        :return: None
        :raises ParsingDone: if line handled by this method.
        """
        if self._regex_helper.search_compiled(Scp._re_id_dsa, line):
            self.connection.sendline("")
            raise ParsingDone()
        elif self._regex_helper.search_compiled(
            Scp._re_host_key_verification_failure, line
        ):
            if self._hosts_file:
                self._handle_failed_host_key_verification()
            else:
                self.set_exception(
                    CommandFailure(self, f"Command failed in line >>{line}<<.")
                )
            raise ParsingDone()

    def _handle_failed_host_key_verification(self):
        """
        Handles failed host key verification.

        :return: None
        """
        if "rm" == self.known_hosts_on_failure:
            self.connection.sendline(f"\nrm -f {self._hosts_file}")
        elif "keygen" == self.known_hosts_on_failure:
            self.connection.sendline(f"\nssh-keygen -R {self.dest}")
        else:
            self.set_exception(
                CommandFailure(
                    self,
                    f"Bad value of parameter known_hosts_on_failure '{self.known_hosts_on_failure}'. "
                    "Supported values: rm or keygen."
                )
            )
        self._sent_continue_connecting = False
        self._sent_password = False
        self.connection.sendline(self.command_string)


COMMAND_OUTPUT_succsess = """
ute@debdev:~/Desktop$ scp test.txt ute@localhost:/home/ute
ute@localhost's password:
test.txt                                                            100%  104     0.1KB/s   00:00
ute@debdev:~/Desktop$"""

COMMAND_KWARGS_succsess = {
    "source": "test.txt",
    "dest": "ute@localhost:/home/ute",
    "password": "pass",
}

COMMAND_RESULT_succsess = {"FILE_NAMES": ["test.txt"]}

COMMAND_OUTPUT_recursively_succsess = """
ute@debdev:~/Desktop$ scp -r test ute@localhost:/home/ute
ute@localhost's password:
test.txt                                                             100%  104     0.1KB/s   00:00
test2.txt                                                            100%  104     0.1KB/s   00:00
ute@debdev:~/Desktop$"""

COMMAND_KWARGS_recursively_succsess = {
    "source": "test",
    "dest": "ute@localhost:/home/ute",
    "password": "ute",
    "options": "-r",
}

COMMAND_RESULT_recursively_succsess = {"FILE_NAMES": ["test.txt", "test2.txt"]}

COMMAND_KWARGS_rm = {
    "source": "test.txt",
    "dest": "ute@localhost:/home/ute",
    "password": "pass",
    "known_hosts_on_failure": "rm",
}

COMMAND_OUTPUT_rm = """
ute@debdev:~/Desktop$ scp test.txt ute@localhost:/home/ute
Are you sure you want to continue connecting (yes/no)?"
Please contact your system administrator.
Add correct host key in /home/sward/.ssh/known_hosts to get rid of this message.
Offending RSA key in /home/sward/.ssh/known_hosts:86
RSA host key for [...] has changed and you have requested strict checking.
Host key verification failed.
ute@debdev:~/Desktop$ rm -f /home/sward/.ssh/known_hosts
ute@debdev:~/Desktop$ scp test ute@localhost:/home/ute
test.txt                                                            100%  104     0.1KB/s   00:00
ute@debdev:~/Desktop$ """

COMMAND_RESULT_rm = {"FILE_NAMES": ["test.txt"]}

COMMAND_KWARGS_keygen = {
    "source": "test.txt",
    "dest": "ute@localhost:/home/ute",
    "password": "pass",
}

COMMAND_OUTPUT_keygen = """
ute@debdev:~/Desktop$ scp test.txt ute@localhost:/home/ute
id_dsa:
Are you sure you want to continue connecting (yes/no)?"
Please contact your system administrator.
Add correct host key in /home/sward/.ssh/known_hosts to get rid of this message.
Offending RSA key in /home/sward/.ssh/known_hosts:86
RSA host key for [...] has changed and you have requested strict checking.
Host key verification failed.

ute@debdev:~/Desktop$ ssh-keygen -R ute@localhost:/home/ute
ute@debdev:~/Desktop$ scp test ute@localhost:/home/ute
test.txt                                                            100%  104     0.1KB/s   00:00
ute@debdev:~/Desktop$ """

COMMAND_RESULT_keygen = {"FILE_NAMES": ["test.txt"]}

COMMAND_OUTPUT_ldap = """
ute@debdev:~/Desktop$ scp test.txt ute@localhost:/home/ute
ute@localhost's password:
ldap password:
test.txt                                                            100%  104     0.1KB/s   00:00
ute@debdev:~/Desktop$"""

COMMAND_KWARGS_ldap = {
    "source": "test.txt",
    "dest": "ute@localhost:/home/ute",
    "password": ("pass1", "pass2"),
}

COMMAND_RESULT_ldap = {"FILE_NAMES": ["test.txt"]}
