# Copyright 2017: GoDaddy Inc.

import time

import mock

from netmet.server import db
from netmet.server import mesher
from tests.unit import test


class MesherTestCase(test.TestCase):

    keys = ["ip", "port", "host", "dc", "az"]

    def tearDown(self):
        super(MesherTestCase, self).tearDown()
        mesher.Mesher.destroy()

    @mock.patch("netmet.server.mesher.Mesher._job")
    def test_create(self, mock_job):
        mesher.Mesher.create("netmet_server_url")
        time.sleep(0.1)
        mesher.Mesher.destroy()
        self.assertEqual(1, mock_job.call_count)
        mock_job.assert_called_once_with()

    @mock.patch("netmet.server.mesher.LOG.exception")
    @mock.patch("netmet.server.db.get")
    def test_job_failed(self, mock_db, mock_log):
        mock_db.return_value.server_config_get.side_effect = Exception
        mesher.Mesher()._job()
        self.assertEqual(1, mock_log.call_count)
        mock_log.assert_called_once_with(mesher.Mesher.update_failed_msg)

    @mock.patch("netmet.server.mesher.LOG.info")
    @mock.patch("netmet.server.db.DB.server_config_get")
    @mock.patch("netmet.server.db.get")
    def test_job_no_config(self, mock_db_get, mock_server_config_get,
                           mock_log_info):
        mock_server_config_get.return_value = None
        mock_db_get.return_value = db.DB()

        mesher.Mesher()._job()
        mock_log_info.assert_called_once_with(mesher.Mesher.no_changes_msg)
        self.assertEqual(1, mock_db_get.call_count)
        self.assertEqual(1, mock_log_info.call_count)

    @mock.patch("netmet.server.mesher.LOG.info")
    @mock.patch("netmet.server.db.DB.server_config_get")
    @mock.patch("netmet.server.db.get")
    def test_job_not_applied(self, mock_db_get, mock_server_config_get,
                             mock_log_info):
        mock_server_config_get.return_value = {"applied": False}
        mock_db_get.return_value = db.DB()

        mesher.Mesher()._job()
        mock_log_info.assert_called_once_with(mesher.Mesher.no_changes_msg)
        self.assertEqual(1, mock_db_get.call_count)
        self.assertEqual(1, mock_log_info.call_count)

    @mock.patch("netmet.server.mesher.LOG.info")
    @mock.patch("netmet.server.db.DB.server_config_get")
    @mock.patch("netmet.server.db.get")
    def test_job_applied_and_meshed(self, mock_db_get, mock_server_config_get,
                                    mock_log_info):

        mock_server_config_get.return_value = {"applied": True, "meshed": True}
        mock_db_get.return_value = db.DB()

        mesher.Mesher()._job()
        mock_log_info.assert_called_once_with(mesher.Mesher.no_changes_msg)
        self.assertEqual(1, mock_db_get.call_count)
        self.assertEqual(1, mock_log_info.call_count)

    @mock.patch("netmet.server.mesher.requests")
    @mock.patch("netmet.server.mesher.LOG")
    @mock.patch("netmet.server.db.DB.clients_get")
    @mock.patch("netmet.server.db.DB.server_config_meshed")
    @mock.patch("netmet.server.db.DB.server_config_get")
    @mock.patch("netmet.server.db.get")
    def test_job_applied_not_meshed(
            self, mock_db_get, mock_server_config_get,
            mock_server_config_meshed, mock_clients_get, mock_log,
            mock_requests):
        mock_server_config_get.return_value = {
            "id": "10", "applied": True, "meshed": False}
        db_ = db.DB()
        db_.own_url = "some_stuff"
        db_.elastic = mock.MagicMock()
        mock_db_get.return_value = db_
        mock_clients_get.return_value = [
            {k: str(i) for k in self.keys} for i in xrange(5)
        ]

        mesh = mesher.Mesher()
        mesh.netmet_server_url = "some_url"
        mesh._job()
        mock_log.info.assert_called_once_with(mesher.Mesher.new_config_msg)
        self.assertEqual(1, mock_log.info.call_count)
