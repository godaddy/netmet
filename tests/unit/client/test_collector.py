# Copyright 2017: GoDaddy Inc.

import collections
import StringIO
import time

import futurist.periodics
import mock

from netmet.client import collector
from netmet.utils import pusher
from tests.unit import test


class CollectorTestCase(test.TestCase):

    def test_init_standalone(self):
        host = mock.MagicMock()
        hosts = [mock.MagicMock()]

        c = collector.Collector(None, host, hosts)
        self.assertEqual(host, c.client_host)
        self.assertEqual(5, c.period)
        self.assertEqual(1, c.timeout)
        self.assertEqual(55, c.packet_size)
        self.assertIsNone(c.pusher)

    def test_init_full(self):
        host = mock.MagicMock()
        hosts = [mock.MagicMock()]

        c = collector.Collector("http://netmet_url", host, hosts,
                                period=10, timeout=2, packet_size=5)
        self.assertEqual(host, c.client_host)
        self.assertEqual(10, c.period)
        self.assertEqual(2, c.timeout)
        self.assertEqual(5, c.packet_size)
        self.assertIsInstance(c.pusher, pusher.Pusher)

    @mock.patch("netmet.client.collector.ping.Ping.ping")
    def test_gen_periodic_ping(self, mock_ping):
        client_host = mock.MagicMock()
        dest_host = {"ip": "1.1.1.1"}
        mock_ping.return_value = {
            "ret_code": 0,
            "rtt": 10,
            "timestamp": "ttt",
            "packet_size": 55
        }

        c = collector.Collector("some_url", client_host, [])
        c.gen_periodic_ping(dest_host)()
        self.assertEqual(1, len(c.queue))
        expected = {
            "client_src": client_host,
            "client_dest": dest_host,
            "protocol": "icmp",
            "timestamp": "ttt",
            "latency": 10,
            "packet_size": 55,
            "lost": 0,
            "transmitted": 1,
            "ret_code": 0
        }
        self.assertEqual(expected, c.queue.pop()["east-west"])

    @mock.patch("netmet.client.collector.LOG")
    @mock.patch("netmet.client.collector.ping.Ping.ping")
    def test_gen_periodic_ping_raises(self, mock_ping, mock_log):
        c = collector.Collector("some_url", {}, [])
        mock_ping.side_effect = Exception
        ping_ = c.gen_periodic_ping({"ip": "1.2.3.4"})
        ping_()

        mock_log.exception.assert_called_once_with(c.pinger_failed_msg)
        self.assertEqual(1, mock_log.exception.call_count)

    @mock.patch("netmet.client.collector.datetime")
    @mock.patch("netmet.client.collector.monotonic.monotonic")
    @mock.patch("netmet.client.collector.requests.get")
    def test_gen_periodic_http_ping(self, mock_get, mock_monotonic,
                                    mock_datetime):
        client_host = mock.MagicMock()
        dest_host = {"ip": "1.1.1.1", "host": "1.2.3.4", "port": 80}
        mock_datetime.datetime.now.return_value.isoformat.return_value = "aaa"

        c = collector.Collector("some_url", client_host, [dest_host])
        mock_monotonic.side_effect = [1, 2]
        mock_get.return_value = mock.MagicMock(
            content="Q" * 10, status_code=200)
        c.gen_periodic_http_ping(dest_host)()
        self.assertEqual(1, len(c.queue))

        expected = {
            "client_src": client_host,
            "client_dest": dest_host,
            "protocol": "http",
            "timestamp": "aaa",
            "latency": 1000,
            "packet_size": 10,
            "lost": 0,
            "transmitted": 1,
            "ret_code": 200
        }

        self.assertEqual(expected, c.queue.pop()["east-west"])

    def test_gen_periodic_http_ping_requests_raises(self):
        pass

    def test_gen_periodic_http_ping_raises(self):
        pass

    @mock.patch("netmet.client.collector.pusher.Pusher.add")
    def test_process_results_with_pusher(self, mock_pusher_add):
        c = collector.Collector("some_url", {}, [])
        c.queue = collections.deque(xrange(100))
        c.process_results()
        self.assertEqual(100, mock_pusher_add.call_count)

    @mock.patch("sys.stdout", new_callable=StringIO.StringIO)
    def test_process_results_without_pusher(self, mock_stdout):
        c = collector.Collector(None, {}, [])
        c.queue = collections.deque(xrange(10))
        c.process_results()
        self.assertEqual("\n".join(str(i) for i in xrange(10)) + "\n",
                         mock_stdout.getvalue())

    @mock.patch("netmet.client.collector.Collector.gen_periodic_ping")
    @mock.patch("netmet.client.collector.Collector.gen_periodic_http_ping")
    def test_start_and_stop_no_pusher(self, mock_gen_ping, mock_gen_http_ping):

        @futurist.periodics.periodic(1)
        def noop():
            pass

        mock_gen_ping.return_value = noop
        mock_gen_http_ping.return_value = noop

        c = collector.Collector(None, {}, [1, 2, 3])
        c.start()
        time.sleep(0.1)
        c.stop()

    @mock.patch("netmet.client.collector.Collector.gen_periodic_ping")
    @mock.patch("netmet.client.collector.Collector.gen_periodic_http_ping")
    def test_start_and_stop_w_pusher(self, mock_gen_ping, mock_gen_http_ping):

        @futurist.periodics.periodic(1)
        def noop():
            pass

        mock_gen_ping.return_value = noop
        mock_gen_http_ping.return_value = noop
        c = collector.Collector("netmet_url", {}, [1, 2, 3])
        c.start()
        time.sleep(0.1)
        c.stop()
