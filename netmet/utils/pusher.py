# Copyright 2017: GoDaddy Inc.

import collections
import logging
import threading

import futurist
import monotonic
import requests


LOG = logging.getLogger(__name__)


class Pusher(object):

    def __init__(self, url, period=10, max_count=1000):
        self.url = url
        self.period = period
        self.max_count = max_count
        self.objects = collections.deque()
        self._worker = None

    def _send(self):
        while not self._death.is_set():
            body = []
            count = 0
            while self.objects and count < self.max_count:
                count += 1
                body.append(self.objects.popleft())

            # Try to push data 3 times. Helps to avoid network blinks
            # and netmet server failures
            for i in xrange(3):
                r = requests.post(self.url, json=body)
                if r.status_code == 201:
                    break
                if self._death.is_set():
                    break
            else:
                LOG.warning("Can't push data to netmet server %s (status %s)"
                            % (self.url, r.status_code))
                self._death.wait(1)
                # Put data back, in case of failure
                self.objects.extendleft(body)
                break

            if len(self.objects) < self.max_count:
                break

    def _send_peridoically(self):
        while not self._death.is_set():
            try:
                if monotonic.monotonic() - self._started_at > self.period:
                    self._send()
                    self._started_at = monotonic.monotonic()

                self._death.wait(self.period / 20.0)
            except Exception:
                # If execution fails we should reset our timer
                # to not flood netmet server
                self._started_at = monotonic.monotonic()
                LOG.exception("Pusher failed")

    def add(self, item):
        self.objects.append(item)

    def start(self):
        if not self._worker:
            self._started_at = monotonic.monotonic()
            self._worker = futurist.ThreadPoolExecutor()
            self._death = threading.Event()
            self._worker.submit(self._send_peridoically)

    def stop(self):
        if self._worker:
            self._death.set()
            self._worker.shutdown()
