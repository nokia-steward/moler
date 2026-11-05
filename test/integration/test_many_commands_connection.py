# -*- coding: utf-8 -*-
"""
Testing of uptime command.
"""
__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'

import pytest
import time
from moler.event_awaiter import EventAwaiter
from moler.exceptions import CommandTimeout
from moler.command_scheduler import CommandScheduler
import datetime


def test_two_commands_uptime_whoami(buffer_connection, command_output_and_expected_result_uptime_whoami):
    from moler.cmd.unix.uptime import Uptime
    from moler.cmd.unix.whoami import Whoami
    command_output, expected_result = command_output_and_expected_result_uptime_whoami
    uptime_cmd = Uptime(connection=buffer_connection.moler_connection)
    whoami_cmd = Whoami(connection=buffer_connection.moler_connection)
    uptime_cmd.start(timeout=2)
    time.sleep(0.005)
    whoami_cmd.start(timeout=2)
    time.sleep(0.05)
    assert CommandScheduler.is_waiting_for_execution(connection_observer=whoami_cmd) is True
    buffer_connection.moler_connection.data_received(command_output[0].encode("utf-8"), datetime.datetime.now())
    time.sleep(0.2)
    buffer_connection.moler_connection.data_received(command_output[1].encode("utf-8"), datetime.datetime.now())
    assert EventAwaiter.wait_for_all(timeout=2, events=[uptime_cmd, whoami_cmd]) is True
    ret_uptime = uptime_cmd.result()
    ret_whoami = whoami_cmd.result()
    assert ret_uptime == expected_result[0]
    assert ret_whoami == expected_result[1]
    assert CommandScheduler.is_waiting_for_execution(connection_observer=whoami_cmd) is False


def test_two_commands_uptime(buffer_connection, command_output_and_expected_result_uptime):
    from moler.cmd.unix.uptime import Uptime
    command_output, expected_result = command_output_and_expected_result_uptime
    uptime1_cmd = Uptime(connection=buffer_connection.moler_connection, prompt="host:.*#")
    uptime2_cmd = Uptime(connection=buffer_connection.moler_connection, prompt="host:.*#")
    uptime1_cmd.start(timeout=2)
    uptime2_cmd.start(timeout=2)
    time.sleep(0.05)
    buffer_connection.moler_connection.data_received(command_output[0].encode("utf-8"), datetime.datetime.now())
    time.sleep(0.2)
    buffer_connection.moler_connection.data_received(command_output[1].encode("utf-8"), datetime.datetime.now())
    assert EventAwaiter.wait_for_all(timeout=2, events=(uptime1_cmd, uptime2_cmd)) is True
    uptime1_ret = uptime1_cmd.result()
    uptime2_ret = uptime2_cmd.result()
    assert uptime1_ret == expected_result[0]
    assert uptime2_ret == expected_result[1]


def test_timeout_before_command_sent(buffer_connection, command_output_and_expected_result_ping):
    from moler.cmd.unix.uptime import Uptime
    from moler.cmd.unix.ping import Ping
    command_output, expected_result = command_output_and_expected_result_ping
    ping_cmd = Ping(connection=buffer_connection.moler_connection, prompt="host:.*#", destination="localhost",
                    options="-w 5")
    uptime_cmd = Uptime(connection=buffer_connection.moler_connection, prompt="host:.*#")
    ping_cmd.start(timeout=2)
    time.sleep(0.05)
    buffer_connection.moler_connection.data_received(command_output[0].encode("utf-8"), datetime.datetime.now())
    with pytest.raises(CommandTimeout):
        uptime_cmd(timeout=0.2)
    buffer_connection.moler_connection.data_received(command_output[1].encode("utf-8"), datetime.datetime.now())
    ping_cmd.await_done(timeout=0.2)
    ping_ret = ping_cmd.result()
    assert ping_ret == expected_result


