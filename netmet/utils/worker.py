# Copyright 2017: GoDaddy Inc.

import random
import threading

import futurist


class LonelyWorker(object):
    _self = None
    _lock = threading.Lock()
    _period = 40

    def __init__(self):
        """Do not call this method directly. Call create() instead."""

    @classmethod
    def create(cls, callback_after_job=None):
        cls._self = cls()
        cls._self._worker = futurist.ThreadPoolExecutor()
        cls._self._death = threading.Event()
        cls._self._worker.submit(cls._self._periodic_workder)
        cls._self._force_update = False
        cls._self._callback_after_job = callback_after_job or (lambda: True)

    @classmethod
    def get(cls):
        return cls._self

    @classmethod
    def force_update(cls):
        cls._self._force_update = True

    @classmethod
    def destroy(cls):
        with cls._lock:
            if cls._self is not None:
                if not cls._self._death.is_set():
                    cls._self._death.set()
                    cls._self._worker.shutdown()
                    cls._self = None

    def _periodic_workder(self):
        while not self._death.is_set():
            if self._job():
                self._callback_after_job()

            t = 0
            while t < self._period:
                if self._force_update:
                    self._force_update = False
                    break
                else:
                    t += 1 + random.random()
                    self._death.wait(1 + random.random())
