# -*- coding: utf-8 -*-
"""
Moler's device has 2 main responsibilities:
- be the factory that returns commands of that device
- be the state machine that controls which commands may run in given state
"""
__author__ = "Marcin Usielski"
__copyright__ = "Copyright (C) 2019-2024, Nokia"
__email__ = "marcin.usielski@nokia.com"

import abc

import six


@six.add_metaclass(abc.ABCMeta)
class AbstractDevice:
    def __init__(self):
        super(AbstractDevice, self).__init__()
        self._remove_callbacks = []

    @property
    @abc.abstractmethod
    def current_state(self):
        """
        Getter of current state.

        :return: String with the name of current state.
        """

    @property
    @abc.abstractmethod
    def name(self):
        """
        Getter of device name.

        :return: String with the device name.
        """

    @name.setter
    @abc.abstractmethod
    def name(self, value):
        """
        Setter for device name.

        :param value: String with device name.
        :return: None
        """

    @property
    @abc.abstractmethod
    def public_name(self):
        """
        Getter for publicly used device name.

        Internal name of device (.name attribute) may be modified by device itself  in some circumstances (to not
        overwrite logs). However, public_name is guaranteed to be preserved as it was set by external/client code.

        :return: String with the device alias name.
        """

    @public_name.setter
    @abc.abstractmethod
    def public_name(self, value):
        """
        Setter for publicly used device name. If you clone devices and close them then if you want to create with
        already used name then device will be created with different name but public name will be as you want.

        :param value: String with device name.
        :return: None
        """

    @abc.abstractmethod
    def has_established_connection(self):
        """
        Checks if connection is established to real device.

        :return: True if connection is established, False otherwise.
        """

    @abc.abstractmethod
    def goto_state(
        self,
        state,
        timeout=-1,
        rerun=0,
        send_enter_after_changed_state=False,
        log_stacktrace_on_fail=True,
        keep_state=True,
        sleep_after_change=0.5
    ):
        """
        Goes to state.

        :param state: name of state to go.
        :param timeout: Time in seconds when break transitions if still not success.
        :param rerun: How many times try to rerun command(s) when device is still not in requested state.
        :param send_enter_after_changed_state: Set True to send enter after enters proper state.
        :param log_stacktrace_on_fail: Set True to log exceptions if command to enter state failed.
        :param keep_state: if True and state is changed without goto_state then device tries to change state to state
         defined by goto_state.
        :param sleep_after_change: Time in seconds to sleep after state change.
        :return: None
        """

    @abc.abstractmethod
    def establish_connection(self):
        """
        Establishes connection to real device.

        :return: None
        """

    @abc.abstractmethod
    def add_neighbour_device(self, neighbour_device, bidirectional=True):
        """
        Adds neighbour device to this device.

        :param neighbour_device: device object or string with device name.
        :param bidirectional: If True then this device will be added to f_device.
        :return: None
        """

    @abc.abstractmethod
    def get_neighbour_devices(self, device_type):
        """
        Returns list of neighbour devices of passed type.

        :param device_type: type of device. If None then all neighbour devices will be returned.
        :return: list of devices.
        """

    @abc.abstractmethod
    def configure_logger(self, name, propagate):
        """
        Configures logger.

        :param name: Name of logger
        :param propagate: Set True if you want to propagate logs, False otherwise (recommended)
        :return: None
        """

    @abc.abstractmethod
    def on_connection_made(self, connection):
        """
        Method to call by Moler framework when connection is established.

        :param connection: Connection object.
        :return: None
        """

    @abc.abstractmethod
    def on_connection_lost(self, connection):
        """
        Method to call by Moler framework when connection is lost.

        :param connection: Connection object.
        :return: None
        """

    @abc.abstractmethod
    def get_cmd(self, cmd_name, cmd_params=None, check_state=True, for_state=None):
        """
        Returns instance of command connected with the device.

        :param cmd_name: name of commands, name of class (without package), for example "cd".
        :param cmd_params: dict with command parameters.
        :param check_state: if True then before execute of command the state of device will be check if the same
         as when command was created. If False the device state is not checked.
        :param for_state: if None then command object for current state is returned, otherwise object for for_state is
         returned.
        :return: Instance of command
        """

    @abc.abstractmethod
    def get_event(
        self, event_name, event_params=None, check_state=True, for_state=None
    ):
        """
        Return instance of event connected with the device.

        :param event_name: name of event, name of class (without package).
        :param event_params: dict with event parameters.
        :param check_state: if True then before execute of event the state of device will be check if the same
         as when event was created. If False the device state is not checked.
        :param for_state: if None then event object for current state is returned, otherwise object for for_state is
         returned.
        :return: Event object
        """

    @abc.abstractmethod
    def run(self, cmd_name, **kwargs):
        """
        Wrapper for simple use command: creates command, runs it and waits till it ends.

        :param cmd_name: name of class of command.
        :param kwargs: dict with parameters for command constructor.
        :return: object from command get_result (mainly dict).
        """

    @abc.abstractmethod
    def start(self, cmd_name, **kwargs):
        """
        Wrapper for simple use command: creates command and runs it.

        :param cmd_name: name of class of command.
        :param kwargs: dict with parameters for command constructor.
        :return: command object
        """

    def register_device_removal_callback(self, callback):
        """
        Registers callable to be called (notified) when device is removed.

        :param callback: callable to call when device is being removed.
        :return: None
        """
        if callback not in self._remove_callbacks:
            self._remove_callbacks.append(callback)

    def remove(self):
        """
        Closes device, if any command or event is attached to this device they will be finished.

        :return: None
        """
        callbacks = self._remove_callbacks
        self._remove_callbacks = []
        for callback in callbacks:
            callback()
