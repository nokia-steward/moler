## moler 4.13.1
* Preserve log paths when building compression commands

## moler 4.13.0
* Add AT command for Fibocom devices, to get information about cell

## moler 4.12.0
* Add AT command for Fibocom devices, for enable/disable IP pass-through
* OutOfPty rerun and closing pty fix

## moler 4.11.1
 * unix command df improvements

## moler 4.10.1
 * get_apns: allow dotted and underscored APN names in CGDCONT parser

## moler 4.10.0
 * Set terminal dimension in PtyProessUnicodeNotFork

## moler 4.9.1
 * Default terminal switch

## moler 4.9.0
 * Removed code for old, unsupported  Pythons (below 3.8)
 * Terminal without fork as default

## moler 4.8.0
 * Delete device aftret its test
 * Fixing threads remaining after device removal

## moler 4.7.0
 * Add support for NSA mode in the AT+COPS command

## moler 4.6.0
 * Deleted asyncio policy class
 * Warning when using ThreadedTerminalNoFork

## moler 4.5.0
 * Optional terminal without forkpty

## moler 4.4.0
 * Warning if command goes to queue

## moler 4.3.2
 * rm fails on permission denied

## moler 4.3.1
 * duplicates in ping

## moler 4.3.0
 * Command Crrl+C
 * Enhancement of MolerTimeout exception
 * Log traceback when exception is set

## moler 4.2.1
 * make_record - tuple instead of any

## moler 4.2.0
 * Unix command hostanamectl
 * Unix command ip maddr

## moler 4.1.0
 * Unset PROMPT_COMMAND for every new virtual terminal

## moler 4.0.1
 * UnixRemote - change the Exception when wrong configuration

## moler 4.0.0
 * Exchange state machines for devices (conditionally delete state PROXY_PC as default)

## moler 3.13.0
 * Optional disable debug log
 * Enhancement for optional PROXY_PC state removal

## moler 3.12.0
 * Remove state from state machine dict. Devices (with suffix 3) can conditionally delete state PROXY_PC
 * Readability logs
 * Debug info

## moler 3.11.1
 * Fix the Wait4prompts (data processing in reverse order)

## moler 3.11.0
 * New Unix commands (bzip2, 7z)
 * uptime - new parser
 * Log info for state observer
 * Number converters can return None instead raise an exception
 * New locking commands for AT devices
 * Change at command to accept in apt name

## moler 3.10.0
 * Wait4prompts - reverse order of processing lines
 * More readable info when more than 1 prompt match the same line
 * CommandChangingPrompt - refactoring

## moler 3.9.0
 * Change the way of validating if Ctrl+Z has worked and stopped the command
 * Keygen file is taken from ssh output
 * Optional sleep after state change
 * Change the way the date is parsed (time zone)

## moler 3.8.0
 * More info when SshShell is disconnected
 * Fix prompt detection for ProxyPc2

## moler 3.7.1
 * Fix version

## moler 3.7.0
 * Changed regex in iperf3 cmd _parse_header to accept 'Bitrate' and 'Bandwidth' to support older iperf3 versions
 * Optional mrge additional params from config and from function
 * Coverage - parameters values converted to compatibility with version 7.4.4

## moler 3.6.0
 * Optional pause Wait4Prompts during state change
 * Added CRT tests

## moler 3.5.0
* Unix commands - optional ctrl + z and kill on timeout - add `wait` call after `kill`
* Add helper for escape codes `[2004l` `[2004h`
* Add break_event to Event

## moler 3.4.0
* StateMachine - lock to avoid race conditions
* Command failure regular expression and exceptions for them
* Timeout msg for unix commands

## moler 3.3.0
* Optional log to console/stdout
* Optional sleep before commands in EventAwaiter
* Unix commands - optional ctrl + z and kill on timeout

## moler 3.2.0
* Refactoring - removed warnings for Python
* ConnectionObserverLifeStatus - debug enhancement
* Refactoring - fstrings

