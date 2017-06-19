# Copyright 2017: Godaddy Inc.

import json
import threading
import time

import futurist
import mock
import requests

from netmet.utils import pusher
from tests.unit import test


class PusherTestCase(test.TestCase):

    def test_init(self):
        p = pusher.Pusher("some_url", period=20, max_count=40)
        self.assertEqual("some_url", p.url)
        self.assertEqual(20, p.period)
        self.assertEqual(40, p.max_count)

    def test_add(self):
        p = pusher.Pusher("")
        p.add(1)
        p.add(2)
        self.assertEqual(list(p.objects), [1, 2])

    def test_send_stops(self):
        p = pusher.Pusher("")
        p._death = threading.Event()
        p._death.set()
        p._send()

    @mock.patch("netmet.utils.pusher.requests.session")
    def test_send(self, mock_session):
        mock_session.return_value.post.side_effect = [
            mock.Mock(status_code=201),
            requests.exceptions.RequestException,
            mock.Mock(status_code=504),
            mock.Mock(status_code=201)
        ]

        p = pusher.Pusher("http://some_url", max_count=10)
        p._death = threading.Event()
        for i in xrange(22):
            p.add(i)

        p._send()
        calls = [
            mock.call("http://some_url",
                      data=json.dumps(range(0, 10)), headers={}, timeout=2),
            mock.call("http://some_url",
                      data=json.dumps(range(10, 20)), headers={}, timeout=2),
            mock.call("http://some_url",
                      data=json.dumps(range(10, 20)), headers={}, timeout=2),
            mock.call("http://some_url",
                      data=json.dumps(range(10, 20)), headers={}, timeout=2)
        ]
        mock_session.return_value.post.assert_has_calls(calls)
        self.assertEqual(4, mock_session.return_value.post.call_count)

    @mock.patch("netmet.utils.pusher.requests.session")
    def test_send_hmac(self, mock_session):
        mock_session.return_value.post.return_value = (
            mock.Mock(status_code=201))

        p = pusher.Pusher("http://some_url", timeout=5,
                          extra_headers=lambda x: {"a": "a"}, max_count=10)
        p._death = threading.Event()
        for i in xrange(11):
            p.add(i)

        p._send()

        mock_session.return_value.post.assert_called_once_with(
            "http://some_url",
            data=json.dumps(range(0, 10)), headers={"a": "a"}, timeout=5)
        self.assertEqual(1, mock_session.return_value.post.call_count)

    def test_send_periodically_stops(self):
        p = pusher.Pusher("")
        p._death = threading.Event()
        p._death.set()
        p._send_peridoically()

    @mock.patch("netmet.utils.pusher.Pusher._send")
    def test_send_periodically(self, mock_send):

        p = pusher.Pusher("", period=0.1)
        p._death = threading.Event()

        def stop():
            time.sleep(0.55)
            p._death.set()

        e = futurist.ThreadPoolExecutor()
        e.submit(stop)

        p._send_peridoically()
        self.assertEqual(5, mock_send.call_count)
        e.shutdown()

    @mock.patch("netmet.utils.pusher.Pusher._send_peridoically")
    def test_start_and_stop(self, mock_send_peridoically):
        p = pusher.Pusher("", period=0.1)
        p.start()
        started_at = p._started_at
        worker = p._worker
        p.start()   # test that start() can be called 2 times
        self.assertEqual(p._started_at, started_at)
        self.assertIs(p._worker, worker)
        time.sleep(0.1)
        self.assertEqual(1, mock_send_peridoically.call_count)
        mock_send_peridoically.assert_called_once_with()
        p.stop()
        p.stop()   # test that stop() can be called 2 times
