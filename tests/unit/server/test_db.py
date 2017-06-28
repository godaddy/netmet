# Copyright 2017: GoDaddy Inc.

import json

import elasticsearch
import mock

from netmet import exceptions
from netmet.server import db
from tests.unit import test


class DBTestCase(test.TestCase):

    def tearDown(self):
        db.DB.destroy()
        super(DBTestCase, self).tearDown()

    def test_get_not_init(self):
        self.assertIsNone(db.get())

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    @mock.patch("netmet.server.db.DB._rollover_data")
    @mock.patch("netmet.server.db.DB._ensure_schema")
    @mock.patch("netmet.server.db.DB._ensure_elastic")
    def test_create_mocked_all(self, mock_ensure_elastic, mock_ensure_schema,
                               mock_rollover_data, mock_elastic):
        elastics = ["elastic"]
        db.DB.create("own_url", elastics)
        self.assertIsInstance(db.get(), db.DB)
        self.assertEqual(db.get().own_url, "own_url")
        self.assertEqual(db.get().elastic_urls, elastics)
        mock_ensure_elastic.assert_called_once_with()
        mock_ensure_schema.assert_called_once_with()
        mock_rollover_data.assert_called_once_with()
        mock_elastic.assert_called_once_with(elastics)

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_create_mocked_only_elastic(self, mock_elastic):
        elastics = ["elastic"]

        melastic = mock_elastic.return_value
        melastic.indices.exists.side_effect = [True, False, True]
        melastic.indices.create.side_effect = (
            elasticsearch.exceptions.ElasticsearchException)

        melastic.indices.exists_alias.side_effect = [False, True]

        db.DB.create("own_url", elastics)
        mock_elastic.assert_called_once_with(elastics)

        melastic.info.assert_called_once_with()
        melastic.indices.exists.assert_has_calls(
            [mock.call("netmet_catalog"), mock.call("netmet_events")],
            any_order=True)

        melastic.indices.create.assert_has_calls(
            [mock.call(index="netmet_events", body=db.DB._EVENTS)])

        melastic.indices.rollover.assert_called_once_with(
            alias="netmet_data_v2", body=mock.ANY)

        melastic.indices.exists_alias.assert_has_calls(
            [
                mock.call(name="netmet_data_v2"),
                mock.call(name="netmet_data_v2")
            ],
            any_order=True)

    @mock.patch("netmet.server.db.DB._rollover_data")
    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_job(self, mock_elastic, mock_rollover_data):
        db.DB()._job()
        self.assertEqual(0, mock_rollover_data.call_count)

    @mock.patch("netmet.server.db.DB._rollover_data")
    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_job_inited(self, mock_elastic, mock_rollover_data):
        db.DB.create("own_url", ["elastics"])
        self.assertEqual(1, mock_rollover_data.call_count)
        db.get()._job()
        self.assertEqual(2, mock_rollover_data.call_count)

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_clients_get(self, mock_elastic):
        mock_elastic.return_value.search.return_value = {
            "hits": {"hits": [{"_source": {"a": 1}}, {"_source": {"a": 2}}]}
        }
        db.DB.create("a", ["b"])
        self.assertEqual(db.get().clients_get(), [{"a": 1}, {"a": 2}])

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_clients_set(self, mock_elastic):
        fake_catalog = [{"a": 1}, {"b": 2}]
        expected_body = '{"index": {}}\n{"a": 1}\n{"index": {}}\n{"b": 2}'
        db.DB.create("a", ["b"])
        db.get().clients_set(fake_catalog)

        mock_elastic.return_value.delete_by_query.assert_called_once_with(
            index="netmet_catalog", doc_type="clients",
            body={"query": {"match_all": {}}})

        mock_elastic.return_value.bulk.assert_called_once_with(
            index="netmet_catalog", doc_type="clients", body=expected_body,
            refresh="true")

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_server_config_get(self, mock_elastic):
        config = {
            "config": json.dumps({"some": "stuff"}),
            "applied": True,
            "meshed": "False"
        }

        expected_result = {
            "id": "id",
            "config": {"some": "stuff"},
            "applied": True,
            "meshed": "False"
        }

        query = {
            "sort": {"timestamp": {"order": "desc"}},
            "query": {"term": {"applied": True}}
        }

        mock_elastic.return_value.search.side_effect = [
            {"hits": {"hits": [{"_id": "id", "_source": config}]}},
            {"hits": {"hits": []}}
        ]
        db.DB.create("a", ["b"])
        self.assertEqual(expected_result,
                         db.get().server_config_get(only_applied=True))
        mock_elastic.return_value.search.assert_called_once_with(
            index="netmet_catalog", doc_type="config", body=query, size=1)

        self.assertIsNone(db.get().server_config_get(only_applied=True))

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_server_config_add(self, mock_elastic):
        db.DB.create("a", ["b"])
        db.get().server_config_add({"a": 1})

        expected_body = {
            "config": '{"a": 1}',
            "applied": False,
            "meshed": False,
            "timestamp": mock.ANY
        }
        mock_elastic.return_value.index.assert_called_once_with(
            index="netmet_catalog", doc_type="config", body=expected_body,
            refresh="true")

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_server_config_apply(self, mock_elastic):
        db.DB.create("a", ["b"])
        db.get().server_config_apply("id1")
        mock_elastic.return_value.update.assert_called_once_with(
            index="netmet_catalog", doc_type="config", id="id1",
            body={"doc": {"applied": True}}, refresh="true")

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_server_config_meshed(self, mock_elastic):
        db.DB.create("a", ["b"])
        db.get().server_config_meshed("id2")
        mock_elastic.return_value.update.assert_called_once_with(
            index="netmet_catalog", doc_type="config", id="id2",
            body={"doc": {"meshed": True}}, refresh="true")

    def test_metrics_add_wrong_type(self):
        self.assertRaises(ValueError,
                          db.DB().metrics_add, "some_invalid_type", [])

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_metrics_add(self, mock_elastic):
        mock_elastic.return_value.bulk.return_value = {
            "items": [
                {"index": {"status": 200}},
                {"index": {"status": 200}},
                {"index": {"status": 500}}
            ]
        }
        db.DB.create("a", ["b"])
        doc = {"a": {"b": 1}, "c": 2}
        expected_bulk = '{"index": {}}\n{"c": 2, "a.b": 1}'
        self.assertEqual({200: 2, 500: 1},
                         db.get().metrics_add("east-west", [doc]))
        mock_elastic.return_value.bulk.assert_called_once_with(
            index="netmet_data_v2", doc_type="east-west", body=expected_bulk)

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_event_get(self, mock_elastic):
        mock_elastic.return_value.get.return_value = {
            "found": True, "_version": 2, "_source": {"a": 1}
        }
        db.DB.create("a", ["b"])
        self.assertEqual((2, {"a": 1}), db.get().event_get("some_id"))
        mock_elastic.return_value.get.assert_called_once_with(
            index="netmet_events", doc_type="events", id="some_id")

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_event_get_not_found(self, mock_elastic):
        mock_elastic.return_value.get.return_value = {"found": False}
        db.DB.create("a", ["b"])
        self.assertRaises(exceptions.DBRecordNotFound,
                          db.get().event_get, "some_id2")
        mock_elastic.return_value.get.assert_called_once_with(
            index="netmet_events", doc_type="events", id="some_id2")

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_events_list(self, mock_elastic):
        mock_elastic.return_value.search.return_value = {
            "hits": {"hits": [{"_source": {"a": 1}}, {"_source": {"b": 2}}]}
        }

        db.DB.create("a", ["b"])
        self.assertEqual([{"a": 1}, {"b": 2}],
                         db.get().events_list(10, 20, only_active=True))

        expected_query = {
            "from": 10,
            "size": 20,
            "query": {
                "bool": {
                    "must_not": [{"term": {"status": "deleted"}}],
                    "should": [
                        {"range": {"finished_at": {"gt": "now/m"}}},
                        {"missing": {"field": "finished_at"}}
                    ]
                },
                "filter": [{"range": {"started_at": {"lte": "now/m"}}}]
            }
        }
        mock_elastic.return_value.search.assert_called_once_with(
            index="netmet_events", body=expected_query)

    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    @mock.patch("netmet.server.db.DB.event_get")
    def test_event_update(self, mock_event_get, mock_elastic):
        mock_elastic.return_value.update.side_effect = [
            {"result": "updated"}, {"result": "noop"}
        ]
        mock_event_get.return_value = (2, {})
        db.DB.create("a", ["b"])
        self.assertTrue(db.get()._event_update("some_id", {"a": 1}))
        mock_event_get.assert_called_once_with("some_id")
        mock_elastic.return_value.update.assert_called_once_with(
            index="netmet_events", doc_type="events", id="some_id",
            body={"doc": {"a": 1}}, refresh='true', version=2)

        self.assertRaises(exceptions.DBConflict,
                          db.get()._event_update, "some_other_id", {"a": 1})

    @mock.patch("netmet.server.db.DB.event_get")
    def test_event_update_version_conflict(self, mock_event_get):
        mock_event_get.return_value = (1, {})

        self.assertRaises(exceptions.DBConflict,
                          db.DB()._event_update, "some_id", {}, version=2)

    def test_get_query(self):
        event = {
            "started_at": "a",
            "finished_at": "b",
            "traffic_to.type": "to_type",
            "traffic_to.value": "to_value",
            "traffic_from.type": "from_type",
            "traffic_from.value": "from_value"
        }

        expected_filter = [
            {"range": {"timestamp": {"gte": "a", "lte": "b"}}},
            {"term": {"client_dest.to_type": "to_value"}},
            {"term": {"client_src.from_type": "from_value"}}
        ]
        id_query = {"term": {"events": "some_id"}}

        self.assertEqual(
            {
                "bool": {
                    "filter": expected_filter,
                    "must": [],
                    "must_not": [id_query]
                }
            },
            db.DB()._get_query(event, "some_id", "add")),

        self.assertEqual(
            {
                "bool": {
                    "filter": expected_filter,
                    "must": [id_query],
                    "must_not": []
                }
            },
            db.DB()._get_query(event, "some_id", "remove"))

    def test_get_script(self):
        self.assertEqual(
            {
                "inline": "ctx._source.events.add('some_id')",
                "lang": "painless"
            },
            db.DB()._get_script("some_id", "add"))

        self.assertEqual(
            {
                "inline": "ctx._source.events.remove"
                          "(ctx._source.events.indexOf('some_id2'))",
                "lang": "painless"
            },
            db.DB()._get_script("some_id2", "remove"))

    @mock.patch("netmet.server.db.DB._get_script")
    @mock.patch("netmet.server.db.DB._get_query")
    @mock.patch("netmet.server.db.DB.event_get")
    @mock.patch("netmet.server.db.DB._event_update")
    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_event_upgrade_metrics(self, mock_elastic, mock_event_update,
                                   mock_event_get, mock_get_query,
                                   mock_get_script):
        melastic = mock_elastic.return_value

        mock_event_get.return_value = (1, {"task_id": "some_task2"})
        melastic.tasks.get.return_value = {"completed": True}
        melastic.update_by_query.return_value = {"task": "some_task"}

        db.DB.create("a", ["b"])
        db.get()._event_upgrade_metrics("some_id", "add")

        mock_event_get.assert_called_once_with("some_id")
        melastic.tasks.get.assert_called_once_with(task_id="some_task2")
        mock_event_update.assert_has_calls([
            mock.call("some_id", {"task_id": None, "status": "updating"},
                      version=1),
            mock.call("some_id", {"task_id": "some_task", "status": "created"})
        ])

        body = {
            "query": mock_get_query.return_value,
            "script": mock_get_script.return_value,
        }
        melastic.update_by_query.assert_called_once_with(
            index="netmet_data_v2*", body=body, conflicts="proceed",
            wait_for_completion=False, requests_per_second=1000)
        mock_get_query.assert_called_once_with(mock_event_get.return_value[1],
                                               "some_id", "add")
        mock_get_script.assert_called_once_with("some_id", "add")

    @mock.patch("netmet.server.db.DB._event_upgrade_metrics")
    @mock.patch("netmet.server.db.elasticsearch.Elasticsearch")
    def test_event_create(self, mock_elastic, mock_event_upgrade_metrics):
        db.DB.create("a", ["b"])
        data = {"some_data": 1}

        mock_elastic.return_value.create.return_value = {"created": True}

        self.assertTrue(db.get().event_create("some_id", data))

        mock_elastic.return_value.create.assert_called_once_with(
            index="netmet_events", doc_type="events", id="some_id",
            body={"some_data": 1, "status": "created"}, refresh="true")

        mock_event_upgrade_metrics.assert_called_once_with("some_id", "add")

    @mock.patch("netmet.server.db.DB.event_get")
    @mock.patch("netmet.server.db.DB._event_update")
    def test_event_stop(self, mock_event_update, mock_event_get):
        mock_event_get.return_value = (2, {})
        db.DB().event_stop("22")
        mock_event_get.assert_called_once_with("22")
        mock_event_update.assert_called_once_with(
            "22", {"finished_at": mock.ANY}, 2)

    @mock.patch("netmet.server.db.DB.event_get")
    def test_event_stop_conflict(self, mock_event_get):
        mock_event_get.return_value = (1, {"finished_at": "some_value"})
        self.assertRaises(exceptions.DBConflict,
                          db.DB().event_stop, "42")
        mock_event_get.assert_called_once_with("42")

    @mock.patch("netmet.server.db.DB._event_upgrade_metrics")
    @mock.patch("netmet.server.db.DB._event_update")
    def test_event_delete(self, mock_event_update, mock_event_upgrade_metrics):
        db.DB().event_delete("22")
        mock_event_update.assert_called_once_with("22", {"status": "deleted"})
        mock_event_upgrade_metrics.assert_called_once_with("22", "remove")