## moler 3.1.0
* Refactoring - Pylint
* Changed time calculation to time.monotonic()
* Type annotations for command base classes
* Removed code for Python < 3.7

## moler 3.0.0
* Common way to fail commands based on their output
* Start command(s) when event(s) finished - start_command_after_event
* Changed deprecated test code
* Removed support for Python 2.7-3.6

## moler 2.17.1
* Fix for compare objects under Python 2.7

## moler 2.17.0
* Implementation of internal Quectel AT command for setting network preferences
* Removed Deepdiff

## moler 2.16.0
* Tests on Python 3.12
* Warning for Pythons 2.7 -3.6 (support will be removed soon)
* Prompt detection for overloaded systems

## moler 2.15.0
* ConnectionObserver objects store full exception stack for Python3.5+
* Support for failure regex for commands for devices based on Unix
* Support values without prefix in byte converter
* Improvement prompt detection for devices using Paramiko for the first ssh

## moler 2.14.0
* Implementation of internal Quectel command for set NR earfcn lock
* Fix typo in `nft` command

## moler 2.13.0
* Iperf3 implementation
* Parameter force for method break_cmd

## moler 2.12.0
* Implementation of AT commands with Get and Set for Cell Id (general, GPRS, LTE, NR)

## moler 2.11.0
* Implementation of PDU sessions AT commands
* Refactoring - get rid of warnings for newer Pythons
* Tests work on Python 3.11

## moler 2.10.0

### Improved
* Commands `su` and `sudo` support many passwords
* Command exit doesn't wait for echo (optional)

## moler 2.9.0

### Improved
* Log all command attributes when timeout
* Detect prompt for devices with paramiko connection

## moler 2.8.0

### Improved

* Deeper stack logging
* Methods search_compiled and match_compiled can support None as compiled regex

## moler 2.7.0

### Improved

* Command ethtool - add support for -S option
* Command nmap - add support for many crypto protocols
* Set level of functionality - AT cmd
* Get level of functionality - AT cmd

## moler 2.6.0

### Improved

* Command run_script for AT
* Improved tests for state machines - continued

## moler 2.5.0

### Improved

* Improved tests of state machines - continued

## moler 2.4.0

### Improved

* New adb commands for Unix
* Improved tests of state machines

## moler 2.3.1

### Improved

* Add support for commands when prompt is not set

## moler 2.3.0

### Improved

* Mark ConnectionObserver objects start and end in logs
* MolerTest.raise_background_exceptions - Python 3.10

## moler 2.2.1

### Improved

* Change deepdiff constraint: `deepdiff == 5.7.0; python_version > '3'`

## moler 2.2.0

### Improved

* Improvement state NOT_CONNECTED in device SM.
* SM can enter state if prompt regex matches a line without anchors.

## moler 2.1.0

### Improved

* Optional compress logs after rotation.
* Log stack for set_exception in ConnectionObserver.
* Caller stack info for MolerTest.error.

## moler 2.0.0

### Improved

* Change default runner and connection type (less threads).
* Improve removing escape character from unix output

## moler 1.33.0

### Improved

* Change dealyafterclose value in Terminal
* Optional ignore exception when try to create all devices
* Print time of processing every command and event while the documentation is being checked

## moler 1.32.2

### Improved
* Proper handled timeout in wait_for of RunnerSingleThread

## moler 1.32.1

### Improved
* Check if passed object is ConnectionObserver instance in MolerConnectionForSingleThreadRunner

## moler 1.32.0

### Added
* add `ADDITIONAL_PARAMS` in device configuration
* add possibility use `single-threaded` runner for all ConnectionObservers

### Improved
* Add more readable traceback
* Parsing fail and success for RunScript command
* Add new regex for retry password(ssh/telnet commands)

## moler 1.31.2

### Improved
* Add logs for troubleshoot threads

## moler 1.31.1

### Improved
* Set flag to run in embeded command

## moler 1.31.0

### Added
* Unix command nping
* Unix command sysctl

