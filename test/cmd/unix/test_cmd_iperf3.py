# -*- coding: utf-8 -*-
"""
Iperf3 command test module.
"""

__author__ = "Kacper Kozik, Marcin Usielski"
__copyright__ = "Copyright (C) 2023-2026, Nokia"
__email__ = "kacper.kozik@nokia.com, marcin.usielski@nokia.com"

import pytest
from unittest import mock
import time
import platform
from moler.cmd.unix.iperf3 import Iperf3
from moler.exceptions import CommandFailure, CommandTimeout


pytestmark = pytest.mark.skipif('Linux' != platform.system(), reason="Skip for no Linux system.")


def test_iperf_returns_proper_command_string(buffer_connection):
    iperf_cmd = Iperf3(buffer_connection, options='-c 10.1.1.1 -M 1300 -m')
    assert "iperf3 -c 10.1.1.1 -M 1300 -m" == iperf_cmd.command_string


def test_iperf_can_set_direct_path_to_command_executable(buffer_connection):
    iperf_cmd = Iperf3(buffer_connection, options='-c 10.1.1.1 -M 1300 -m')
    assert "iperf3 -c 10.1.1.1 -M 1300 -m" == iperf_cmd.command_string
    iperf_cmd.command_path = 'adb shell /data/data/com.magicandroidapps.iperf/bin/'
    assert "adb shell /data/data/com.magicandroidapps.iperf/bin/iperf3 -c 10.1.1.1 -M 1300 -m" == iperf_cmd.command_string


def test_iperf_raise_error_on_bind_failed(buffer_connection, command_output_and_expected_result_on_bind_failed):
    iperf_cmd = Iperf3(
        connection=buffer_connection.moler_connection, options='-s')
    command_output, expected_result = command_output_and_expected_result_on_bind_failed
    buffer_connection.remote_inject_response([command_output])
    assert 'iperf3 -s' == iperf_cmd.command_string
    with pytest.raises(CommandFailure):
        iperf_cmd(timeout=0.2)


def test_iperf_raise_error_on_no_such_file(buffer_connection, command_output_and_expected_result_on_connect_failed):
    iperf_cmd = Iperf3(
        connection=buffer_connection.moler_connection, options='-c 10.156.236.132')
    command_output, expected_result = command_output_and_expected_result_on_connect_failed
    buffer_connection.remote_inject_response([command_output])
    assert 'iperf3 -c 10.156.236.132' == iperf_cmd.command_string
    with pytest.raises(CommandFailure):
        iperf_cmd(timeout=0.2)


def test_iperf_raise_error_on_iperf_problem(buffer_connection, command_output_and_expected_result_on_iperf_problem):
    iperf_cmd = Iperf3(
        connection=buffer_connection.moler_connection, options='-i')
    command_output, expected_result = command_output_and_expected_result_on_iperf_problem
    buffer_connection.remote_inject_response([command_output])
    assert 'iperf3 -i' == iperf_cmd.command_string
    with pytest.raises(CommandFailure):
        iperf_cmd()


def test_iperf_raise_error_on_udp_server_option(buffer_connection):
    with pytest.raises(AttributeError) as err:
        Iperf3(connection=buffer_connection.moler_connection, options='-s -u')
    assert "Option (--udp) you are trying to set is client only" in str(
        err.value)


def test_iperf_raise_error_on_time_server_option(buffer_connection):
    with pytest.raises(AttributeError) as err:
        Iperf3(connection=buffer_connection.moler_connection, options='-s -t 5')
    assert "Option (--time) you are trying to set is client only" in str(
        err.value)


def test_iperf_raise_error_on_parallel_connection_server_option(buffer_connection):
    with pytest.raises(AttributeError) as err:
        Iperf3(connection=buffer_connection.moler_connection, options='-s -P 3')
    assert "Option (--parallel) you are trying to set is client only" in str(
        err.value)


def test_iperf_stores_ipv6_connections_as_port_at_host_tuple_for_local_and_remote(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_tcp_ipv6_client])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_tcp_ipv6_client)
    iperf_cmd()
    stored_connections = iperf_cmd.result()['CONNECTIONS'].keys()
    #      local port@host      remote port@host
    assert len(stored_connections) == 2
    assert ("49597@fd00::2:0", "5901@fd00::1:0") in stored_connections
    assert ("fd00::2:0", "5901@fd00::1:0") in stored_connections


