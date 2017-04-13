# Copyright 2017: GoDaddy Inc.

import collections
import logging
import threading

import futurist
import monotonic
import requests


LOG = logging.getLogger(__name__)


class Pusher(object):

    def __init__(self, url, period=10, max_count=1000,
                 dealey_between_requests=0.2, timeout=2):
        self.url = url
        self.period = period
        self.dealey_between_requests = dealey_between_requests
        self.timeout = timeout
        self.max_count = max_count
        self.objects = collections.deque()
        self._worker = None
        self.session = requests.session()

    def _send(self):
        body = []
        fails_in_row = 0
        while not self._death.is_set():
            count = len(body)
            while self.objects and count < self.max_count:
                count += 1
                body.append(self.objects.popleft())

            try:
                r = self.session.post(self.url, json=body,
                                      timeout=self.timeout)
                if r.status_code == 201:
                    body = []
                    fails_in_row = 0

                error_status = r.status_code if r.status_code != 201 else None
            except requests.exceptions.RequestException as e:
                error_status = str(e)
            finally:
                if error_status:
                    fails_in_row += 1
                    LOG.warning("Can't push data to %s (status %s)"
                                % (self.url, error_status))

            if not body and len(self.objects) < self.max_count:
                break

            if fails_in_row > 2:
                self.objects.extendleft(body[::-1])
                break

            self._death.wait(self.dealey_between_requests)

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
