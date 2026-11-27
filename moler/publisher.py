# -*- coding: utf-8 -*-
"""
Moler implementation of Publisher-Subscriber Design Pattern.

Main characteristic:
- allow Subscribers to be garbage collected while still subscribed inside Publisher

This is required since:
- both parties may exist in different threads
- both parties may keep references to themselves creating reference cycles
"""

__author__ = "Grzegorz Latuszek"
__copyright__ = "Copyright (C) 2020-2026, Nokia"
__email__ = "grzegorz.latuszek@nokia.com"

import weakref
from threading import Lock

from moler.helpers import instance_id


class Publisher:
    """
    Allows objects to subscribe for notification about data.

    Subscription is made by registering function to be called with this data (may be object's method).
    Function should have signature like:

    def subscriber(data):
        # handle that data
    """

    def __init__(self):
        """Create Publisher instance."""
        super(Publisher, self).__init__()
        self._subscribers = {}
        self._subscribers_lock = Lock()

    def subscribe(self, subscriber):
        """
        Subscribe for 'data notification'.

        :param subscriber: function to be called to notify about data.
        """
        with self._subscribers_lock:
            subscription_key, subscription_value = self._get_subscriber_key_and_value(
                subscriber
            )

            if subscription_key not in self._subscribers:
                self._subscribers[subscription_key] = subscription_value

    def unsubscribe(self, subscriber):
        """
        Unsubscribe from 'data notification'.

        :param subscriber: function that was previously subscribed
        """
        with self._subscribers_lock:
            subscription_key, _ = self._get_subscriber_key_and_value(subscriber)
            if subscription_key in self._subscribers:
                del self._subscribers[subscription_key]

    def notify_subscribers(self, *args, **kwargs):
        """Notify all subscribers passing them notification parameters."""
        # need copy since calling subscribers may change self._subscribers
        current_subscribers = list(self._subscribers.values())
        for self_or_none, subscriber_function in current_subscribers:
            try:
                if self_or_none is None:
                    subscriber_function(*args, **kwargs)
                else:
                    subscriber_self = self_or_none
                    subscriber_function(subscriber_self, *args, **kwargs)
            except ReferenceError:
                pass  # ignore: weakly-referenced object no longer exists
            except Exception as exc:  # we don't want subscriber bug to kill publisher
                self.handle_subscriber_exception(self_or_none, subscriber_function, exc)

    def handle_subscriber_exception(
        self, subscriber_owner, subscriber_function, raised_exception
    ):
        """
        Handle exception raised by subscriber during publishing.

        :param subscriber_owner: instance of class whose method was subscribed (or None)
        :param subscriber_function: subscribed class method or raw function
        :param raised_exception: exception raised by subscriber during publishing
        :return: None
        """
        # TODO: we may log it

    @staticmethod
    def _get_subscriber_key_and_value(subscriber):
        """
        Allow Subscribers to be garbage collected while still subscribed inside Publisher.

        Subscribing methods of objects is tricky::

            class TheObserver:
                def __init__(self):
                    self.received_data = []

                def on_new_data(self, data):
                    self.received_data.append(data)

            observer1 = TheObserver()
            observer2 = TheObserver()

            subscribe(observer1.on_new_data)
            subscribe(observer2.on_new_data)
            subscribe(observer2.on_new_data)

        Even if it looks like 2 different subscriptions they all
        pass 3 different bound-method objects (different id()).
        This is so since access via observer1.on_new_data
        creates new object (bound method) on the fly.

        We want to use weakref but weakref to bound method doesn't work
        see: http://code.activestate.com/recipes/81253/
        and : https://stackoverflow.com/questions/599430/why-doesnt-the-weakref-work-on-this-bound-method
        When we wrap bound-method into weakref it may quickly disappear
        if that is only reference to bound method.
        So, we need to unbind it to have access to real method + self instance

        Unbinding above 3 examples of on_new_data will give:
        1) self                      - 2 different id()
        2) function object of class  - all 3 have same id()

        Observer key is pair: (self-id, function-id)
        """
        try:
            self_or_none = subscriber.__self__
            self_id = instance_id(self_or_none)
            self_or_none = weakref.proxy(self_or_none)
        except AttributeError:
            self_id = 0  # default for not bound methods
            self_or_none = None

        try:
            func = subscriber.__func__
        except AttributeError:
            func = subscriber
        function_id = instance_id(func)

        subscription_key = (self_id, function_id)
        subscription_value = (self_or_none, weakref.proxy(func))
        return subscription_key, subscription_value
