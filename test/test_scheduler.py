# -*- coding: utf-8 -*-
"""
Testing of Scheduler.
"""
__author__ = 'Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'marcin.usielski@nokia.com'

from moler.scheduler import Scheduler
from moler.exceptions import WrongUsage
from moler.util.moler_test import MolerTest
import time
import pytest
import platform
import asyncio


pytestmark = pytest.mark.skipif('Linux' != platform.system(), reason="Skip for no Linux system.")


def test_job():
    values = {'number': 0}
    job = Scheduler.get_job(callback=callback, interval=0.1, callback_params={'param_dict': values})
    job.start()
    MolerTest.sleep(seconds=0.22)
    job.cancel()
    assert(2 == values['number'])


def test_exception_in_job_canceled():
    values = {'number': 0}
    job = Scheduler.get_job(callback=callback_exception, interval=0.1, callback_params={'param_dict': values}, cancel_on_exception=True)
    job.start()
    MolerTest.sleep(seconds=0.32)
    job.cancel()
    assert(2 == values['number'])


def test_exception_in_job_not_canceled():
    values = {'number': 0}
    job = Scheduler.get_job(callback=callback_exception, interval=0.1, callback_params={'param_dict': values}, cancel_on_exception=False)
    job.start()
    MolerTest.sleep(seconds=0.32)
    job.cancel()
    assert(3 == values['number'])


def test_long_job():
    values = {'number': 0}
    job = Scheduler.get_job(callback=callback_long, interval=0.1, callback_params={'param_dict': values}, cancel_on_exception=True)
    job.start()
    MolerTest.sleep(seconds=0.45)
    job.cancel()
    assert(2 == values['number'])


def test_wrong_usage():
    with pytest.raises(WrongUsage):
        Scheduler.change_kind('wrong_kind')


def test_job_callback_as_method():
    values = {'number': 0}
    obj = CallbackTest()
    job = Scheduler.get_job(callback=obj.callback_method, interval=0.1, callback_params={'param_dict': values})
    job.start()
    MolerTest.sleep(seconds=0.22)
    job.cancel()
    assert(2 == values['number'])
    assert(6 == obj.counter)


def test_2_jobs_concurrently():
    job_tick = 0.1
    double_job_tick = 2. * job_tick
    values_1 = {'number': 0}
    values_2 = {'number': 0}
    job1 = Scheduler.get_job(callback=callback, interval=job_tick, callback_params={'param_dict': values_1})
    job2 = Scheduler.get_job(callback=callback, interval=double_job_tick, callback_params={'param_dict': values_2})
    job1.cancel()
    job1.start()
    job1.start()
    job2.start()
    MolerTest.sleep(seconds=2. * double_job_tick + job_tick / 2.)
    job1.cancel()
    job1.cancel()
    job2.cancel()
    assert (2 == values_2['number'])
    assert (4 == values_1['number'])


def test_thread_test_job():
    Scheduler.change_kind("thread")
    values = {'number': 0}
    job = Scheduler.get_job(callback=callback, interval=0.1, callback_params={'param_dict': values})
    job.start()
    time.sleep(0.38)
    job.cancel()
    Scheduler.change_kind()  # Set the default
    assert (3 == values['number'])



def test_asyncio_test_job():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # No working asyncio
    Scheduler.change_kind("asyncio")
    values = {'number': 0}
    job = Scheduler.get_job(callback=callback, interval=0.1, callback_params={'param_dict': values})
    job.start()
    loop.run_until_complete(asyncio.sleep(0.23))
    job.cancel()
    loop.stop()
    Scheduler.change_kind()  # Set the default
    assert (2 == values['number'])


def test_cannot_create_more_objects():
    with pytest.raises(WrongUsage):
        Scheduler()
        Scheduler()


def callback(param_dict):
    param_dict['number'] += 1


def callback_long(param_dict):
    param_dict['number'] += 1
    MolerTest.sleep(seconds=0.12)


def callback_exception(param_dict):
    param_dict['number'] += 1
    if param_dict['number'] == 2:
        return 2/0


class CallbackTest(object):
    def __init__(self):
        super(CallbackTest, self).__init__()
        self.counter = 0

    def callback_method(self, param_dict):
        param_dict['number'] += 1
        self.counter += 3
