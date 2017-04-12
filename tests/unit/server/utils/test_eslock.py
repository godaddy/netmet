# Copyright 2017: GoDaddy Inc.

import elasticsearch
import mock

from netmet import exceptions
from netmet.server import db
from netmet.server.utils import eslock
from tests.unit import test


class PingTestCase(test.TestCase):

    def test_init(self):
        g = eslock.Glock("some_name")
        self.assertEqual("some_name", g.name)
        self.assertEqual(10, g.ttl)
        self.assertFalse(g.accuired)

    @mock.patch("netmet.server.utils.eslock.db.get")
    def test_lock_accuired(self, mock_get):
        db_ = db.DB()
        db_.elastic = mock.MagicMock()
        db_.own_url = "upsis"
        mock_get.return_value = db_

        g = eslock.Glock("some_name")
        with g:
            self.assertTrue(g.accuired)
            self.assertRaises(exceptions.GlobalLockException, g.__enter__)

        self.assertFalse(g.accuired)

    @mock.patch("netmet.server.utils.eslock.db.get")
    def test_lock_failed(self, mock_get):
        db_ = db.DB()
        db_.own_url = "upsis"
        db_.elastic = mock.MagicMock()
        db_.elastic.indices.create.side_effect = (
            elasticsearch.exceptions.ElasticsearchException)
        mock_get.return_value = db_

        g = eslock.Glock("some_name")
        self.assertRaises(exceptions.GlobalLockException, g.__enter__)
