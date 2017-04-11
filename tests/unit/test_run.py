# Copyright 2017: Godaddy Inc.

import os

from gevent import wsgi
import mock

from netmet import run
from tests.unit import test


class RunTestCase(test.TestCase):

    @mock.patch.dict(os.environ, {})
    def test_load_no_app(self):
        self.assertRaises(ValueError, run.load)

    @mock.patch.dict(os.environ, {"APP": "not_a_valid"})
    def test_load_wrong_app(self):
        self.assertRaises(ValueError, run.load)

    @mock.patch.dict(os.environ, {"APP": "server", "HOST": ""})
    @mock.patch("netmet.server.main.load")
    def test_load_server_app(self, mock_load):
        http_server = run.load()
        mock_load.assert_called_once_with()
        self.assertEqual(mock_load.call_count, 1)
        self.assertIsInstance(http_server, wsgi.WSGIServer)
        self.assertEqual("", http_server.server_host)
        self.assertEqual(5000, http_server.server_port)

    @mock.patch.dict(os.environ, {"APP": "client", "HOST": ""})
    @mock.patch("netmet.client.main.load")
    def test_load_client_app(self, mock_load):
        http_server = run.load()
        mock_load.assert_called_once_with()
        self.assertEqual(mock_load.call_count, 1)
        self.assertIsInstance(http_server, wsgi.WSGIServer)
        self.assertEqual("", http_server.server_host)
        self.assertEqual(5000, http_server.server_port)

    @mock.patch.dict(os.environ,
                     {"APP": "client", "PORT": "80", "HOST": "1.2.3.4"})
    @mock.patch("netmet.client.main.load")
    def test_load_non_default_port_and_host(self, mock_load):
        http_server = run.load()
        self.assertEqual("1.2.3.4", http_server.server_host)
        self.assertEqual(80, http_server.server_port)

    @mock.patch.dict(os.environ, {"APP": "client"})
    @mock.patch("netmet.run.wsgi.WSGIServer.serve_forever")
    @mock.patch("netmet.client.main.load")
    def test_run(self, mock_load, mock_serve_forever):
        run.run()
        self.assertEqual(mock_serve_forever.call_count, 1)
        mock_serve_forever.assert_called_once_with()
