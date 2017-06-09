# Copyright 2017: GoDaddy Inc.

import collections
import StringIO
import time

import mock

from netmet.client import collector
from netmet.utils import pusher
from tests.unit import test


class CollectorTestCase(test.TestCase):

    def test_init_standalone(self):
        host = mock.MagicMock()
        tasks = [mock.MagicMock()]

        c = collector.Collector(None, host, tasks)
        self.assertEqual(tasks, c.tasks)
        self.assertIsNone(c.pusher)

    def test_init_full(self):
        host = mock.MagicMock()
        tasks = [mock.MagicMock()]

        c = collector.Collector("http://netmet_url", host, tasks)
        self.assertEqual(tasks, c.tasks)
        self.assertIsInstance(c.pusher, pusher.Pusher)

    @mock.patch("netmet.client.collector.ping.Ping.ping")
    def test_gen_periodic_ping_east_west(self, mock_ping):
        client_host = mock.MagicMock()
        task = {
            "east-west": {
                "dest": {
                    "ip": "1.1.1.1"
                },
                "settings": {
                    "timeout": 5,
                    "packet_size": 55
                }
            }
        }

        mock_ping.return_value = {
            "ret_code": 0,
            "rtt": 10,
            "timestamp": "ttt",
            "packet_size": 55
        }

        c = collector.Collector("some_url", client_host, [])
        c.gen_periodic_ping(task)()
        self.assertEqual(1, len(c.queue))
        expected = {
            "client_src": client_host,
            "client_dest": task["east-west"]["dest"],
            "protocol": "icmp",
            "timestamp": "ttt",
            "latency": 10,
            "packet_size": 55,
            "lost": 0,
            "transmitted": 1,
            "ret_code": 0
        }
        self.assertEqual(expected, c.queue.pop()["east-west"])

    @mock.patch("netmet.client.collector.ping.Ping.ping")
    def test_gen_periodic_ping_south_north(self, mock_ping):
        client_host = mock.MagicMock()
        task = {
            "north-south": {
                "dest": "1.1.1.1",
                "settings": {
                    "timeout": 5,
                    "packet_size": 55
                }
            }
        }

        mock_ping.return_value = {
            "ret_code": 0,
            "rtt": 10,
            "timestamp": "ttt",
            "packet_size": 55
        }

        c = collector.Collector("some_url", client_host, [])
        c.gen_periodic_ping(task)()
        self.assertEqual(1, len(c.queue))
        expected = {
            "client_src": client_host,
            "dest": task["north-south"]["dest"],
            "protocol": "icmp",
            "timestamp": "ttt",
            "latency": 10,
            "packet_size": 55,
            "lost": 0,
            "transmitted": 1,
            "ret_code": 0
        }
        self.assertEqual(expected, c.queue.pop()["north-south"])

    @mock.patch("netmet.client.collector.LOG")
    @mock.patch("netmet.client.collector.ping.Ping.ping")
    def test_gen_periodic_ping_raises(self, mock_ping, mock_log):
        c = collector.Collector("some_url", {}, [])
        mock_ping.side_effect = Exception
        ping_ = c.gen_periodic_ping({"east-west": {
            "dest": {"ip": "1.2.3.4"},
            "settings": {"packet_size": 55, "timeout": 1}
        }})
        ping_()

        mock_log.exception.assert_called_once_with(c.pinger_failed_msg)
        self.assertEqual(1, mock_log.exception.call_count)

    @mock.patch("netmet.client.collector.datetime")
    @mock.patch("netmet.client.collector.monotonic.monotonic")
    @mock.patch("netmet.client.collector.requests.get")
    def test_gen_periodic_http_ping_east_west(self, mock_get, mock_monotonic,
                                              mock_datetime):
        client_host = mock.MagicMock()
        task = {
            "east-west": {
                "dest": {
                    "ip": "1.1.1.1",
                    "host": "1.2.3.4",
                    "port": 80
                },
                "settings": {
                    "timeout": 5,
                    "packet_size": 55
                }
            }
        }

        mock_datetime.datetime.now.return_value.isoformat.return_value = "aaa"

        c = collector.Collector("some_url", client_host, [task])
        mock_monotonic.side_effect = [1, 2]
        mock_get.return_value = mock.MagicMock(
            content="Q" * 10, status_code=200)
        c.gen_periodic_http_ping(task)()
        self.assertEqual(1, len(c.queue))

        expected = {
            "client_src": client_host,
            "client_dest": task["east-west"]["dest"],
            "protocol": "http",
            "timestamp": "aaa",
            "latency": 1000,
            "packet_size": 10,
            "lost": 0,
            "transmitted": 1,
            "ret_code": 200
        }

        self.assertEqual(expected, c.queue.pop()["east-west"])

    @mock.patch("netmet.client.collector.datetime")
    @mock.patch("netmet.client.collector.monotonic.monotonic")
    @mock.patch("netmet.client.collector.requests.get")
    def test_gen_periodic_http_ping_south_north(self, mock_get, mock_monotonic,
                                                mock_datetime):
        client_host = mock.MagicMock()
        task = {
            "north-south": {
                "dest": "http://1.2.3.4",
                "settings": {
                    "timeout": 5,
                    "packet_size": 55
                }
            }
        }

        mock_datetime.datetime.now.return_value.isoformat.return_value = "aaa"

        c = collector.Collector("some_url", client_host, [task])
        mock_monotonic.side_effect = [1, 2]
        mock_get.return_value = mock.MagicMock(
            content="Q" * 10, status_code=200)
        c.gen_periodic_http_ping(task)()
        self.assertEqual(1, len(c.queue))

        expected = {
            "client_src": client_host,
            "dest": task["north-south"]["dest"],
            "protocol": "http",
            "timestamp": "aaa",
            "latency": 1000,
            "packet_size": 10,
            "lost": 0,
            "transmitted": 1,
            "ret_code": 200
        }

        self.assertEqual(expected, c.queue.pop()["north-south"])

    def test_gen_periodic_http_ping_requests_raises(self):
        pass

    def test_gen_periodic_http_ping_raises(self):
        pass

    @mock.patch("netmet.client.collector.pusher.Pusher.add")
    def test_process_results_with_pusher(self, mock_pusher_add):
        c = collector.Collector("some_url", {}, [])
        c.death.set()
        c.queue = collections.deque(xrange(100))
        c.process_results()
        self.assertEqual(100, mock_pusher_add.call_count)

    @mock.patch("sys.stdout", new_callable=StringIO.StringIO)
    def test_process_results_without_pusher(self, mock_stdout):
        c = collector.Collector(None, {}, [])
        c.death.set()
        c.queue = collections.deque(xrange(10))
        c.process_results()
        self.assertEqual("\n".join(str(i) for i in xrange(10)) + "\n",
                         mock_stdout.getvalue())

    @mock.patch("netmet.client.collector.Collector.gen_periodic_ping")
    @mock.patch("netmet.client.collector.Collector.gen_periodic_http_ping")
    def test_start_and_stop_no_pusher(self, mock_gen_ping, mock_gen_http_ping):
        mock_gen_ping.return_value = str
        mock_gen_http_ping.return_value = str
        c = collector.Collector(None, {}, [1, 2, 3])
        c.start()
        time.sleep(0.05)
        c.stop()

    @mock.patch("netmet.client.collector.Collector.gen_periodic_ping")
    @mock.patch("netmet.client.collector.Collector.gen_periodic_http_ping")
    def test_start_and_stop_w_pusher(self, mock_gen_ping, mock_gen_http_ping):
        mock_gen_ping.return_value = str
        mock_gen_http_ping.return_value = str
        c = collector.Collector("netmet_url", {}, [1, 2, 3])
        c.start()
        time.sleep(0.05)
        c.stop()
