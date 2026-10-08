[![image](https://img.shields.io/badge/pypi-v4.13.1-blue.svg)](https://pypi.org/project/moler/)
[![image](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://pypi.org/project/moler/)
[![Build Status](https://github.com/nokia/moler/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/nokia/moler/actions)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](./LICENSE)

# Table of Contents
1. [Changelog](#changelog)
2. [Moler info](#moler)
3. [Moler usage examples](#moler-usage-examples)
4. [API design reasoning](#api-design-reasoning)
5. [Designed API](#designed-api)

# Changelog
View our [chronological list](https://github.com/nokia/moler/CHANGELOG.md) of user-facing changes, large and small, made to the Moler project.

![moler logo](https://i.imgur.com/mkPutdC.png)
# Moler
Moler ([name origin](https://github.com/nokia/moler/wiki#moler-name-origin)) is a Python library
that provides "bricks" for building  automated tests.
All these "bricks" have clearly defined responsibilities, have similar API,
follow same construction pattern (so new ones are easy to create).

Here they are:
* Commands as self-reliant object
  * to allow for command triggering and parsing encapsulated in single object (lower maintenance cost)
* Event observers & callbacks (alarms are events example)
  * to allow for online reaction (not offline postprocessing)
* Run observers/commands in the background
  * to allow for test logic decomposition into multiple commands running in parallel
  * to allow for handling unexpected system behavior (reboots, alarms)
* State machines -> automatic auto-connecting after dropped connection
  * to increase framework auto-recovery and help in troubleshooting "what went wrong"
* Automatic logging of all connections towards devices used by tests
  * to decrease investigation time by having logs focused on different parts of system under test

# Moler usage examples
Let's see Moler in action. Here is hypothetical use case: "find PIDs of all python processes":

```python

from moler.config import load_config
from moler.device import DeviceFactory

load_config(config='my_devices.yml')                    # description of available devices
my_unix = DeviceFactory.get_device(name='MyMachine')    # take specific device out of available ones
ps_cmd = my_unix.get_cmd(cmd_name="ps",                 # take command of that device
                         cmd_params={"options": "-ef"})

processes_info = ps_cmd()                               # run the command, it returns result
for proc_info in processes_info:
    if 'python' in proc_info['CMD']:
        print("PID: {info[PID]} CMD: {info[CMD]}".format(info=proc_info))
```

* To have command we ask device "give me such command".
* To run command we just call it as function (command object is callable)
* What command returns is usually dict or list of dicts - easy to process

Above code displays:

```bash

    PID: 1817 CMD: /usr/bin/python /usr/share/system-config-printer/applet.py
    PID: 21825 CMD: /usr/bin/python /home/gl/moler/examples/command/unix_ps.py
```

How does it know what `'MyMachine'` means? Code loads definition from `my_devices.yml` configuration file:

```yaml

    DEVICES:

      MyMachine:
        DEVICE_CLASS: moler.device.unixlocal.UnixLocal

      RebexTestMachine:
        DEVICE_CLASS: moler.device.unixremote.UnixRemote
        CONNECTION_HOPS:
          UNIX_LOCAL:                # from state
            UNIX_REMOTE:             # to state
              execute_command: ssh   # via command
              command_params:        # with params
                expected_prompt: demo@
                host: test.rebex.net
                login: demo
                password: password
                set_timeout: None   # remote doesn't support: export TMOUT
```

We have remote machine in our config. Let's check if there is 'readme.txt' file
on that machine (and some info about the file):

```python
from moler.device import DeviceFactory
remote_unix = DeviceFactory.get_device(name='RebexTestMachine')  # it starts in local shell
remote_unix.goto_state(state="UNIX_REMOTE")                      # make it go to remote shell

ls_cmd = remote_unix.get_cmd(cmd_name="ls", cmd_params={"options": "-l"})

remote_files = ls_cmd()

if 'readme.txt' in remote_files['files']:
    print("readme.txt file:")
    readme_file_info = remote_files['files']['readme.txt']
    for attr in readme_file_info:
        print("  {:<18}: {}".format(attr, readme_file_info[attr]))
```

As you may noticed device is state machine. State transitions are defined inside
configuration file under `CONNECTION_HOPS`. Please note, that it is only config file who
knows "I need to use ssh to be on remote" - client code just says "go to remote".
Thanks to that you can exchange "how to reach remote" without any change in main code.

Above code displays:

```bash

    readme.txt file:
      permissions       : -rw-------
      hard_links_count  : 1
      owner             : demo
      group             : users
      size_raw          : 403
      size_bytes        : 403
      date              : Apr 08  2014
      name              : readme.txt
```

How about doing multiple things in parallel. Let's ping google
while asking test.rebex.net about readme.txt file:

```python
from moler.device import DeviceFactory
my_unix = DeviceFactory.get_device(name='MyMachine')
host = 'www.google.com'
ping_cmd = my_unix.get_cmd(cmd_name="ping", cmd_params={"destination": host, "options": "-w 6"})

remote_unix = DeviceFactory.get_device(name='RebexTestMachine')
remote_unix.goto_state(state="UNIX_REMOTE")
ls_cmd = remote_unix.get_cmd(cmd_name="ls", cmd_params={"options": "-l"})

print("Start pinging {} ...".format(host))
ping_cmd.start()                                # run command in background
print("Let's check readme.txt at {} while pinging {} ...".format(remote_unix.name, host))

remote_files = ls_cmd()                         # foreground "run in the meantime"
file_info = remote_files['files']['readme.txt']
print("readme.txt file: owner={fi[owner]}, size={fi[size_bytes]}".format(fi=file_info))

ping_stats = ping_cmd.await_done(timeout=6)     # await background command
print("ping {}: {}={}, {}={} [{}]".format(host,'packet_loss',
                                          ping_stats['packet_loss'],
                                          'time_avg',
                                          ping_stats['time_avg'],
                                          ping_stats['time_unit']))
```

```log
Start pinging www.google.com ...
Let's check readme.txt at RebexTestMachine while pinging www.google.com ...
readme.txt file: owner=demo, size=403
ping www.google.com: packet_loss=0, time_avg=35.251 [ms]
```

Besides being callable command-object works as "Future" (result promise).
You can start it in background and later await till it is done to grab result.

If we enhance our configuration with logging related info:

```yaml
    LOGGER:
      PATH: ./logs
      DATE_FORMAT: "%H:%M:%S"
```

then above code will automatically create Molers' main log (`moler.log`)
which shows activity on all devices:

```log
22:30:19.723 INFO       moler               |More logs in: ./logs
22:30:19.747 INFO       MyMachine           |Connection to: 'MyMachine' has been opened.
22:30:19.748 INFO       MyMachine           |Changed state from 'NOT_CONNECTED' into 'UNIX_LOCAL'
22:30:19.866 INFO       MyMachine           |Event 'moler.events.unix.wait4prompt.Wait4prompt':'[re.compile('^moler_bash#')]' started.
22:30:19.901 INFO       RebexTestMachine    |Connection to: 'RebexTestMachine' has been opened.
22:30:19.901 INFO       RebexTestMachine    |Changed state from 'NOT_CONNECTED' into 'UNIX_LOCAL'
22:30:19.919 INFO       RebexTestMachine    |Event 'moler.events.unix.wait4prompt.Wait4prompt':'[re.compile('demo@')]' started.
22:30:19.920 INFO       RebexTestMachine    |Event 'moler.events.unix.wait4prompt.Wait4prompt':'[re.compile('^moler_bash#')]' started.
22:30:19.921 INFO       RebexTestMachine    |Command 'moler.cmd.unix.ssh.Ssh':'TERM=xterm-mono ssh -l demo test.rebex.net' started.
22:30:19.921 INFO       RebexTestMachine    |TERM=xterm-mono ssh -l demo test.rebex.net
22:30:20.763 INFO       RebexTestMachine    |*********
22:30:20.909 INFO       RebexTestMachine    |Changed state from 'UNIX_LOCAL' into 'UNIX_REMOTE'
22:30:20.917 INFO       RebexTestMachine    |Command 'moler.cmd.unix.ssh.Ssh' finished.
22:30:20.919 INFO       MyMachine           |Command 'moler.cmd.unix.ping.Ping':'ping www.google.com -w 6' started.
22:30:20.920 INFO       MyMachine           |ping www.google.com -w 6
22:30:20.920 INFO       RebexTestMachine    |Command 'moler.cmd.unix.ls.Ls':'ls -l' started.
22:30:20.922 INFO       RebexTestMachine    |ls -l
22:30:20.985 INFO       RebexTestMachine    |Command 'moler.cmd.unix.ls.Ls' finished.
22:30:26.968 INFO       MyMachine           |Command 'moler.cmd.unix.ping.Ping' finished.
22:30:26.992 INFO       RebexTestMachine    |Event 'moler.events.unix.wait4prompt.Wait4prompt': '[re.compile('^moler_bash#')]' finished.
22:30:27.011 INFO       RebexTestMachine    |Event 'moler.events.unix.wait4prompt.Wait4prompt': '[re.compile('demo@')]' finished.
22:30:27.032 INFO       MyMachine           |Event 'moler.events.unix.wait4prompt.Wait4prompt': '[re.compile('^moler_bash#')]' finished.

```

As you may noticed main log shows code progress from high-level view - data
on connections are not visible, just activity of commands running on devices.

If you want to see in details what has happened on each device - you have it in device logs.
Moler creates log per each device
`moler.RebexTestMachine.log`:

```log
22:30:19.901  |Changed state from 'NOT_CONNECTED' into 'UNIX_LOCAL'
22:30:19.902 <|
22:30:19.919  |Event 'moler.events.unix.wait4prompt.Wait4prompt':'[re.compile('demo@')]' started.
22:30:19.920  |Event 'moler.events.unix.wait4prompt.Wait4prompt':'[re.compile('^moler_bash#')]' started.
22:30:19.921  |Command 'moler.cmd.unix.ssh.Ssh':'TERM=xterm-mono ssh -l demo test.rebex.net' started.
22:30:19.921 >|TERM=xterm-mono ssh -l demo test.rebex.net

22:30:19.924 <|TERM=xterm-mono ssh -l demo test.rebex.net

22:30:20.762 <|Password:
22:30:20.763 >|*********
22:30:20.763 <|

22:30:20.908 <|Welcome to Rebex Virtual Shell!
              |For a list of supported commands, type 'help'.
              |demo@ETNA:/$
22:30:20.909  |Changed state from 'UNIX_LOCAL' into 'UNIX_REMOTE'
22:30:20.917  |Command 'moler.cmd.unix.ssh.Ssh' finished.
22:30:20.920  |Command 'moler.cmd.unix.ls.Ls':'ls -l' started.
22:30:20.922 >|ls -l

22:30:20.974 <|ls -l

22:30:20.978 <|drwx------ 2 demo users          0 Jul 26  2017 .

22:30:20.979 <|drwx------ 2 demo users          0 Jul 26  2017 ..
              |drwx------ 2 demo users          0 Dec 03  2015 aspnet_client
              |drwx------ 2 demo users          0 Oct 27  2015 pub
              |-rw------- 1 demo users        403 Apr 08  2014 readme.txt
              |demo@ETNA:/$
22:30:20.985  |Command 'moler.cmd.unix.ls.Ls' finished.
22:30:26.992  |Event 'moler.events.unix.wait4prompt.Wait4prompt': '[re.compile('^moler_bash#')]' finished.
22:30:27.011  |Event 'moler.events.unix.wait4prompt.Wait4prompt': '[re.compile('demo@')]' finished.
```

and `moler.MyMachine.log`:

```log
22:30:19.748  |Changed state from 'NOT_CONNECTED' into 'UNIX_LOCAL'
22:30:19.748 <|
22:30:19.866  |Event 'moler.events.unix.wait4prompt.Wait4prompt':'[re.compile('^moler_bash#')]' started.
22:30:20.919  |Command 'moler.cmd.unix.ping.Ping':'ping www.google.com -w 6' started.
22:30:20.920 >|ping www.google.com -w 6

22:30:20.921 <|ping www.google.com -w 6

22:30:20.959 <|PING www.google.com (216.58.215.68) 56(84) bytes of data.
22:30:20.960 <|

22:30:21.000 <|64 bytes from waw02s16-in-f4.1e100.net (216.58.215.68): icmp_seq=1 ttl=51 time=40.1 ms
22:30:21.001 <|

22:30:21.992 <|64 bytes from waw02s16-in-f4.1e100.net (216.58.215.68): icmp_seq=2 ttl=51 time=31.0 ms

22:30:22.999 <|64 bytes from waw02s16-in-f4.1e100.net (216.58.215.68): icmp_seq=3 ttl=51 time=36.5 ms

22:30:23.996 <|64 bytes from waw02s16-in-f4.1e100.net (216.58.215.68): icmp_seq=4 ttl=51 time=31.4 ms

22:30:24.996 <|64 bytes from waw02s16-in-f4.1e100.net (216.58.215.68): icmp_seq=5 ttl=51 time=29.8 ms

22:30:26.010 <|64 bytes from waw02s16-in-f4.1e100.net (216.58.215.68): icmp_seq=6 ttl=51 time=42.4 ms

22:30:26.960 <|
              |--- www.google.com ping statistics ---
              |6 packets transmitted, 6 received, 0% packet loss, time 5007ms
              |rtt min/avg/max/mdev = 29.888/35.251/42.405/4.786 ms
              |moler_bash#
22:30:26.968  |Command 'moler.cmd.unix.ping.Ping' finished.
22:30:27.032  |Event 'moler.events.unix.wait4prompt.Wait4prompt': '[re.compile('^moler_bash#')]' finished.
```

If the log files are too large you can split files.

The log files can be split by size. For example let's assume we want split log files by 5 MB (5242880 bytes) and we want
to keep maximum 999 files:
```yaml
    LOGGER:
      PATH: ./logs
      DATE_FORMAT: "%H:%M:%S"
      LOG_ROTATION:
        KIND: size
        INTERVAL: 5242880
        BACKUP_COUNT: 999  # Default value


```

The log files can be split by time. For example let's assume we want split log files every 30 minutes (1800 seconds)
 and we want to keep maximum 999 files (default value):

```yaml
    LOGGER:
      PATH: ./logs
      DATE_FORMAT: "%H:%M:%S"
      LOG_ROTATION:
        KIND: time
        INTERVAL: 1800
        BACKUP_COUNT: 999  # Default value
```

For space saving Moler can compress the logs after rotation. The external tool is used. Let's use the above examples
to show how to compress logs:

```yaml
    LOGGER:
      PATH: ./logs
      DATE_FORMAT: "%H:%M:%S"
      LOG_ROTATION:
        KIND: size
        INTERVAL: 5242880
        BACKUP_COUNT: 999  # Default value
        COMPRESS_AFTER_ROTATION: True  # Default is False
        COMPRESS_COMMAND: "zip -9mq {compressed} {log_input}"  # Default value
        COMPRESSED_FILE_EXTENSION: ".zip"  # Default value


```

```yaml
    LOGGER:
      PATH: ./logs
      DATE_FORMAT: "%H:%M:%S"
      LOG_ROTATION:
        KIND: time
        INTERVAL: 1800
        BACKUP_COUNT: 999  # Default value
        COMPRESS_COMMAND: "zip -9mq {compressed} {log_input}"  # Default value
        COMPRESSED_FILE_EXTENSION: ".zip"  # Default value
```

In a script we can also disable logging from device. Please use it very carefully. Investigation any issue may be
 impossible if we don't have full logs.

```python
from moler.device import DeviceFactory
my_unix = DeviceFactory.get_device(name='MyMachine')

my_unix.disbale_logging()  # to disable logging on device

my_unix.enable_logging()  # to enable logging on device
```

In a script you can add suffix to all log files or only to files for specific devices. with disable logging from device.

```python
from moler.device import DeviceFactory
from moler.config.loggers import change_logging_suffix
change_logging_suffix(".suffix1")  # all log files with suffix
change_logging_suffix(None)  # all log files without suffx

my_unix = DeviceFactory.get_device(name='MyMachine')

my_unix.set_logging_suffix("device_suffix")  # to add suffix to filename with logs

my_unix.set_logging_suffix(None)  # to remove suffix from filename with logs
```

Previous examples ask device to create command. We can also create command ourselves
giving it connection to operate on:

```python

import time
from moler.cmd.unix.ping import Ping
from moler.connection_factory import get_connection

host = 'www.google.com'
terminal = get_connection(io_type='terminal', variant='threaded')  # take connection
with terminal.open():
    ping_cmd = Ping(connection=terminal.moler_connection,
                    destination=host, options="-w 6")
    print("Start pinging {} ...".format(host))
    ping_cmd.start()
    print("Doing other stuff while pinging {} ...".format(host))
    time.sleep(3)
    ping_stats = ping_cmd.await_done(timeout=4)
    print("ping {}: {}={}, {}={} [{}]".format(host,'packet_loss',
                                              ping_stats['packet_loss'],
                                              'time_avg',
                                              ping_stats['time_avg'],
                                              ping_stats['time_unit']))
```

Please note also that connection is context manager doing open/close actions.


```bash

    Start pinging www.google.com ...
    Doing other stuff while pinging www.google.com ...
    ping www.google.com: packet_loss=0, time_avg=50.000 [ms]
```

## Reuse freedom
Library gives you freedom which part you want to reuse. We are fans of "take what you need only".
* You may use configuration files or configure things by Python calls.

   ```python
   from moler.config import load_config
   load_config(config={'DEVICES': {'MyMachine': {'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal'}}})
   ```
* You may use devices or create commands manually
* You can take connection or build it yourself:

   ```python
   from moler.threaded_moler_connection import ThreadedMolerConnection
   from moler.io.raw.terminal import ThreadedTerminal

   terminal_connection = ThreadedTerminal(moler_connection=ThreadedMolerConnection())
   ```
* You can even install your own implementation in place of default implementation per connection type

# API design reasoning
The main goal of command is its usage simplicity: just run it and give me back its result.

Command hides from its caller:
* a way how it realizes "runs"
* how it gets data of output to be parsed
* how it parses that data

Command shows to its caller:
* API to start/stop it or await for its completion
* API to query for its result or result readiness

Command works as [Futures and promises](https://en.wikipedia.org/wiki/Futures_and_promises)

After starting, we await for its result which is parsed out command output provided usually as dict.
Running that command and parsing its output may take some time, so till that point result computation is yet incomplete.

## Command as future
* it starts some command on device/shell over connection
  (as future-function starts its execution)
* it parses data incoming over such connection
  (as future-function does its processing)
* it stores result of that parsing
  (as future-function concludes in calculation result)
* it provides means to return that result
  (as future-function does via 'return' or 'yield' statement)
* its result is not ready "just-after" calling command
  (as it is with future in contrast to function)

So command should have future API.

Quote from **_"Professional Python"_** by **Luke Sneeringer**:
> The Future is a standalone object. It is independent of the actual function that is running.
> It does nothing but store the state and result information.

Command differs in that it is both:
* function-like object performing computation
* future-like object storing result of that computation.

## Command vs. Connection-observer
Command is just "active version" of connection observer.

Connection observer is passive since it just observes connection for some data;
data that may just asynchronously appear (alarms, reboots or anything you want).
Intention here is split of responsibility: one observer is looking for alarms,
another one for reboots.

Command is active since it actively triggers some output on connection
by sending command-string over that connection. So, it activates some action
on device-behind-connection. That action is "command" in device terminology.
Like `ping` on bash console/device. And it produces that "command" output.
That output is what Moler's Command as connection-observer is looking for.

## Most well known Python's futures
* [concurrent.futures.Future](https://docs.python.org/3/library/concurrent.futures.html)
* [asyncio.Future](https://docs.python.org/3/library/asyncio-task.html#future)

| API                     | concurrent.futures.Future                   | asyncio.Future                                      |
| :---------------------- | :------------------------------------------ | :-------------------------------------------------- |
| storing result          | :white_check_mark: `set_result()`           | :white_check_mark: `set_result()`                   |
| result retrieval        | :white_check_mark: `result()`               | :white_check_mark: `result()`                       |
| storing failure cause   | :white_check_mark: `set_exception()`        | :white_check_mark: `set_exception()`                |
| failure cause retrieval | :white_check_mark: `exception()`            | :white_check_mark: `exception()`                    |
| stopping                | :white_check_mark: `cancel()`               | :white_check_mark: `cancel()`                       |
| check if stopped        | :white_check_mark: `cancelled()`            | :white_check_mark: `cancelled()`                    |
| check if running        | :white_check_mark: `running()`              | :no_entry_sign: `(but AbstractEventLoop.running())` |
| check if completed      | :white_check_mark: `done()`                 | :white_check_mark: `done()`                         |
| subscribe completion    | :white_check_mark: `add_done_callback()`    | :white_check_mark: `add_done_callback()`            |
| unsubscribe completion  | :no_entry_sign:                             | :white_check_mark: `remove_done_callback()`         |

Starting callable to be run "as future" is done by entities external to future-object

| API              | concurrent.futures<br>start via Executor objects (thread/proc) | asyncio<br>start via module-lvl functions or ev-loop |
| ---------------- | ---------------------------------------- | ---------------------------------------------- |
| start callable   | submit(fn, *args, **kwargs)<br>Schedules callable to be executed as<br>fn(*args **kwargs) -> Future | ensure_future(coro_or_future) -> Task<br>future = run_coroutine_threadsafe(coro, loop) |
| start same callable<br>on data iterator | map(fn, *iterables, timeout) -> iterator | join_future = asyncio.gather(*map(f, iterable))<br>loop.run_until_complete(join_future)|

Awaiting completion of future is done by entities external to future-object

| API               | concurrent.futures<br>awaiting by module level functions | asyncio<br>awaiting by module-lvl functions or ev-loop |
| ----------------- | ------------------------------------------ | -------------------------------------------- |
| await completion  |  done, not_done = wait(futures, timeout) -> futures | done, not_done = await wait(futures)<br>results = await gather(futures)<br>result = await future<br>result = yield from future<br>result = await coroutine<br>result = yield from coroutine<br>result = yield from wait_for(future, timeout)<br>loop.run_until_complete(future) -> blocking run |
| process as they<br>complete | for done in as_completed(futures, timeout) -> futures | for done in as_completed(futures, timeout) -> futures |

## Fundamental difference of command
Contrary to **concurrent.futures** and **asyncio** we don't want command to be run by some external entity.
We want it to be self-executable for usage simplicity.
We want to take command and just say to it:
* **"run"** or **"run in background"**
* and not **"Hi, external runner, would you run/run-background that command for me"**

# Designed API
1. create command object
``` python
command = Command()
```

2. run it synchronously/blocking and get result in one shot behaves like function call since Command is callable.

Run-as-callable gives big advantage since it fits well in python ecosystem.
``` python
result = command()
```
function example:
``` python
map(ping_cmd, all_machines_to_validate_reachability)
```

3. run it asynchronously/nonblocking
``` python
command_as_future = command.start()
```

4. shift from background to foreground

**asyncio:** variant looks like:
``` python
result = await future
done_futures, pending = yield from asyncio.wait(futures)
result = yield from asyncio.wait_for(future, 60.0)
```
and **concurrent.futures** variant looks like:
``` python
done_futures, pending = wait(futures)
```
Moler's API maps to above well-known API
``` python
result = command.await_done(timeout)
```
* it is "internal" to command "Hi command, that is what I want from you" (above APIs say "Hi you there, that is what I want you to do with command")
* it directly (Zen of Python) shows what we are awaiting for
* timeout is required parameter (not as in concurrent.futures) since we don't expect endless execution of command (user must know what is worst case timeout to await command completion)

# Video introduction
You can [watch videos how to use Moler on YouTube](https://www.youtube.com/channel/UCgToo2qq8kLMyEgzd4btM9g).
