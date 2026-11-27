# -*- coding: utf-8 -*-
"""Tests for pty.openpty retry when the system is out of pty devices."""

__author__ = "Marcin Usielski"
__copyright__ = "Copyright (C) 2026, Nokia"
__email__ = "marcin.usielski@nokia.com"

import sys

from unittest import mock
import pytest

from moler.io.raw import opentty_retry as pty_mod
from moler.io.raw.opentty_retry import _format_pty_usage, _get_pty_usage, openpty_with_retry


def test_openpty_retries_after_out_of_pty_devices():
    out_of_pty = OSError("out of pty devices")
    with mock.patch("moler.io.raw.opentty_retry.openpty", side_effect=[out_of_pty, (7, 8)]) as openpty:
        with mock.patch("moler.io.raw.opentty_retry.sleep") as sleep:
            master, slave = openpty_with_retry(delay_s=3.0, max_attempts=2)

    assert (master, slave) == (7, 8)
    assert openpty.call_count == 2
    sleep.assert_called_once_with(3.0)


def test_openpty_retries_on_singular_out_of_pty_device_message():
    out_of_pty = OSError("out of pty device")
    with mock.patch("moler.io.raw.opentty_retry.openpty", side_effect=[out_of_pty, (3, 4)]):
        with mock.patch("moler.io.raw.opentty_retry.sleep") as sleep:
            master, slave = openpty_with_retry()

    assert (master, slave) == (3, 4)
    sleep.assert_called_once()


def test_openpty_does_not_retry_other_oserror():
    other_error = OSError("permission denied")
    with mock.patch("moler.io.raw.opentty_retry.openpty", side_effect=other_error):
        with mock.patch("moler.io.raw.opentty_retry.sleep") as sleep:
            with pytest.raises(OSError, match="permission denied"):
                openpty_with_retry()

    sleep.assert_not_called()


def test_openpty_raises_after_retries_exhausted():
    out_of_pty = OSError("out of pty devices")
    with mock.patch("moler.io.raw.opentty_retry.openpty", side_effect=out_of_pty) as openpty:
        with mock.patch("moler.io.raw.opentty_retry.sleep") as sleep:
            with pytest.raises(OSError, match="out of pty devices"):
                openpty_with_retry(delay_s=3.0, max_attempts=2)

    assert openpty.call_count == 2
    sleep.assert_called_once_with(3.0)


def test_get_pty_usage_linux_reads_proc():
    with mock.patch.object(pty_mod.sys, "platform", "linux"):
        with mock.patch.object(pty_mod, "_read_int_file", side_effect=[10, 4096]):
            assert _get_pty_usage() == (10, 4096)


def test_get_pty_usage_darwin_reads_sysctl_and_ttys():
    with mock.patch.object(pty_mod.sys, "platform", "darwin"):
        with mock.patch.object(pty_mod, "_count_dev_ttys", return_value=12):
            with mock.patch.object(pty_mod, "_sysctl_int_byname", return_value=511):
                assert _get_pty_usage() == (12, 511)


def test_get_pty_usage_unknown_platform():
    with mock.patch.object(pty_mod.sys, "platform", "win32"):
        assert _get_pty_usage() == (None, None)


def test_format_pty_usage():
    with mock.patch.object(pty_mod, "_get_pty_usage", return_value=(10, 4096)):
        assert _format_pty_usage() == "pty devices in use: 10/4096"
    with mock.patch.object(pty_mod, "_get_pty_usage", return_value=(None, 511)):
        assert _format_pty_usage() == "pty devices in use: ?/511"
    with mock.patch.object(pty_mod, "_get_pty_usage", return_value=(None, None)):
        assert _format_pty_usage() == "pty devices in use: unknown"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux pty sysctls")
def test_get_pty_usage_linux_live():
    used, maximum = _get_pty_usage()
    assert used is not None
    assert maximum is not None
    assert maximum >= used >= 0