def test_iperf_creates_summary_connection_for_parallel_testing(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_multiple_connections])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections)
    iperf_cmd()
    stored_connections = iperf_cmd.result()['CONNECTIONS'].keys()
    #        local host:port      remote host:port
    assert len(stored_connections) == 5
    assert ('multiport@127.0.0.1',
            '5201@127.0.0.1') in stored_connections  # summary
    assert ('127.0.0.1', '5201@127.0.0.1') in stored_connections  # result


def test_iperf_ignores_multiple_echo_of_command(buffer_connection):
    # running on cygwin may cause getting multiple echo even mixed with prompt
    from moler.cmd.unix import iperf3

    collected_lines = []
    output_with_multiple_echo = "andromeda:/ # /bin/iperf3 -c 1.2.3.4 -p 5001 -f k -i 1.0 -t 6.0\n" + \
                                "/bin/iperf3 -c 1.2.3.4 -p 5001 -f k -i 1.0 -t 6.0 -\n" + \
                                "andromeda:/ # /bin/iperf3 -c 1.2.3.4 -p 5001 -f k -i 1.0 -t 6.0\n" + \
                                "------------------------------------------------------------\n" + \
                                "[  3] local 192.168.0.1 port 49597 connected to 1.2.3.4 port 5001\n" + \
                                "[ ID] Interval       Transfer     Bitrate\n" + \
                                "[  3]  0.0- 1.0 sec  28.6 MBytes   240 Mbits/sec\n" + \
                                "[  3]  0.0-10.0 sec   265 MBytes   222 Mbits/sec\n" + \
                                "andromeda:/ # "

    buffer_connection.remote_inject_response([output_with_multiple_echo])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              prompt='andromeda:/ # ',
                              options='-c 1.2.3.4 -p 5001 -f k -i 1.0 -t 6.0')
    iperf_cmd.command_path = '/bin/'
    oryg_on_new_line = iperf_cmd.__class__.on_new_line

    def on_new_line(self, line, is_full_line):
        collected_lines.append(line)
        oryg_on_new_line(self, line, is_full_line)

    with mock.patch.object(iperf_cmd.__class__, "on_new_line", on_new_line):
        iperf_cmd()
    assert "andromeda:/ # /bin/iperf3 -c 1.2.3.4 -p 5001 -f k -i 1.0 -t 6.0" not in collected_lines


def test_iperf_correctly_parses_basic_udp_server_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_basic_server])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_basic_server)
    ret = iperf_cmd()
    assert ret == iperf3.COMMAND_RESULT_basic_server


def test_iperf_correctly_parses_basic_tcp_client_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_basic_client])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_basic_client)
    res = iperf_cmd()
    assert res == iperf3.COMMAND_RESULT_basic_client


def test_iperf_correctly_parses_basic_tcp_client_bytes_bits_convert_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_basic_client_bytes_bits_convert])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_basic_client_bytes_bits_convert)
    res = iperf_cmd()
    assert res == iperf3.COMMAND_RESULT_basic_client_bytes_bits_convert


def test_iperf_correctly_parses_tcp_ipv6_client_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_tcp_ipv6_client])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_tcp_ipv6_client)
    res = iperf_cmd()
    assert res == iperf3.COMMAND_RESULT_tcp_ipv6_client


def test_iperf_correctly_parses_tcp_ipv6_server_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_tcp_ipv6_server])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_tcp_ipv6_server)
    res = iperf_cmd()
    assert res == iperf3.COMMAND_RESULT_tcp_ipv6_server


def test_iperf_correctly_parses_multiconnection_tcp_client_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_multiple_connections])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections)
    ret = iperf_cmd()
    assert ret == iperf3.COMMAND_RESULT_multiple_connections


def test_iperf_correctly_parses_multiconnection_tcp_server_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_multiple_connections_server])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections_server)
    ret = iperf_cmd()
    assert ret == iperf3.COMMAND_RESULT_multiple_connections_server


