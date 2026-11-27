# -*- coding: utf-8 -*-

__author__ = "Michal Ernst, Marcin Usielski"
__copyright__ = "Copyright (C) 2018-2026, Nokia"
__email__ = "michal.ernst@nokia.com, marcin.usielski@nokia.com"

import abc
import functools
import logging
from typing import Optional

from moler.abstract_moler_connection import AbstractMolerConnection
from moler.runner import ConnectionObserverRunner
from moler.connection_observer import ConnectionObserver
from moler.exceptions import MolerException, ResultAlreadySet
from moler.helpers import instance_id


class Event(ConnectionObserver, metaclass=abc.ABCMeta):
    def __init__(self, connection: Optional[AbstractMolerConnection] = None, till_occurs_times: int = -1, runner: Optional[ConnectionObserverRunner] = None):
        """

        :param connection: connection to observe.
        :param till_occurs_times: If -1 then infinite. If positive value match the number of times.
        :param runner: runner to run event.
        """
        super(Event, self).__init__(connection=connection, runner=runner)
        # By default events are infinite (100 years :-) so, they won't timeout since they are
        # mainly designed to catch something inside event_occurred(), notify interested parties and keep going.
        self.timeout = 60 * 60 * 24 * 356 * 100  # [sec]
        self.callback = None
        self.callback_params = {}
        self._occurred = None
        self.till_occurs_times = till_occurs_times
        self._log_every_occurrence = True
        self.event_name = Event.observer_name
        self._last_chunk_matched = False

    def __str__(self):
        """
        Returns description of event object.

        :return: String representation of event.
        """
        return f"{self.__class__.__name__}(id:{instance_id(self)})"

    # pylint: disable=keyword-arg-before-vararg
    def start(self, timeout: float = None, *args, **kwargs):
        """Start background execution of command."""
        self._validate_start(*args, **kwargs)
        ret = super(Event, self).start(timeout, *args, **kwargs)
        self.life_status._is_running = True  # pylint: disable=protected-access
        return ret

    def add_event_occurred_callback(self, callback, callback_params=None):
        if not self.callback:
            if callback_params is None:
                callback_params = {}
            partial_callback = functools.partial(callback, **callback_params)
            self.callback = partial_callback
        else:
            raise MolerException(
                f"Cannot assign a callback '{callback}' to event '{self}' when another callback '{self.callback}' is already assigned"
            )

    def enable_log_occurrence(self) -> None:
        """
        Enables to log every occurrence of the event.

        :return: None
        """
        self._log_every_occurrence = True

    def disable_log_occurrence(self) -> None:
        """
        Disables to log every occurrence of the event.

        :return: None
        """
        self._log_every_occurrence = False

    def remove_event_occurred_callback(self) -> None:
        """
        Removes callback from the event.

        :return: None
        """
        self.callback = None

    def notify(self) -> None:
        """
        Notifies (call callback).

        :return: None
        """
        self._log_occurred()
        if self.callback:
            self.callback()

    def event_occurred(self, event_data) -> None:
        """
        Sets event_data as new item of occurrence ret.
        :param event_data: data to set as value of occurrence.
        :return: None
        """
        # Should be used to set final result of event.
        if self.done():
            raise ResultAlreadySet(self)
        self._prepare_result_from_occurred()
        self._occurred.append(event_data)
        self._last_chunk_matched = True
        if self.till_occurs_times > 0:
            if len(self._occurred) >= self.till_occurs_times:
                self.break_event()
        self.notify()

    def _prepare_result_from_occurred(self) -> None:
        """
        Prepare result from occurred.

        :return: None
        """
        if self._occurred is None:
            self._occurred = []

    def _get_module_class(self) -> str:
        return f"{self.__class__.__module__}.{self}"

    def get_long_desc(self) -> str:
        """
        Returns string with description of event.

        :return: String with description.
        """
        return f"Event '{self._get_module_class()}'"

    def get_short_desc(self) -> str:
        """
        Returns string with description of event.

        :return: String with description.
        """
        return self.get_long_desc()

    def get_last_occurrence(self):
        """
        Returns ret value from last occurrence.

        :return: ret value form last occurrence or None if there is no occurrence.
        """
        if self._occurred:
            return self._occurred[-1]
        else:
            return None

    def break_event(self, force=False) -> None:
        """
        Break event. Do not process anymore. Clean up all resources. Prepare result.

        :param force: If False then check if no of occurred is as expected Force, True to not check.
        :return: None
        """
        if not self.done():
            self._prepare_result_from_occurred()
            if not force and len(self._occurred) < self.till_occurs_times:
                self.set_exception(MolerException(f"Expected {self.till_occurs_times} occurrences but got {len(self._occurred)}."))
            else:
                self.set_result(self._occurred)

    def _log_occurred(self) -> None:
        """
        Logs info about notify when callback is not defined.

        :return: None
        """
        msg = f"Notify for event:  '{self.__class__.__module__}.{self}'"
        if self._log_every_occurrence:
            self._log(lvl=logging.INFO, msg=msg)
        if self.callback:
            msg = f"{msg} with callback '{self.callback}'."
        else:
            msg = f"{msg} without callback."
        self._log(lvl=logging.DEBUG, msg=msg)

    @abc.abstractmethod
    def pause(self) -> None:
        """
        Pauses the event. Do not process till resume.

        :return: None
        """

    @abc.abstractmethod
    def resume(self) -> None:
        """
        Resumes processing output from connection by the event.

        :return: None
        """