### Improved
* Check cmd status before break
* Commands and events - 100% coverage in tests
* Run tests with flake8


### Fixed
* CI on GitHub Actions and resolved issues with new Python
* Fix the possibility to break command if the command is not running

## moler 1.30.0

### Improved
* goto_state_bg
* Parallel tests for device SM

## moler 1.29.0

### Improved
* Close python
* Packages list

## moler 1.28.0

### Added
* Add-set-apn-at-cmd

### Improved
* CMDs and events - empty string as unicode
* Coverage events in test - 100%
* Faster SM tests
* State machine in device - check overlapping patterns for prompts.

## moler 1.27.0

### Added
* Disable logging incoming data
* Enable_echo AT cmd
* Logs rotating
* Set mode AT cmd
* ssh keygen override

### Improved
* Logging suffix
* Terminal investigation

## moler 1.26.0

### Added
* New output for iptables and add rest in ret
* nft command

### Improved
* Modify cu command

## moler 1.25.1

### Improved
* Don't tail full file for first file

## moler 1.25.0

### Added
* At cmd
* Create cu.py
* tail_latest_file

### Improved
* Change ATI cmd name to GetProductInfo
* Log exception from runner
* Modify regex in get_apns.py

## moler 1.24.0

### Improved
* nmap
* Remove hardcore
* Command traceroute
* Scp - new format of question

## moler 1.23.0

### Improved
* Openssl cmd
* Unix lxc* commands

### Fixed
* OpenSSL S Client - class name fix

## moler 1.22.0

### Added
* New format of ssh question

## moler 1.21.0

### Added
* New funcionality for ssh
* Tcpdump new regex

## moler 1.20.0

### Improved
* Load events only if they are not loaded
* Unxz
* Fix packages for UnixLocal in examples
* Commands may break on regex

## moler 1.19.0

### Added
* New type of io-connection: threaded sshshell based on Paramiko

## moler 1.18.0

### Improved
* Ssh Telnet coverage

### Fixed
* DeviceFactory doesn't pass io constructor parameters towards created devices
* Fix parsing date where exists from and on

## moler 1.17.0

### Improved
* Option clear devices history
* Sm not connected
* Tail and cat work with error in content of file
* Collect output from telent and ssh
* Sum cmds

## moler 1.16.0

### Improved
* Optional parameter username for telnet and ssh.
* Cmds for pdu aten
* Convert to number

## moler 1.15.0

### Improved
* Documentation fix for return value
* Add ret_required=False
* Pdu Aten

## moler 1.14.0

### Improved
* Support for text files with content the same as errors from commands

## moler 1.13.0

### Improved
* Iperf2: calculate summary report at each interval when server handles client running in --parallel mode

## moler 1.12.0

### Improved
* Allow AdbRemote device to have expected_prompt generated from serial_number of Android device

## moler 1.11.0

### Improved
* Add catching error to openssl_x509_text_in command
* New fail scenario for ssh
* Openssl cmd
* Store datetime when data was read on connection
* Set establish_connection to False
* Support initial_state for already created devices

## moler 1.10.0

### Improved
* Classes Connection and ObservableConnection are deprecated now. Their original code has been moved into
 AbstractMolerConnection and ThreadedMolerConnection. Change made for code clarity.

### Fixed
* Iperf2 command fails on parsing when used `with -s -P 1` options (single run server).
* Log all state changes in devices.

## moler 1.9.0

### Added
* New method of converting string to int for whole dict.

### Improved
* Keep state in background does not block main flow
* data_received() of commands & events gets additional parameter: time when data was caught on connection
* Improvement parsing in command ls.
* Commands, events and callbacks data processing is done in separate thread to secure connection reads against blocking
 them by commands/events/callbacks.

## moler 1.8.0

### Added
* AdbRemote device - new state ADB_SHELL_ROOT
   * allow firing android-linux commands that need root
* access to .start_time of any ConnectionObserver
   * help in extending its timeout (calculating its "already passed life-time")

