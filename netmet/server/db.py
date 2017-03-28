# Copyright 2017: GoDaddy Inc.

import copy
import datetime
import json
import logging
import threading

import elasticsearch

from netmet import exceptions


LOG = logging.getLogger(__name__)

# Use streaming API instead of this
# Elastic doesn't allow to query more than 10k elements (for the reason)
MAX_AMOUNT_OF_SERVERS = 10000


_DB = None
_INIT_LOCK = threading.Lock()


def get():
    if not _DB:
        raise exceptions.DBNotInitialized()
    return _DB


def init(own_url, elastic):
    global _DB
    with _INIT_LOCK:
        if not _DB:
            _DB = DB(own_url, elastic)


def is_inited(elastic):
    return bool(_DB)


class DB(object):

    _CLIENT_PROPS = {
        "host": {"type": "keyword"},
        "ip": {"type": "ip"},
        "port": {"type": "integer"},
        "mac": {"type": "keyword"},
        "az": {"type": "keyword"},
        "dc": {"type": "keyword"}
    }

    _CLIENT_CONF_PROPS = copy.deepcopy(_CLIENT_PROPS)
    _CLIENT_CONF_PROPS.update({
        "configured": {"type": "boolean"}
    })

    _LATENCY_TYPE = {
        "type": "nested",
        "properties": {
            "min": {"type": "float"},
            "max": {"type": "float"},
            "avg": {"type": "float"}
        }
    }

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
                "properties": _CLIENT_CONF_PROPS
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
                    "client": {"type": "nested", "properties": _CLIENT_PROPS},
                    "dest": {"type": "keyword"},
                    "protocol": {"type": "text"},
                    "timestamp": {"type": "date"},
                    "transmitted": {"type": "integer"},
                    "packet_size": {"type": "integer"},
                    "lost": {"type": "integer"},
                    "latency": _LATENCY_TYPE,
                    "ret_code": {"type": "integer"}
                }
            },
            "east-west": {
                "dynamic": "strict",
                "properties": {
                    "protocol": {"type": "text"},
                    "client_src": {
                        "type": "nested",
                        "properties": _CLIENT_PROPS
                    },
                    "client_dest": {
                        "type": "nested",
                        "properties": _CLIENT_PROPS
                    },
                    "timestamp": {"type": "date"},
                    "packet_size": {"type": "integer"},
                    "transmitted": {"type": "integer"},
                    "lost": {"type": "integer"},
                    "latency": _LATENCY_TYPE,
                    "ret_code": {"type": "integer"}
                }
            }
        }
    }

    def __init__(self, own_url, elastic):
        self.own_url = own_url
        self.elastic_urls = elastic
        self.elastic = elasticsearch.Elasticsearch(elastic)
        self._ensure_elastic()
        self._ensure_schema()

    def _ensure_elastic(self):
        self.elastic.info()

    def _ensure_schema(self):
        """Ensures that indexes exist & have right schemas.

            If there is no index this method creates it.
            If there is index but it has different schema process is shutdown
        """
        indexes = {"netmet_catalog": DB._CATALOG, "netmet_data": DB._DATA}

        try:
            for idx, schema in indexes.iteritems():
                if not self.elastic.indices.exists(idx):
                    self.elastic.indices.create(index=idx, body=schema)
        except elasticsearch.exceptions.ElasticsearchException as e:
            if not all(self.elastic.indices.exists(i) for i in indexes):
                LOG.info("Creatation of index failed: %s" % e)
                raise exceptions.DBInitFailure(elastic=self.elastic, message=e)
            # TODO(boris-42): Check whatever shcema is the same.

    def clients_get(self):
        data = self.elastic.search(index="netmet_catalog", doc_type="clients",
                                   size=MAX_AMOUNT_OF_SERVERS)

        return [x["_source"] for x in data["hits"]["hits"]]

    def clients_set(self, catalog):
        bulk_body = []
        for c in catalog:
            bulk_body.append(json.dumps({"index": {}}))
            bulk_body.append(json.dumps(c))

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
            bulk_body.append(json.dumps(d))

        # NOTE(boris-42): We should analyze Elastic response here.
        self.elastic.bulk(index="netmet_data", doc_type=doc_type,
                          body="\n".join(bulk_body))

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
