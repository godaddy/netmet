# Copyright 2017: Godaddy Inc.

import datetime

import mock

from netmet.utils import status
from tests.unit import test


class StatusTestCase(test.TestCase):

    def test_count_request(self):
        self.stats = status.Stats()

        expected = {
            "total": 0,
            "total_duration": 0,
            "avg_duration": 0,
            "success": 0,
            "success_rate": 1,
            "per_code": {}
        }
        for k, v in expected.iteritems():
            self.assertEqual(self.stats.stats["requests"][k], v)

        self.stats.count_request(400, 1.0)
        self.stats.count_request(400, 2.0)
        self.stats.count_request(500, 2.0)
        self.stats.count_request(200, 3.0)

        expected["total"] = 4
        expected["success"] = 3
        expected["success_rate"] = 3 / 4.0
        expected["total_duration"] = 8.0
        expected["avg_duration"] = 2.0
        expected["per_code"] = {400: 2, 500: 1, 200: 1}
        for k, v in expected.iteritems():
            self.assertEqual(self.stats.stats["requests"][k], v)

    def test_status_response(self):
        stats = status.Stats()
        status_ = stats.status()

        self.assertEqual(status_["started_at"], stats.started_at.isoformat())
        self.assertIsInstance(status_["runtime"], int)
        self.assertIsInstance(status_["stats"], dict)

        self.assertTrue(status_ is not stats.stats)
        self.assertEqual(status_["stats"], stats.stats)

    def test_status_respnose_runtime(self):
        started_at = datetime.datetime(2017, 4, 10, 14, 15, 43, 572065)
        running_1 = datetime.datetime(2017, 4, 10, 14, 20, 46, 572065)
        running_2 = datetime.datetime(2017, 4, 10, 14, 20, 47, 572065)

        with mock.patch("netmet.utils.status.datetime.datetime") as mock_date:
            mock_date.now.side_effect = [started_at, running_1, running_2]

            self.stats = status.Stats()
            self.assertEqual(self.stats.started_at, started_at)
            self.assertEqual(mock_date.now.call_count, 1)

            self.assertEqual(self.stats.status()["runtime"], 303)
            self.assertEqual(mock_date.now.call_count, 2)

            self.assertEqual(self.stats.status()["runtime"], 304)
            self.assertEqual(mock_date.now.call_count, 3)


class TestStatusMiddleware(test.TestCase):

    def test_init(self):
        app = mock.Mock()
        app.wsgi_app = mock.Mock()
        app.route = mock.MagicMock()
        middleware = status.StatusMiddleware(app)

        self.assertEqual(middleware.app, app.wsgi_app)
        app.route.assert_called_once_with("/status", methods=["GET"])
        app.route.return_value.assert_called()

    def test_call(self):
        app = mock.MagicMock()
        request = mock.MagicMock()

        s = status.StatusMiddleware(app)
        response = s(request)
        self.assertEqual(response, request.get_response.return_value)
        request.get_response.assert_called_once_with(app.wsgi_app)
        self.assertEqual(s.stats.stats["requests"]["total"], 1)
