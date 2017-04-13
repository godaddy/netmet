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
    _DATA_ALIAS = "netmet_data"
    _DATA_IDX = "<%s-{now/d}-000001>" % _DATA_ALIAS

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
            "south-north": {
                "dynamic": "strict",
                "properties": {
                    "client.host": {"type": "keyword"},
                    "client.ip": {"type": "ip"},
                    "client.port": {"type": "integer"},
                    "client.mac": {"type": "keyword"},
                    "client.az": {"type": "keyword"},
                    "client.dc": {"type": "keyword"},
                    "dest": {"type": "keyword"},
                    "protocol": {"type": "text"},
                    "timestamp": {"type": "date"},
                    "transmitted": {"type": "integer"},
                    "packet_size": {"type": "integer"},
                    "lost": {"type": "integer"},
                    "latency": {"type": "float"},
                    "ret_code": {"type": "integer"}
                }
            },
            "east-west": {
                "dynamic": "strict",
                "properties": {
                    "protocol": {"type": "text"},
                    "client_src.host": {"type": "keyword"},
                    "client_src.ip": {"type": "ip"},
                    "client_src.port": {"type": "integer"},
                    "client_src.mac": {"type": "keyword"},
                    "client_src.az": {"type": "keyword"},
                    "client_src.dc": {"type": "keyword"},
                    "client_dest.host": {"type": "keyword"},
                    "client_dest.ip": {"type": "ip"},
                    "client_dest.port": {"type": "integer"},
                    "client_dest.mac": {"type": "keyword"},
                    "client_dest.az": {"type": "keyword"},
                    "client_dest.dc": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "packet_size": {"type": "integer"},
                    "transmitted": {"type": "integer"},
                    "lost": {"type": "integer"},
                    "latency": {"type": "float"},
                    "ret_code": {"type": "integer"}
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
        self.elastic.indices.rollover(alias=self._DATA_ALIAS, body=body)

    def _ensure_elastic(self):
        self.elastic.info()

    def _ensure_schema(self):
        """Ensures that indexes exist & have right schemas.

            If there is no index this method creates it.
            If there is index but it has different schema process is shutdown
        """
        try:
            if not self.elastic.indices.exists(self._CATALOG_IDX):
                self.elastic.indices.create(index=self._CATALOG_IDX,
                                            body=self._CATALOG)
        except elasticsearch.exceptions.ElasticsearchException as e:
            if not self.elastic.indices.exists(self._CATALOG_IDX):
                raise exceptions.DBInitFailure(elastic=self.elastic, message=e)

        try:
            if not self.elastic.indices.exists_alias(name=self._DATA_ALIAS):
                new_data = copy.deepcopy(self._DATA)
                new_data["aliases"] = {self._DATA_ALIAS: {}}
                self.elastic.indices.create(index=self._DATA_IDX,
                                            body=new_data)
        except elasticsearch.exceptions.ElasticsearchException as e:
            if not self.elastic.indices.exists_alias(name=self._DATA_ALIAS):
                raise exceptions.DBInitFailure(elastic=self.elastic, message=e)

    def clients_get(self):
        data = self.elastic.search(index="netmet_catalog", doc_type="clients",
                                   size=MAX_AMOUNT_OF_SERVERS)

        return [morph.unflatten(x["_source"]) for x in data["hits"]["hits"]]

    def clients_set(self, catalog):
        bulk_body = []
        for c in catalog:
            bulk_body.append(json.dumps({"index": {}}))
            bulk_body.append(json.dumps(morph.flatten(c)))

        self.elastic.delete_by_query(index="netmet_catalog",
                                     doc_type="clients",
                                     body={"query": {"match_all": {}}})

        self.elastic.bulk(index="netmet_catalog", doc_type="clients",
                          body="\n".join(bulk_body))

    def server_config_get(self, only_applied=False):
        query = {
            "sort": {"timestamp": {"order": "desc"}}
        }
        if only_applied:
            query["query"] = {"term": {"applied": True}}
        result = self.elastic.search(index="netmet_catalog", doc_type="config",
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
        self.elastic.index(index="netmet_catalog",
                           doc_type="config", body=body)

    def server_config_apply(self, id):
        self.elastic.update(index="netmet_catalog",
                            doc_type="config", id=id,
                            body={"doc": {"applied": True}})

    def server_config_meshed(self, id):
        self.elastic.update(index="netmet_catalog",
                            doc_type="config", id=id,
                            body={"doc": {"meshed": True}})

    def metrics_add(self, doc_type, data):
        if doc_type not in ["east-west", "south-north"]:
            raise ValueError("Wrong doc type")

        bulk_body = []
        for d in data:
            bulk_body.append(json.dumps({"index": {}}))
            bulk_body.append(json.dumps(morph.flatten(d)))

        # NOTE(boris-42): We should analyze Elastic response here.
        r = self.elastic.bulk(index="netmet_data", doc_type=doc_type,
                              body="\n".join(bulk_body))

        results = {}
        for it in r["items"]:
            k = it["index"]["status"]
            results.setdefault(k, 0)
            results[k] += 1

        LOG.info("Metrics bulk insert result: %s" % results)

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
