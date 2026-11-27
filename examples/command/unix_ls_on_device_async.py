import asyncio
import logging
import sys
import moler.config.runners
from moler.config import load_config
from moler.device.device import DeviceFactory


def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s |%(name)-45s | %(threadName)22s |%(message)s',
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


# configure library directly from dict
load_config(config={'DEVICES': {'DEFAULT_CONNECTION':
                                    {'CONNECTION_DESC': {'io_type': 'terminal', 'variant': 'asyncio-in-thread'}},
                                'RebexTestMachine':
                                    {'DEVICE_CLASS': 'moler.device.unixremote.UnixRemote',
                                     'CONNECTION_HOPS': {'UNIX_LOCAL':
                                                             {'UNIX_REMOTE':
                                                                  {'execute_command': 'ssh',
                                                                   'command_params': {'expected_prompt': 'demo@',
                                                                                      'host': 'test.rebex.net',
                                                                                      'login': 'demo',
                                                                                      'password': 'password',
                                                                                      'set_timeout': None}}}}}}},
            config_type='dict')

configure_logging()
moler.config.runners.set_default_variant(variant='asyncio-in-thread')


# TODO: problem for {'CONNECTION_DESC': {'io_type': 'terminal', 'variant': 'asyncio'}},
# TODO: get_device() uses io.open() and not await open()
# async def do_async_device_ls():
#     remote_unix = await DeviceFactory.get_device_coro(name='RebexTestMachine')
#     remote_unix = await AsyncDeviceFactory.get_device(name='RebexTestMachine')
#     # TODO: + textualdevice should have separate __init__()   and   async def open()
#     await remote_unix.goto_state_coro(state="UNIX_REMOTE")
#     ls_cmd = remote_unix.get_cmd(cmd_name="ls", cmd_params={"options": "-l"})
#     remote_files = await ls_cmd
#
# run_via_asyncio(do_async_device_ls())


remote_unix = DeviceFactory.get_device(name='RebexTestMachine')  # it starts in local shell
remote_unix.goto_state(state="UNIX_REMOTE")                      # make it go to remote shell

ls_cmd = remote_unix.get_cmd(cmd_name="ls", cmd_params={"options": "-l"})

remote_files = ls_cmd()

if 'readme.txt' in remote_files['files']:
    print("readme.txt file:")
    readme_file_info = remote_files['files']['readme.txt']
    for attr in readme_file_info:
        print(f"  {attr:<18}: {readme_file_info[attr]}")

# result:
"""
readme.txt file:
  permissions       : -rw-------
  hard_links_count  : 1
  owner             : demo
  group             : users
  size_raw          : 403
  size_bytes        : 403
  date              : Apr 08  2014
  name              : readme.txt
"""
