# -*- coding: utf-8 -*-

__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2026-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'

import subprocess

import pytest
import tempfile
import os
import getpass
import platform
from moler.device.unixlocal import UnixLocal
from moler.event_awaiter import EventAwaiter


@pytest.mark.skipif('Darwin' == platform.system(), reason="No ip on Macos on Github")
def test_many_commands_wait(unix_terminal):
    unix = unix_terminal
    cmd_ip_link = unix.get_cmd(cmd_name="ip_link", cmd_params={'action': 'show'})
    cmd_ip_addr = unix.get_cmd(cmd_name="ip_link", cmd_params={'action': 'show'})
    cmd_env = unix.get_cmd(cmd_name="env")
    cmd_ip_link.start()
    cmd_ip_addr.start()
    cmd_env.start()
    assert True is EventAwaiter.wait_for_all(timeout=10, events=[cmd_ip_link, cmd_ip_addr, cmd_env])
    env_ret = cmd_env.result()
    assert cmd_ip_addr.result() is not None
    assert cmd_ip_link.result() is not None
    assert "PWD" in env_ret


def test_many_commands_wait_ping(unix_terminal):
    unix = unix_terminal
    count_ping_1 = 1
    count_ping_2 = 2
    cmd_ping_1 = unix.get_cmd(cmd_name="ping", cmd_params={'options': f"-c {count_ping_1}", 'destination': '127.0.0.1'})
    cmd_ping_2 = unix.get_cmd(cmd_name="ping", cmd_params={'options': f"-c {count_ping_2}", 'destination': '127.0.0.1'})
    cmd_whoami = unix.get_cmd(cmd_name="whoami")
    cmd_ping_1.start()
    cmd_ping_2.start()
    cmd_whoami.start()
    assert True is EventAwaiter.wait_for_all(timeout=10, events=[cmd_ping_1, cmd_ping_2, cmd_whoami])
    ret_whoami = cmd_whoami.result()
    assert getpass.getuser() == ret_whoami['USER']
    assert cmd_ping_1.result() is not None
    assert cmd_ping_1.result()['packets_transmitted'] == count_ping_1
    assert cmd_ping_2.result() is not None
    assert cmd_ping_2.result()['packets_transmitted'] == count_ping_2


@pytest.mark.skipif('Darwin' == platform.system(), reason="No ip on Macos on Github")
def test_ip_link(unix_terminal):
    unix = unix_terminal
    cmd_ip = unix.get_cmd(cmd_name="ip_link", cmd_params={'action': 'show'})
    ret = cmd_ip()
    assert ret is not None


@pytest.mark.skipif('Darwin' == platform.system(), reason="No ip on Macos on Github")
def test_ip_neigh(unix_terminal):
    unix = unix_terminal
    cmd_ip = unix.get_cmd(cmd_name="ip_neigh", cmd_params={'options': 'show'})
    ret = cmd_ip()
    assert ret is not None


def test_enter(unix_terminal):
    unix = unix_terminal
    cmd_enter = unix.get_cmd(cmd_name="enter")
    cmd_enter()


def test_env(unix_terminal):
    unix = unix_terminal
    cmd_env = unix.get_cmd(cmd_name="env")
    ret = cmd_env()
    assert "PWD" in ret


def test_echo(unix_terminal):
    unix = unix_terminal
    text = "simple"
    cmd_echo = unix.get_cmd(cmd_name="echo", cmd_params={'text': text})
    ret = cmd_echo()
    assert text in ret['RESULT']


def test_dmesg(unix_terminal):
    unix = unix_terminal
    cmd_dmesg = unix.get_cmd(cmd_name="dmesg")
    cmd_dmesg.add_failure_exception(r"Failed to connect to system scope bus via local transport")
    ret = cmd_dmesg()
    assert 'LINES' in ret


def test_date(unix_terminal):
    unix = unix_terminal
    cmd_date = unix.get_cmd(cmd_name="date")
    ret = cmd_date()
    assert 'ZONE' in ret
    assert 'TIME' in ret


def test_uname(unix_terminal):
    unix = unix_terminal
    cmd_uname = unix.get_cmd(cmd_name="uname", cmd_params={"options": "-a"})
    ret = cmd_uname()
    found = False
    system_name = platform.system()
    for line in ret["RESULT"]:
        if system_name in line:
            found = True
    assert found


def test_whoami(unix_terminal):
    unix = unix_terminal
    cmd_whoami = unix.get_cmd(cmd_name="whoami")
    ret = cmd_whoami()
    assert getpass.getuser() == ret['USER']


def test_7z(unix_terminal):
    unix = unix_terminal
    cmd_7z = unix.get_cmd(cmd_name="7z", cmd_params={"options": "a", "archive_file": "arch.7z", "files": ["a", "b"],})
    assert cmd_7z is not None