def test_iperf_server_detects_all_multiport_records_of_interval(buffer_connection):
    from moler.cmd.unix import iperf3
    from moler.exceptions import ParsingDone
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections_udp_server)
    client_connection_lines = [
        "[  5] local 127.0.0.1 port 5016 connected to 127.0.0.1 port 33549",
        "[  6] local 127.0.0.1 port 5016 connected to 127.0.0.1 port 36062",
        "[  9] local 127.0.0.1 port 5016 connected to 127.0.0.1 port 52695"
    ]
    for line in client_connection_lines:
        try:
            iperf_cmd._parse_connection_name_and_id(line)
        except ParsingDone:
            pass
    parallel_client_1 = ('33549@127.0.0.1', '5016@127.0.0.1')
    parallel_client_2 = ('36062@127.0.0.1', '5016@127.0.0.1')
    parallel_client_3 = ('52695@127.0.0.1', '5016@127.0.0.1')

    single_record = {'Bitrate': 132125,
                     'Bitrate Raw': '1057 Kbits/sec',
                     'Interval': (0.0, 1.0),
                     'Jitter': 0.007,
                     'Jitter Raw': '0.007 ms',
                     'Lost_Datagrams_ratio': '0%',
                     'Lost_vs_Total_Datagrams': (0, 6),
                     'Transfer': 132096,
                     'Transfer Raw': '129 KBytes'}

    iperf_cmd.current_ret['CONNECTIONS'][parallel_client_1] = [single_record]
    iperf_cmd.current_ret['CONNECTIONS'][parallel_client_2] = [single_record]
    assert iperf_cmd._all_multiport_records_of_interval(
        connection_name=parallel_client_2) is False
    iperf_cmd.current_ret['CONNECTIONS'][parallel_client_3] = [single_record]
    assert iperf_cmd._all_multiport_records_of_interval(
        connection_name=parallel_client_3) is True
    second_record = dict(single_record)
    second_record['Interval'] = (1.0, 2.0)
    iperf_cmd.current_ret['CONNECTIONS'][parallel_client_1] = [second_record]
    assert iperf_cmd._all_multiport_records_of_interval(
        connection_name=parallel_client_1) is False
    iperf_cmd.current_ret['CONNECTIONS'][parallel_client_2] = [second_record]
    assert iperf_cmd._all_multiport_records_of_interval(
        connection_name=parallel_client_2) is False
    iperf_cmd.current_ret['CONNECTIONS'][parallel_client_3] = [second_record]
    assert iperf_cmd._all_multiport_records_of_interval(
        connection_name=parallel_client_3) is True


def test_iperf_correctly_parses_multiconnection_udp_server_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_multiple_connections_udp_server])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections_udp_server)
    ret = iperf_cmd()
    assert ret == iperf3.COMMAND_RESULT_multiple_connections_udp_server


def test_iperf_correctly_parses_multiconnection_udp_client_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_multiple_connections_udp_client])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections_udp_client)
    ret = iperf_cmd()
    assert ret == iperf3.COMMAND_RESULT_multiple_connections_udp_client


def test_iperf_correctly_breaks_server_on_final_inactivity(buffer_connection):
    from moler.cmd.unix import iperf3
    cmd_output = iperf3.COMMAND_OUTPUT_multiple_connections_udp_server.split(
        "\n")
    prompt = cmd_output.pop()
    cmd_output_without_prompt = "\n".join(cmd_output) + "\n"
    buffer_connection.remote_inject_response([cmd_output_without_prompt])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections_udp_server)

    def injecting_break_cmd(self):
        self.connection.send("\x03")  # ctrl+c
        buffer_connection.remote_inject_line(line="^C", add_newline=False)
        buffer_connection.remote_inject_line(line=prompt, add_newline=False)

    # ensuring that break_cmd() is not called via on_timeout()
    iperf_cmd.break_on_timeout = False
    with mock.patch.object(iperf_cmd.__class__, "break_cmd", injecting_break_cmd):
        ret = iperf_cmd()
        assert ret == iperf3.COMMAND_RESULT_multiple_connections_udp_server


def test_iperf_correctly_parses_singlerun_tcp_server_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_singlerun_server])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_singlerun_server)
    ret = iperf_cmd()
    assert ret == iperf3.COMMAND_RESULT_singlerun_server


def test_iperf_correctly_parses_singlerun_udp_server_output(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_singlerun_udp_server])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_singlerun_udp_server)
    ret = iperf_cmd()
    assert ret == iperf3.COMMAND_RESULT_singlerun_udp_server


def test_iperf_singlerun_server_doesnt_use_ctrlc_to_stop_server(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_singlerun_server])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_singlerun_server)
    with mock.patch.object(iperf_cmd, "break_cmd") as send_ctrlc:
        iperf_cmd()
    send_ctrlc.assert_not_called()


