# -*- coding: utf-8 -*-
"""
asyncio_common.py
~~~~~~~~~~~~~~~~~

Common part for asyncio examples.
"""

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2018, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

import logging
import sys
import asyncio


def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s |%(name)-45s | %(threadName)12s |%(message)s',
        # format=' |%(name)-45s | %(threadName)12s |%(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stderr,
    )


def _cleanup_remaining_tasks(loop, logger):
    # https://stackoverflow.com/questions/30765606/whats-the-correct-way-to-clean-up-after-an-interrupted-event-loop
    # https://medium.com/python-pandemonium/asyncio-coroutine-patterns-beyond-await-a6121486656f
    # Handle shutdown gracefully by waiting for all tasks to be cancelled
    not_done_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
    if not_done_tasks:
        logger.info("cancelling all remaining tasks")
        # NOTE: following code cancels all tasks - possibly not ours as well
        remaining_tasks = asyncio.gather(*not_done_tasks, return_exceptions=True)
        remaining_tasks.add_done_callback(lambda t: loop.stop())
        logger.debug(f"remaining tasks = {not_done_tasks}")
        remaining_tasks.cancel()

        # Keep the event loop running until it is either destroyed or all
        # tasks have really terminated
        loop.run_until_complete(remaining_tasks)


def run_via_asyncio(async_to_run, debug_event_loop=False):
    logger = logging.getLogger('asyncio.main')

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    event_loop.set_debug(enabled=debug_event_loop)
    try:
        logger.info("starting events loop ...")
        event_loop.run_until_complete(async_to_run)

        _cleanup_remaining_tasks(loop=event_loop, logger=logger)

    finally:
        logger.info("closing events loop ...")
        event_loop.close()
        logger.info("... events loop closed")
