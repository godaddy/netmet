# Copyright 2017: GoDaddy Inc.

import json

import mock
import requests

from netmet.client import conf
from tests.unit import test


class ConfTestCase(test.TestCase):

    @mock.patch("netmet.client.conf.open", create=True)
    def test_restore_no_url(self, mock_open):
        mock_open.side_effect = mock.mock_open(read_data="{}").return_value
        conf.restore(100)

    @mock.patch("netmet.client.conf.requests.post")
    @mock.patch("netmet.client.conf.restore._die.wait")
    @mock.patch("netmet.client.conf.open", create=True)
    def test_restore_io_error(self, mock_open, mock_wait, mock_post):
        mock_open.side_effect = [mock.mock_open(
            read_data=json.dumps({"refresh_conf_url": "aa"})).return_value
        ]
        mock_post.side_effect = Exception
        conf.restore(100)
        mock_wait.assert_called_once_with(0.25)

    @mock.patch("netmet.client.conf.LOG.warning")
    @mock.patch("netmet.client.conf.requests.post")
    @mock.patch("netmet.client.conf.restore._die.wait")
    @mock.patch("netmet.client.conf.open", create=True)
    def test_restore_success_scenario(self, mock_open, mock_wait,
                                      mock_post, mock_warn):

        data = json.dumps({"refresh_conf_url": "aa"})
        mock_open.side_effect = [mock.mock_open(read_data=data).return_value,
                                 mock.mock_open(read_data=data).return_value,
                                 mock.mock_open(read_data=data).return_value]

        mock_post.side_effect = [
            requests.exceptions.RequestException,
            mock.Mock(status_code=500),
            mock.Mock(status_code=200)
        ]
        conf.restore(50)
        mock_open.assert_has_calls(
            [mock.call(conf._RUNTIME_CONF_FILE % 50, "rw")] * 3)
        self.assertEqual(1, mock_warn.call_count)
        mock_post.assert_has_calls(
            [mock.call("aa"), mock.call("aa"), mock.call("aa")]
        )
        mock_wait.assert_has_calls(
            [mock.call(0.25), mock.call(1), mock.call(1)])

    @mock.patch("netmet.client.conf.os.remove")
    @mock.patch("netmet.client.conf.requests.post")
    @mock.patch("netmet.client.conf.restore._die.wait")
    @mock.patch("netmet.client.conf.open", create=True)
    def test_restore_404_scenario(self, mock_open, mock_wait, mock_post,
                                  mock_remove):
        mock_open.side_effect = [mock.mock_open(
            read_data=json.dumps({"refresh_conf_url": "aa"})).return_value
        ]
        mock_post.side_effect = [mock.Mock(status_code=404)]
        conf.restore(50)
        mock_remove.assert_called_once_with(conf._RUNTIME_CONF_FILE % 50)
        mock_wait.assert_called_once_with(0.25)

    @mock.patch("netmet.client.conf.open", create=True)
    def test_restore_url_get(self, mock_open):
        mock_open.side_effect = [
            mock.mock_open(
                read_data=json.dumps({"refresh_conf_url": "aa"})).return_value,
            mock.mock_open(read_data=json.dumps({})).return_value
        ]
        self.assertEqual("aa", conf.restore_url_get(50))
        self.assertIsNone(conf.restore_url_get(55))
        mock_open.assert_has_calls(
            [mock.call(conf._RUNTIME_CONF_FILE % 50, "rw"),
             mock.call(conf._RUNTIME_CONF_FILE % 55, "rw")])

    @mock.patch("netmet.client.conf.LOG.exception")
    @mock.patch("netmet.client.conf.open", create=True)
    def test_retore_url_get_no_file(self, mock_open, mock_log_exc):
        mock_open.side_effect = OSError
        self.assertIsNone(conf.restore_url_get(80))
        mock_open.assert_called_once_with(conf._RUNTIME_CONF_FILE % 80, "rw")
        self.assertEqual(1, mock_log_exc.call_count)

    @mock.patch("netmet.client.conf.json.dump")
    @mock.patch("netmet.client.conf.os.path.exists")
    @mock.patch("netmet.client.conf.open", create=True)
    def test_restore_url_set(self, mock_open, mock_exists, mock_json_dump):
        mock_exists.return_value = True
        mock_open.return_value = mock.MagicMock()
        conf.restore_url_set("a", "b", 80)

        mock_exists.assert_called_once_with(conf._RUNTIME_CONF_DIR)
        mock_open.assert_called_once_with(conf._RUNTIME_CONF_FILE % 80, "w+")
        url = conf._RESTORE_API % {"server": "a", "host": "b", "port": 80}
        mock_json_dump.assert_called_once_with(
            {"refresh_conf_url": url},
            mock_open.return_value.__enter__.return_value)

    @mock.patch("netmet.client.conf.json.dump")
    @mock.patch("netmet.client.conf.os.mkdir")
    @mock.patch("netmet.client.conf.os.path.exists")
    @mock.patch("netmet.client.conf.open", create=True)
    def test_restore_url_set_no_dir(self, mock_open, mock_exists, mock_mkdir,
                                    mock_json_dump):
        mock_exists.return_value = False
        mock_open.return_value = mock.MagicMock()
        conf.restore_url_set("c", "d", 80)
        mock_open.assert_called_once_with(conf._RUNTIME_CONF_FILE % 80, "w+")
        url = conf._RESTORE_API % {"server": "c", "host": "d", "port": 80}

        mock_json_dump.assert_called_once_with(
            {"refresh_conf_url": url},
            mock_open.return_value.__enter__.return_value)

    @mock.patch("netmet.client.conf.LOG.exception")
    @mock.patch("netmet.client.conf.os.path.exists")
    def test_restore_url_set_unexpected_failure(self, mock_path_exists,
                                                mock_log_exc):
        mock_path_exists.side_effect = Exception
        conf.restore_url_set("any", "any", 80)
        self.assertEqual(1, mock_log_exc.call_count)

    @mock.patch("netmet.client.conf.os.remove")
    def test_restore_url_clear(self, mock_remove):
        conf.restore_url_clear(90)
        mock_remove.assert_called_once_with(conf._RUNTIME_CONF_FILE % 90)
        self.assertEqual(1, mock_remove.call_count)

    @mock.patch("netmet.client.conf.os.remove")
    def test_restore_url_clear_no_file(self, mock_remove):
        mock_remove.side_effect = OSError
        conf.restore_url_clear(500)
        mock_remove.assert_called_once_with(conf._RUNTIME_CONF_FILE % 500)
        self.assertEqual(1, mock_remove.call_count)