def test_iperf_sends_additional_ctrl_c_after_detecting_to_early_ctrl_c(buffer_connection):
    from moler.cmd.unix import iperf3

    normal_iperf_output = iperf3.COMMAND_OUTPUT_multiple_connections_server.splitlines(
        True)
    last_line_with_prompt = normal_iperf_output[-1]
    normal_iperf_output[-1] = "^CWaiting for server threads to complete. Interrupt again to force quit\n"
    normal_iperf_output.append(last_line_with_prompt)
    output_with_too_early_ctrl_c = "".join(normal_iperf_output)

    buffer_connection.remote_inject_response([output_with_too_early_ctrl_c])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections_server)
    with mock.patch.object(iperf_cmd, "_stop_server"):
        with mock.patch.object(iperf_cmd, "break_cmd") as break_cmd_method:
            iperf_cmd()
    break_cmd_method.assert_called_once_with()


def test_iperf_timeout_on_version_not_provied_but_prompt(buffer_connection):
    iperf_cmd = Iperf3(connection=buffer_connection.moler_connection, options='--version')
    command_output = """xyz@debian:~$ iperf3 --version
Last login: Thu Nov 14 16:35:41 2024 from 127.0.0.1
xyz@debian:~$
xyz@debian:~$echo DETECTING PROMPT
DETECTING PROMPT
xyz@debian:~$"""
    buffer_connection.remote_inject_response([command_output])
    assert 'iperf3 --version' == iperf_cmd.command_string
    iperf_cmd.terminating_timeout = 0
    with pytest.raises(CommandTimeout):
        iperf_cmd(timeout=0.2)
    assert iperf_cmd._cmd_output_started is True


def test_iperf_not_timeout_on_version_not_provied_but_prompt(buffer_connection):
    iperf_cmd = Iperf3(connection=buffer_connection.moler_connection, options='--blabla')
    command_output = """xyz@debian:~$ iperf3 --version
Last login: Thu Nov 14 16:35:41 2024 from 127.0.0.1
xyz@debian:~$
xyz@debian:~$echo DETECTING PROMPT
DETECTING PROMPT
xyz@debian:~$"""
    iperf_cmd.command_string = 'iperf3 --version'
    buffer_connection.remote_inject_response([command_output])
    assert 'iperf3 --version' == iperf_cmd.command_string
    iperf_cmd.terminating_timeout = 0
    iperf_cmd(timeout=0.2)
    assert iperf_cmd._cmd_output_started is True

iperf_server_output_start = """
xyz@debian:~$ iperf3 -s -i 1
-----------------------------------------------------------
Server listening on 5201
-----------------------------------------------------------
Accepted connection from 127.0.0.1, port 40530
[  5] local 127.0.0.1 port 5201 connected to 127.0.0.1 port 34761
"""


def test_iperf_publishes_records_to_subscribed_observers(buffer_connection):
    from moler.cmd.unix import iperf3
    conn = buffer_connection
    conn.remote_inject_response([iperf_server_output_start])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              options='-s -i 1')
    iperf_stats = []

    def iperf_observer(from_client, to_server, data_record=None, report=None):
        iperf_record = {}
        iperf_record['from_client'] = from_client
        iperf_record['to_server'] = to_server
        if data_record:
            iperf_record['data_record'] = data_record
        if report:
            iperf_record['report'] = report
        iperf_stats.append(iperf_record)

    iperf_cmd.subscribe(subscriber=iperf_observer)
    iperf_cmd.start()

    assert len(iperf_stats) == 0
    conn.remote_inject_line(
        "[ ID] Interval           Transfer     Bitrate         Jitter    Lost/Total Datagrams")
    assert len(iperf_stats) == 0
    conn.remote_inject_line(
        "[  5]   0.00-1.00   sec   129 KBytes  1.06 Mbits/sec  0.015 ms  0/6 (0%)")
    assert len(iperf_stats) == 1
    assert iperf_stats[0]['from_client'] == '34761@127.0.0.1'
    assert iperf_stats[0]['to_server'] == '5201@127.0.0.1'
    # iperf progress lines produce data_records
    assert iperf_stats[0]['data_record'] == {'Bitrate': 132500,
                                             'Bitrate Raw': '1.06 Mbits/sec',
                                             'Interval': (0.0, 1.0),
                                             'Jitter': 0.015,
                                             'Jitter Raw': '0.015 ms',
                                             'Lost_Datagrams_ratio': '0%',
                                             'Lost_vs_Total_Datagrams': (0, 6),
                                             'Transfer': 132096,
                                             'Transfer Raw': '129 KBytes'}
    conn.remote_inject_line(
        "[  5]   1.00-2.00   sec   129 KBytes  1.06 Mbits/sec  0.016 ms  0/6 (0%)")
    assert len(iperf_stats) == 2
    assert ('data_record' in iperf_stats[-1]
            ) and ('report' not in iperf_stats[-1])
    conn.remote_inject_line(
        "[  5]   9.00-10.00  sec   129 KBytes  1.06 Mbits/sec  0.022 ms  0/6 (0%)")
    time.sleep(0.1)
    assert len(iperf_stats) == 3
    assert ('data_record' in iperf_stats[-1]
            ) and ('report' not in iperf_stats[-1])
    # last line of iperf progress produces report
    conn.remote_inject_line(
        "[  5]   0.00-10.04  sec  1.26 MBytes  1.05 Mbits/sec  0.022 ms  0/60 (0%)  receiver")
    assert len(iperf_stats) == 4
    assert 'data_record' not in iperf_stats[-1]
    assert iperf_stats[-1]['from_client'] == '127.0.0.1'
    assert iperf_stats[-1]['to_server'] == '5201@127.0.0.1'
    assert iperf_stats[-1]['report'] == {'Bitrate': 131250,
                                         'Bitrate Raw': '1.05 Mbits/sec',
                                         'Interval': (0.0, 10.04),
                                         'Jitter': 0.022,
                                         'Jitter Raw': '0.022 ms',
                                         'Lost_Datagrams_ratio': '0%',
                                         'Lost_vs_Total_Datagrams': (0, 60),
                                         'Transfer': 1321205,
                                         'Transfer Raw': '1.26 MBytes'}
    iperf_cmd.cancel()