### Improved
* hardening Iperf2 against multiple echo at command startup (observed under cygwin)
* better display of regexp patterns in logs - simplify troubleshooting
* str(CommandChangingPrompt) display expected prompt regexp - simplify troubleshooting
* cmd.unix.exit.Exit got new parameter allowed_newline_after_prompt
   * allowed_newline_after_prompt=True helps to operate with cygwin

## moler 1.7.0

### Added
* AdbRemote device being state machine capable to reach ADB_SHELL state
   * allow firing android-linux commands from within android device
* ADB commands:
   * adb_shell
* AT commands:
   * plink_serial

### Improved
* AtRemote device uses 'plink -serial' to proxy serial into stdin/stdout
* State Machines definition: commands allowed for state may be specified using module name
   * previously (only packages): ['moler.cmd.at'], now: ['moler.cmd.at', 'moler.cmd.unix.ctrl_c']
   * helps in code reuse while keeping commands under related device folder
* Improved connection decoder inside ThreadedTerminal: cleaning output from VT100 terminal codes (not all)

### Fixed
* GenericAtCommand treats 'NO CARRIER' console output as error indication

## moler 1.6.0

### Added
* Publisher class - Moler implementation of Publisher-Subscriber Design Pattern
* Iperf2 command publishing intermediate reports to all subscribed "observers"
* AT commands:
   * at(AT)
   * attach(AT+CGATT=1), detach(AT+CGATT=0), get_attach_state(AT+CGATT?)
   * get_imei(AT+CGSN)
   * get_imsi(AT+CIMI)
   * get_manufacturer_id(AT+CGMI)
   * get_revision_id(AT+CGMR)
* moler_serial_proxy tool proxing between serial connection and stdio/stdout
* AtRemote device being state machine capable to reach AT_REMOTE state and issue AT commands
   * (controlling AT console available over serial connection on remote machine)

### Improved
* CommandTextualGeneric may set direct path to command executable
   * (f.ex. OS may default 'iperf' to '/usr/bin/iperf' but user wants '/usr/local/bin/iperf')

### Fixed
* ConnectionObserver, AbstractDevice were unable to be used inside multiple inheritance

## moler 1.5.1

### Fixed
* SSH regex for fingerptint prompt

## moler 1.5.0

### Added
* Termianl binary debug

### Improved
* CI pipeline
* ls command

### Changed
* Redefined timeout for telnet and ssh
* RegexHelper checks if parameter is not None


## moler 1.4.0

### Changed
* connection name returned by iperf2 uses "port@host" format to not confuse on IPv6 (fd00::1:0:5901 -> 5901@fd00::1:0)

### Deprecated
* `config_type` parameter of `load_config()` is not needed, configuration type is autodetected


## moler 1.3.1

### Added
* possibility to enable/disable logging each occurrence of event
* backward compatibility for load_device_from_config()

### Fixed
* device closing (dev.remove() method) fails if device was already closed


## moler 1.3.0

### Added
* force Unix device to return into local shell when device is closing (that would close ssh if was open)
* allow adding devices after initial load of configuration
* new UNIX command handled by moler: **devmem**
* iperf command refactored into iperf2 command

### Fixed
* wrong iperf bandwidth calculation when bandwidth displayed in Kbits/sec, Mbits/sec, Gbits/sec
* first moler prompt to catch
* removal of new line characters on some connections

### Deprecated
* stop using Iperf command from moler.cmd.unix.iperf; use Iperf2 from moler.cmd.unix.iperf2 instead


## moler v1.2.0

### Added
* Possibility to forget device
* Change number of retry whe terminal not operable yet

### Fixed
* fix calculating timeout of sudo command


## moler v1.1.0

### Added
* new UNIX command handled by moler: **gzip**
* skip asyncio test under python 2 (internal CI of moler)

### Fixed
* wrong processing of chunked lines by textual events
* sudo command incorrectly handling result of sudo-embedded command


## moler v1.0.1

### Added
* improved documentation generation


## moler v1.0.0

### Added
* first official release of Moler