@pytest.mark.skipif('Darwin' == platform.system(), reason="No md5sum on Macos on Github")
def test_cp_md5sum_cat_mv_rm_ls(unix_terminal):
    unix = unix_terminal
    f = tempfile.NamedTemporaryFile(delete=False)
    file_content = "content"
    md5sum = "f75b8179e4bbe7e2b4a074dcef62de95"
    data = (file_content + "\n").encode("latin-1")
    f.write(data)
    src = f.name
    f.close()
    tmp_dir = os.path.dirname(src)
    src_file = os.path.basename(src)
    dst_file = "dst.moler.file"
    dst = os.path.join(tmp_dir, dst_file)

    cmd_cat = unix.get_cmd(cmd_name="cat", cmd_params={"path": src})
    ret = cmd_cat()
    assert file_content in ret['LINES']

    cmd_md5sum = unix.get_cmd(cmd_name="md5sum", cmd_params={"path": src})
    ret = cmd_md5sum()
    assert ret["SUM"] == md5sum

    cmd_cp = unix.get_cmd(cmd_name="cp", cmd_params={"src": src, "dst": dst})
    cmd_cp()
    cmd_ls = unix.get_cmd(cmd_name="ls", cmd_params={"options": f"-l {tmp_dir}"})
    ret = cmd_ls()
    assert src_file in ret['files']
    assert dst_file in ret['files']

    cmd_rm = unix.get_cmd(cmd_name="rm", cmd_params={"file": dst})
    cmd_rm()
    cmd_ls = unix.get_cmd(cmd_name="ls", cmd_params={"options": '-l ' + tmp_dir})
    ret = cmd_ls()
    assert src_file in ret['files']
    assert dst_file not in ret['files']

    cmd_mv = unix.get_cmd(cmd_name="mv", cmd_params={"src": src, "dst": dst})
    cmd_mv()
    cmd_ls = unix.get_cmd(cmd_name="ls", cmd_params={"options": '-l ' + tmp_dir})
    ret = cmd_ls()
    assert src_file not in ret['files']
    assert dst_file in ret['files']

    cmd_rm = unix.get_cmd(cmd_name="rm", cmd_params={"file": dst})
    cmd_rm()
    cmd_ls = unix.get_cmd(cmd_name="ls", cmd_params={"options": '-l ' + tmp_dir})
    ret = cmd_ls()
    assert src_file not in ret['files']
    assert dst_file not in ret['files']


def test_ping_from_two_terminals(unix_terminal, unix_terminal2):
    unix1 = unix_terminal
    unix2 = unix_terminal2

    count1 = 2
    count2 = 3
    options1 = f"-c {count1} -i 0.2"
    options2 = f"-c {count2} -i 0.1"

    cmd_ping_1 = unix1.get_cmd(cmd_name="ping", cmd_params={'options': options1, 'destination': '127.0.0.1'})
    cmd_ping_2 = unix2.get_cmd(cmd_name="ping", cmd_params={'options': options2, 'destination': 'localhost'})
    cmd_ping_1.start()
    cmd_ping_2.start()
    assert cmd_ping_1.running()
    assert cmd_ping_2.running()
    ret1 = cmd_ping_1.await_done(timeout=10)
    ret2 = cmd_ping_2.await_done(timeout=10)
    assert 'packets_transmitted' in ret1
    assert ret1['packets_transmitted'] == count1
    assert 'packets_transmitted' in ret2
    assert ret2['packets_transmitted'] == count2


def test_ps_ef(unix_terminal):
    unix = unix_terminal
    ps_params = "-ef"
    cmd_ps = unix.get_cmd(cmd_name="ps", cmd_params={"options": ps_params})
    cmd_ps.start()
    # execute command ps -ef in local terminal and check if it returns something
    ret_local = subprocess.Popen(["ps", ps_params], text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE).communicate()
    assert ret_local is not None
    ret_moler = cmd_ps.await_done(timeout=10)
    assert ret_moler is not None
    local_lines = ret_local[0].splitlines()
    matched = 0
    diff = 0
    for item in ret_moler:
        cmd_name = item['CMD']
        found = False
        for line in local_lines:
            if cmd_name in line:
                found = True
                matched += 1
                break
        if not found:
            diff += 1
    assert matched > 0
    assert matched > diff


@pytest.fixture
def unix_terminal():
    unix = UnixLocal(io_type='terminal_no_fork', variant='threaded')
    unix.establish_connection()
    yield unix


@pytest.fixture
def unix_terminal2():
    unix = UnixLocal(io_type='terminal_no_fork', variant='threaded')
    unix.establish_connection()
    yield unix