def test_iperf_publishes_only_summary_records_when_handling_parallel_clients(buffer_connection):
    from moler.cmd.unix import iperf3
    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_multiple_connections_udp_server])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections_udp_server)
    expected_result = iperf3.COMMAND_RESULT_multiple_connections_udp_server
    iperf_stats = {}
    iperf_report = {}

    def iperf_observer(from_client, to_server, data_record=None, report=None):
        conn_name = (from_client, to_server)
        if data_record:
            if conn_name not in iperf_stats:
                iperf_stats[conn_name] = []
            iperf_stats[conn_name].append(data_record)
        if report:
            iperf_report[conn_name] = report

    iperf_cmd.subscribe(subscriber=iperf_observer)
    iperf_cmd()
    # published stats should be as
    summary_conn_name = ('multiport@127.0.0.1', '5016@127.0.0.1')
    client_conn_name = ('127.0.0.1', '5016@127.0.0.1')
    assert client_conn_name in iperf_report
    assert summary_conn_name in iperf_stats
    assert len(iperf_stats.keys()) == 1
    assert iperf_stats[summary_conn_name] == expected_result['CONNECTIONS'][summary_conn_name][:-1]

    buffer_connection.remote_inject_response(
        [iperf3.COMMAND_OUTPUT_multiple_connections_udp_client])
    iperf_cmd = iperf3.Iperf3(connection=buffer_connection.moler_connection,
                              **iperf3.COMMAND_KWARGS_multiple_connections_udp_client)
    expected_result = iperf3.COMMAND_RESULT_multiple_connections_udp_client
    iperf_stats = {}
    iperf_report = {}
    iperf_cmd.subscribe(subscriber=iperf_observer)
    iperf_cmd()
    # published stats should be as
    summary_conn_name = ('multiport@127.0.0.1', '5016@127.0.0.1')
    client_conn_name = ('127.0.0.1', '5016@127.0.0.1')
    expected_client_result = expected_result['CONNECTIONS'][summary_conn_name][:-2]
    expected_client_result.append(
        expected_result['CONNECTIONS'][summary_conn_name][-1])
    assert client_conn_name in iperf_report
    assert summary_conn_name in iperf_stats
    assert len(iperf_stats.keys()) == 1
    assert iperf_stats[summary_conn_name] == expected_client_result


@pytest.fixture
def command_output_and_expected_result_on_bind_failed():
    output = """xyz@debian>iperf3 -s
iperf3: error - unable to start listener for connections: Address already in use
iperf3: exiting
xyz@debian>"""
    result = dict()
    return output, result


@pytest.fixture
def command_output_and_expected_result_on_connect_failed():
    output = """xyz@debian>iperf3 -c 10.156.236.132
iperf3: error - unable to connect to server: Connection refused
xyz@debian>"""
    result = dict()
    return output, result


@pytest.fixture
def command_output_and_expected_result_on_iperf_problem():
    output = """xyz@debian>iperf3 -i
iperf: option requires an argument -- i
xyz@debian>"""
    result = dict()
    return output, result
