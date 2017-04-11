# Copyright 2017: GoDaddy Inc.

import logging
import threading

import futurist


LOG = logging.getLogger(__name__)


class LonelyWorker(object):
    _self = None
    _lock = threading.Lock()
    _period = 60

    def __init__(self):
        """Do not call this method directly. Call create() instead."""

    @classmethod
    def create(cls, callback_after_job=None):
        with cls._lock:
            if not cls._self:
                self = cls()
                cls._self = self
                self._worker = futurist.ThreadPoolExecutor()
                self._death = threading.Event()
                self._worker.submit(cls._self._periodic_workder)
                self._force_update = False
                self._callback_after_job = callback_after_job or (lambda: True)

    @classmethod
    def get(cls):
        return cls._self

    @classmethod
    def force_update(cls):
        if cls._self:
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
            try:
                if self._job():
                    self._callback_after_job()

                t = 0
                while t < self._period:
                    if self._force_update:
                        self._force_update = False
                        break
                    else:
                        wait = min(self._period / 10.0, 1.0)
                        t += wait
                        self._death.wait(wait)

            except Exception:
                LOG.exception("LonelyWorker fails to do peridoic duties %s"
                              % self)
