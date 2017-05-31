# Copyright 2017: GoDaddy Inc.

import copy
import datetime
import json
import logging

import elasticsearch
import morph

from netmet import exceptions
from netmet.utils import worker


LOG = logging.getLogger(__name__)

# Use streaming API instead of this
# Elastic doesn't allow to query more than 10k elements (for the reason)
MAX_AMOUNT_OF_SERVERS = 10000


def get():
    return DB.get()


class DB(worker.LonelyWorker):
    _period = 600   # every 10 minutes check needs to rollover index

    _CATALOG_IDX = "netmet_catalog"
    _DATA_ALIAS = "netmet_data_v2"
    _DATA_IDX = "<%s-{now/d}-000001>" % _DATA_ALIAS
    _EVENTS_IDX = "netmet_events"

    _CATALOG = {
        "settings": {
            "index": {
                "number_of_shards": 3,
                "number_of_replicas": 3
            }
        },
        "mappings": {
            "clients": {
                "dynamic": "strict",
                "properties": {
                    "host": {"type": "keyword"},
                    "ip": {"type": "ip"},
                    "port": {"type": "integer"},
                    "mac": {"type": "keyword"},
                    "hypervisor": {"type": "keyword"},
                    "az": {"type": "keyword"},
                    "dc": {"type": "keyword"},
                    "configured": {"type": "boolean"}
                }
            },
            "config": {
                "dynamic": "strict",
                "properties": {
                    "timestamp": {"type": "date"},
                    "config": {"type": "text"},
                    "applied": {"type": "boolean"},
                    "meshed": {"type": "boolean"}
                }
            }
        }
    }

    _DATA = {
        "settings": {
            "index": {
                "number_of_shards": 10,
                "number_of_replicas": 1
            }
        },
        "mappings": {
            "north-south": {
                "dynamic": "strict",
                "properties": {
                    "client_src.host": {"type": "keyword"},
                    "client_src.ip": {"type": "ip"},
                    "client_src.port": {"type": "integer"},
                    "client_src.hypervisor": {"type": "keyword"},
                    "client_src.az": {"type": "keyword"},
                    "client_src.dc": {"type": "keyword"},
                    "dest": {"type": "keyword"},
                    "protocol": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "transmitted": {"type": "integer"},
                    "packet_size": {"type": "integer"},
                    "lost": {"type": "integer"},
                    "latency": {"type": "float"},
                    "ret_code": {"type": "integer"},
                    "events": {"type": "keyword"}
                }
            },
            "east-west": {
                "dynamic": "strict",
                "properties": {
                    "protocol": {"type": "keyword"},
                    "client_src.host": {"type": "keyword"},
                    "client_src.ip": {"type": "ip"},
                    "client_src.port": {"type": "integer"},
                    "client_src.hypervisor": {"type": "keyword"},
                    "client_src.az": {"type": "keyword"},
                    "client_src.dc": {"type": "keyword"},
                    "client_dest.host": {"type": "keyword"},
                    "client_dest.ip": {"type": "ip"},
                    "client_dest.port": {"type": "integer"},
                    "client_dest.hypervisor": {"type": "keyword"},
                    "client_dest.az": {"type": "keyword"},
                    "client_dest.dc": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "packet_size": {"type": "integer"},
                    "transmitted": {"type": "integer"},
                    "lost": {"type": "integer"},
                    "latency": {"type": "float"},
                    "ret_code": {"type": "integer"},
                    "events": {"type": "keyword"}
                }
            }
        }
    }

    _EVENTS = {
        "settings": {
            "index": {
                "number_of_shards": 3,
                "number_of_replicas": 3
            },
        },
        "mappings": {
            "events": {
                "dynamic": "strict",
                "properties": {
                    "name": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "started_at": {"type": "date"},
                    "finished_at": {"type": "date"},
                    "task_id": {"type": "keyword"},
                    "traffic_from.type": {"type": "keyword"},
                    "traffic_from.value": {"type": "keyword"},
                    "traffic_to.type": {"type": "keyword"},
                    "traffic_to.value": {"type": "keyword"}
                }
            }
        }
    }

    @classmethod
    def create(cls, own_url, elastic):
        super(DB, cls).create()
        cls._self.own_url = own_url
        cls._self.elastic_urls = elastic
        cls._self.elastic = elasticsearch.Elasticsearch(elastic)
        cls._self._ensure_elastic()
        cls._self._ensure_schema()
        cls._self._rollover_data()
        cls._self._initied = True

    def _job(self):
        try:
            if getattr(self, "_initied", False):
                self._rollover_data()
        except Exception:
            LOG.exception("DB update failed")

    def _rollover_data(self):
        body = {"conditions": {"max_age": "1d", "max_docs": 10000000}}
        body.update(self._DATA)
        self.elastic.indices.rollover(alias=DB._DATA_ALIAS, body=body)

    def _ensure_elastic(self):
        self.elastic.info()

    def _ensure_schema(self):
        """Ensures that indexes exist & have right schemas.

            If there is no index this method creates it.
            If there is index but it has different schema process is shutdown
        """
        data = [(self._CATALOG_IDX, self._CATALOG),
                (self._EVENTS_IDX, self._EVENTS)]

        for idx, mapping in data:
            try:
                if not self.elastic.indices.exists(idx):
                    self.elastic.indices.create(index=idx, body=mapping)
            except elasticsearch.exceptions.ElasticsearchException as e:
                if not self.elastic.indices.exists(idx):
                    raise exceptions.DBInitFailure(
                        elastic=self.elastic, message=e)

        try:
            if not self.elastic.indices.exists_alias(name=DB._DATA_ALIAS):
                new_data = copy.deepcopy(self._DATA)
                new_data["aliases"] = {DB._DATA_ALIAS: {}}
                self.elastic.indices.create(index=self._DATA_IDX,
                                            body=new_data)
        except elasticsearch.exceptions.ElasticsearchException as e:
            if not self.elastic.indices.exists_alias(name=DB._DATA_ALIAS):
                raise exceptions.DBInitFailure(elastic=self.elastic, message=e)

    def clients_get(self):
        data = self.elastic.search(index=DB._CATALOG_IDX, doc_type="clients",
                                   size=MAX_AMOUNT_OF_SERVERS)

        return [morph.unflatten(x["_source"]) for x in data["hits"]["hits"]]

    def clients_set(self, catalog):
        bulk_body = []
        for c in catalog:
            bulk_body.append(json.dumps({"index": {}}))
            bulk_body.append(json.dumps(morph.flatten(c)))

        self.elastic.delete_by_query(index=DB._CATALOG_IDX,
                                     doc_type="clients",
                                     body={"query": {"match_all": {}}})

        self.elastic.bulk(index=DB._CATALOG_IDX, doc_type="clients",
                          body="\n".join(bulk_body),
                          refresh="true")

    def server_config_get(self, only_applied=False):
        query = {
            "sort": {"timestamp": {"order": "desc"}}
        }
        if only_applied:
            query["query"] = {"term": {"applied": True}}
        result = self.elastic.search(index=DB._CATALOG_IDX, doc_type="config",
                                     body=query, size=1)

        hits = result["hits"]["hits"]
        if not hits:
            return

        result = hits[0]["_source"]
        result["config"] = json.loads(result["config"])
        result["id"] = hits[0]["_id"]
        return result

    def server_config_add(self, config):
        """Adds new server config."""
        body = {
            "config": json.dumps(config),
            "applied": False,
            "meshed": False,
            "timestamp": datetime.datetime.now().isoformat()
        }
        self.elastic.index(index=DB._CATALOG_IDX,
                           doc_type="config", body=body,
                           refresh="true")

    def server_config_apply(self, id_):
        self.elastic.update(index=DB._CATALOG_IDX,
                            doc_type="config", id=id_,
                            body={"doc": {"applied": True}},
                            refresh="true")

    def server_config_meshed(self, id_):
        self.elastic.update(index=DB._CATALOG_IDX,
                            doc_type="config", id=id_,
                            body={"doc": {"meshed": True}},
                            refresh="true")

    def metrics_add(self, doc_type, data):
        if doc_type not in ["east-west", "north-south"]:
            raise ValueError("Wrong doc type")

        bulk_body = []
        for d in data:
            bulk_body.append(json.dumps({"index": {}}))
            bulk_body.append(json.dumps(morph.flatten(d)))

        # NOTE(boris-42): We should analyze Elastic response here.
        r = self.elastic.bulk(index=DB._DATA_ALIAS, doc_type=doc_type,
                              body="\n".join(bulk_body))

        results = {}
        for it in r["items"]:
            k = it["index"]["status"]
            results.setdefault(k, 0)
            results[k] += 1

        LOG.info("Metrics bulk insert result: %s" % results)
        return results

    def event_get(self, id_):
        r = self.elastic.get(index=DB._EVENTS_IDX, doc_type="events", id=id_)
        if not r["found"]:
            raise exceptions.DBRecordNotFound(record=id_)
        return r["_version"], r["_source"]

    def events_list(self, offset, limit, only_active=False):
        query = {
            "from": offset,
            "size": limit,
            "query": {
                "bool": {
                    "must_not": [{"term": {"status": "deleted"}}]
                }
            }
        }
        if only_active:
            query["query"]["filter"] = [
                {"range": {"started_at": {"lte": "now/m"}}}]

            query["query"]["bool"]["should"] = [
                {"range": {"finished_at": {"gt": "now/m"}}},
                {"missing": {"field": "finished_at"}}
            ]

        results = self.elastic.search(index=DB._EVENTS_IDX, body=query)
        return [r["_source"] for r in results["hits"]["hits"]]

    def _event_update(self, id_, doc, version=None):
        v, el = self.event_get(id_)

        version = v if version is None else version
        if v != version:
            raise exceptions.DBConflict(
                "Record %s was updated by another concurrent request" % id_)

        body = {"doc": doc}
        r = self.elastic.update(index=DB._EVENTS_IDX, doc_type="events",
                                id=id_, version=version,
                                body=body, refresh="true")

        if not r["result"] == "updated":
            raise exceptions.DBConflict(
                "Record %s was update by other concurrent request." % id_)

        return True

    def _get_query(self, event, id_, action):
        query = {"must": [], "must_not": [], "filter": []}

        if event["started_at"] or event["finished_at"]:
            q = {"timestamp": {}}
            if event["started_at"]:
                q["timestamp"]["gte"] = event["started_at"]
            if event["finished_at"]:
                q["timestamp"]["lte"] = event["finished_at"]
            query["filter"].append({"range": q})

        if event.get("traffic_to.type"):
            term = "client_dest.%s" % event["traffic_to.type"]
            query["filter"].append({"term": {term: event["traffic_to.value"]}})

        if event.get("traffic_from.type"):
            term = "client_src.%s" % event["traffic_from.type"]
            query["filter"].append(
                {"term": {term: event["traffic_from.value"]}})

        if action == "remove":
            query["must"].append({"term": {"events": id_}})
        elif action == "add":
            query["must_not"].append({"term": {"events": id_}})

        return {"bool": query}

    def _get_script(self, id_, action):
        if action == "add":
            return {
                "inline": "ctx._source.events.add('%s')" % id_,
                "lang": "painless"
            }

        elif action == "remove":
            return {
                "inline": "ctx._source.events.remove"
                          "(ctx._source.events.indexOf('%s'))" % id_,
                "lang": "painless"
            }

    def _event_upgrade_metrics(self, id_, action):
        version, event = self.event_get(id_)

        if event.get("task_id"):
            t = self.elastic.tasks.get(task_id=event["task_id"])
            if not t.get("completed", False):
                raise exceptions.DBConflict(
                    "Task %s is still running" % event["task_id"])

            self._event_update(
                id_, {"task_id": None, "status": "updating"}, version=version)
        else:
            self._event_update(id_, {"status": "updating"}, version=version)

        body = {
            "query": self._get_query(event, id_, action),
            "script": self._get_script(id_, action)
        }

        result = self.elastic.update_by_query(
            index=DB._DATA_ALIAS + "*", body=body, conflicts="proceed",
            wait_for_completion=False, requests_per_second=1000)

        self._event_update(id_,
                           {"task_id": result["task"], "status": "created"})

    def event_create(self, id_, data):
        data = dict(data)
        data["status"] = "created"
        r = self.elastic.create(index=DB._EVENTS_IDX, doc_type="events",
                                id=id_, body=data, refresh="true")
        if r["created"]:
            self._event_upgrade_metrics(id_, "add")
            return True

    def event_stop(self, id_):
        version, event = self.event_get(id_)

        if event.get("finished_at", None):
            raise exceptions.DBConflict("Event is already stopped.")

        return self._event_update(
            id_, {"finished_at": datetime.datetime.now().isoformat()}, version)

    def event_delete(self, id_):
        self._event_upgrade_metrics(id_, "remove")
        return self._event_update(id_, {"status": "deleted"})

    def lock_accuire(self, name, ttl):
        # release old one if ttl hit
        data = {
            "updated_at": datetime.datetime.now().isoformat(),
            "url": self.own_url,
            "ttl": ttl
        }
        try:
            # TODO(boris-42): Check whatever we can delete obsolate lock
            idx = "netmet_lock_%s" % name
            self.elastic.indices.create(idx, body={})
            self.elastic.index(index=idx, doc_type="lock", id=1, body=data)
            return True
        except elasticsearch.exceptions.ElasticsearchException:
            return False

    def lock_release(self, name):
        try:
            # TODO(boris-42): Try few times to delete lock
            self.elastic.indices.delete("netmet_lock_%s" % name)
            return True
        except elasticsearch.exceptions.ElasticsearchException:
            return False
