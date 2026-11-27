# -*- coding: utf-8 -*-
"""
Tests for utilities related to logging.
"""

__author__ = 'Grzegorz Latuszek, Marcin Usielski'
__copyright__ = 'Copyright (C) 2019-2026, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com, marcin.usielski@nokia.com'

from unittest import mock
import sys


def test_extracting_caller_code_location():
    from moler.util.loghelper import find_caller
    if sys.version_info >= (3, 11):
        _level_to_go_up_extra = 1  # For backward compatibility
    else:
        _level_to_go_up_extra = 0
    frames_info = []

    def my_outer_fun():
        frames_info.append(find_caller(levels_to_go_up=0 + _level_to_go_up_extra))  # who called me and from which line
        my_iner_fun()

    def my_iner_fun():
        frames_info.append(find_caller(levels_to_go_up=0 + _level_to_go_up_extra))  # who called me and from which line
        frames_info.append(find_caller(levels_to_go_up=1 + _level_to_go_up_extra))  # who called him and from which line

    my_outer_fun()
    called_from_filename = frames_info[0][0]
    assert called_from_filename.endswith("test_util_loghelper.py")
    assert called_from_filename == frames_info[1][0]
    assert called_from_filename == frames_info[2][0]

    (_, called_from_lineno, called_from_fun_name) = frames_info[0]
    assert called_from_fun_name == "test_extracting_caller_code_location"
    assert called_from_lineno == 30

    (_, called_from_lineno, called_from_fun_name) = frames_info[1]
    assert called_from_fun_name == "my_outer_fun"
    assert called_from_lineno == 24

    (_, called_from_lineno, called_from_fun_name) = frames_info[2]
    assert called_from_fun_name == "test_extracting_caller_code_location"
    assert called_from_lineno == 30


def test_logging_caller_code_location():
    import logging
    from moler.util.loghelper import warning_into_logger

    logger = logging.getLogger('moler')

    def my_deprecated_fun():
        warn_about_calling("you should not call deprecated functions")

    def warn_about_calling(msg):
        warning_into_logger(logger, msg, levels_to_go_up=2)
    logged_record = [None]

    def log_record_receiver(logger, log_record):
        logged_record[0] = log_record

    with mock.patch.object(logger.__class__, "handle", new=log_record_receiver):
        my_deprecated_fun()

    assert logged_record[0] is not None
    log_record = logged_record[0]
    assert log_record.levelname == "WARNING"
    assert log_record.msg == "you should not call deprecated functions"
    assert log_record.funcName == "test_logging_caller_code_location"
    assert log_record.filename.endswith("test_util_loghelper.py")
    assert log_record.lineno == 66


def test_correct_loglevel_of_helper_logging_functions():
    import logging
    from moler.util.loghelper import error_into_logger
    from moler.util.loghelper import warning_into_logger
    from moler.util.loghelper import info_into_logger
    from moler.util.loghelper import debug_into_logger

    logger = logging.getLogger('moler')

    def fun_using_helper_logging():
        error_into_logger(logger, msg="hi")
        warning_into_logger(logger, msg="hi")
        info_into_logger(logger, msg="hi")
        debug_into_logger(logger, msg="hi")

    logged_record = []

    def log_record_receiver(logger, log_record):
        logged_record.append(log_record)

    with mock.patch.object(logger.__class__, "handle", new=log_record_receiver):
        fun_using_helper_logging()

    assert logged_record[0].levelname == "ERROR"
    assert logged_record[1].levelname == "WARNING"
    assert logged_record[2].levelname == "INFO"
    assert logged_record[3].levelname == "DEBUG"


def test_passing_extra_param_into_helper_logging_functions():
    import logging
    from moler.util.loghelper import log_into_logger

    logger = logging.getLogger('moler')

    def fun_using_helper_logging():
        log_into_logger(logger, level=logging.WARNING, msg="hi", extra={'transfer_direction': '<'})

    logged_record = []

    def log_record_receiver(logger, log_record):
        logged_record.append(log_record)

    with mock.patch.object(logger.__class__, "handle", new=log_record_receiver):
        fun_using_helper_logging()

    assert logged_record[0].transfer_direction == "<"
