# Copyright 2017: GoDaddy Inc.

import mock

from netmet.utils import secure
from tests.unit import test


class GenTestCase(test.TestCase):

    def test_generate_digest(self):
        self.assertEqual(type(secure.generate_digest("a", "b")), str)

    def test_is_valid_digest(self):
        digest = secure.generate_digest("abc", "1")
        self.assertTrue(secure.is_valid_digest(digest, "abc", ["2", "3", "1"]))
        self.assertFalse(secure.is_valid_digest(digest, "abc", ["2", "3"]))

    def test_gen_hmac_headers(self):
        h = secure.gen_hmac_headers("d", hmac="h")
        self.assertIn("X-AUTH-HMAC-TIMESTAMP", h)
        self.assertIn("X-AUTH-HMAC-DIGEST", h)

        self.assertTrue(secure.is_valid_digest(
            h["X-AUTH-HMAC-DIGEST"], "d" + h["X-AUTH-HMAC-TIMESTAMP"], ["h"]))

    @mock.patch("netmet.config.get")
    def test_gen_hmac_headers_none(self, mock_get):
        mock_get.return_value = []

        self.assertEqual({}, secure.gen_hmac_headers("any_data"))
        mock_get.assert_called_once_with("hmac_keys")

    @mock.patch("netmet.config.get")
    def test_get_hmac_headers_env(self, mock_get):
        mock_get.return_value = ["a", "b"]

        h = secure.gen_hmac_headers("d")
        self.assertIn("X-AUTH-HMAC-TIMESTAMP", h)
        self.assertIn("X-AUTH-HMAC-DIGEST", h)
        self.assertTrue(secure.is_valid_digest(
            h["X-AUTH-HMAC-DIGEST"], "d" + h["X-AUTH-HMAC-TIMESTAMP"], ["a"]))

    @mock.patch("netmet.config.get")
    def test_check_hmac_auth_skip(self, mock_get):
        mock_get.return_value = True

        @secure.check_hmac_auth
        def f(a, b):
            return a - b

        self.assertEqual(1, f(3, 2))
        mock_get.assert_called_once_with("hmac_skip_check")

    @mock.patch("netmet.utils.secure.flask")
    @mock.patch("netmet.utils.secure.config.get")
    def test_check_hmac_auth_no_header(self, mock_conf_get, mock_flask):
        mock_conf_get.return_value = False
        mock_flask.request.headers = {}

        @secure.check_hmac_auth
        def f(a, b):
            return a - b

        self.assertEqual(403, f(3, 2)[1])

    @mock.patch("netmet.utils.secure.datetime")
    @mock.patch("netmet.utils.secure.flask")
    @mock.patch("netmet.utils.secure.config.get")
    def test_check_hmac_auth_time(self, mock_conf_get, mock_flask, mock_dt):
        mock_conf_get.return_value = False
        mock_dt.datetime.now.return_value.strftime.return_value = "41"
        mock_flask.request.headers = {
            "X-AUTH-HMAC-TIMESTAMP": "10",
            "X-AUTH-HMAC-DIGEST": "b"
        }

        @secure.check_hmac_auth
        def f(a, b):
            return a - b

        self.assertEqual(403, f(3, 2)[1])
        mock_dt.datetime.now.return_value.strftime.assert_called_once_with(
            "%s")

    @mock.patch("netmet.utils.secure.datetime")
    @mock.patch("netmet.utils.secure.flask")
    @mock.patch("netmet.utils.secure.config.get")
    def test_check_hmac_auth_invalid(self, mock_conf_get, mock_flask, mock_dt):
        mock_dt.datetime.now.return_value.strftime.return_value = "22"
        cfg = {"hmac_skip_check": False, "hmac_keys": ["a", "b"]}
        mock_conf_get.side_effect = lambda x: cfg[x]

        mock_flask.request.get_data.return_value = "some_data"
        mock_flask.request.headers = {
            "X-AUTH-HMAC-TIMESTAMP": "1", "X-AUTH-HMAC-DIGEST": "wrong_digest"}

        @secure.check_hmac_auth
        def f(a, b):
            return a - b

        self.assertEqual(403, f(3, 2)[1])

    @mock.patch("netmet.utils.secure.flask")
    @mock.patch("netmet.utils.secure.config.get")
    def test_check_basic_auth_invlid(self, mock_conf_get, mock_flask):
        mock_conf_get.return_value = ["users"]
        mock_flask.request.authorization = None
        mock_flask.Response = mock.MagicMock()

        @secure.check_basic_auth
        def f():
            pass

        self.assertEqual(mock_flask.Response.return_value, f())

    @mock.patch("netmet.utils.secure.config.get")
    def test_check_basic_auth_no_users(self, mock_conf_get):
        mock_conf_get.return_value = []

        @secure.check_basic_auth
        def f(a, b):
            return b - a

        self.assertEqual(-1, f(3, 2))