def test_timeout_before_command_sent_with_observer_timeout(buffer_connection,
                                                           command_output_and_expected_result_ping):
    from moler.cmd.unix.uptime import Uptime
    from moler.cmd.unix.ping import Ping
    command_output, expected_result = command_output_and_expected_result_ping
    ping_cmd = Ping(connection=buffer_connection.moler_connection, prompt="host:.*#", destination="localhost",
                    options="-w 5")
    uptime_cmd = Uptime(connection=buffer_connection.moler_connection, prompt="host:.*#")
    uptime_cmd.terminating_timeout = 0
    ping_cmd.start(timeout=3)
    time.sleep(0.05)
    buffer_connection.moler_connection.data_received(command_output[0].encode("utf-8"), datetime.datetime.now())
    start_time = time.monotonic()
    uptime_cmd.start(timeout=0.5)
    time.sleep(0.4)  # must be shorter than uptime timeout to await still queued command
    with pytest.raises(CommandTimeout):
        uptime_cmd.await_done()
    duration = time.monotonic() - start_time
    assert duration >= 0.5
    assert duration < 0.8
    buffer_connection.moler_connection.data_received(command_output[1].encode("utf-8"), datetime.datetime.now())
    ping_cmd.await_done(timeout=0.5)
    ping_ret = ping_cmd.result()
    assert ping_ret == expected_result


@pytest.fixture
def command_output_and_expected_result_ping():
    data = (
        """host:~ # ping localhost -w 5
PING localhost (127.0.0.1) 56(84) bytes of data.
64 bytes from localhost (127.0.0.1): icmp_seq=1 ttl=64 time=0.047 ms
64 bytes from localhost (127.0.0.1): icmp_seq=2 ttl=64 time=0.039 ms
64 bytes from localhost (127.0.0.1): icmp_seq=3 ttl=64 time=0.041 ms
""",
        """
64 bytes from localhost (127.0.0.1): icmp_seq=4 ttl=64 time=0.035 ms
64 bytes from localhost (127.0.0.1): icmp_seq=5 ttl=64 time=0.051 ms
64 bytes from localhost (127.0.0.1): icmp_seq=6 ttl=64 time=0.062 ms

--- localhost ping statistics ---
6 packets transmitted, 6 received, 0% packet loss, time 4996ms
rtt min/avg/max/mdev = 0.035/0.045/0.062/0.012 ms
host:~ # """
    )

    result = {
        'packets_transmitted': 6,
        'packets_received': 6,
        'packet_loss': 0,
        'time': 4996,
        'time_seconds': 4.996,
        'packets_time_unit': 'ms',
        'time_min': 0.035,
        'time_avg': 0.045,
        'time_max': 0.062,
        'time_mdev': 0.012,
        'time_min_seconds': 0.035 * 0.001,
        'time_avg_seconds': 0.045 * 0.001,
        'time_max_seconds': 0.062 * 0.001,
        'time_mdev_seconds': 0.012 * 0.001,
        'time_unit': 'ms',
    }
    return data, result


@pytest.fixture
def command_output_and_expected_result_uptime_whoami():
    data = ("""uptime
 10:38am  up 3 days  2:14,  29 users,  load average: 0.09, 0.10, 0.07
host:~ # """,
            """whoami
user
host:~ # """)

    result = (
        {
            "UPTIME": '3 days  2:14',
            "UPTIME_SECONDS": 267240,
            "USERS": 29,
        },
        {
            "USER": "user"
        }
    )
    return data, result


@pytest.fixture
def command_output_and_expected_result_uptime():
    data = (
"""host:~ # uptime
 10:38am  up 3 days  2:14,  29 users,  load average: 0.09, 0.10, 0.07
host:~ # """,
"""uptime
10:38am  up 3 days  2:15,  8 users,  load average: 0.09, 0.10, 0.07
host:~ # """)

    result = (
        {
            "UPTIME": '3 days  2:14',
            "UPTIME_SECONDS": 267240,
            "USERS": 29,
        },
        {
            "UPTIME": '3 days  2:15',
            "UPTIME_SECONDS": 267300,
            "USERS": 8,
        }
    )
    return data, result
