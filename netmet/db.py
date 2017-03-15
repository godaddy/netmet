# Copyright 2017: GoDaddy Inc.

import datetime
import json
import logging
import threading

import elasticsearch

from netmet import exceptions
from netmet.utils import net


LOG = logging.getLogger(__name__)

# Use streaming API instead of this
# Elastic doesn't allow to query more than 10k elements (for the reason)
MAX_AMOUNT_OF_SERVERS = 10000


_DB = None
_INIT_LOCK = threading.Lock()


def get(elastic=None):
    global _DB
    with _INIT_LOCK:
        if not _DB:
            if not elastic:
                raise exceptions.DBNotInitialized()

            _DB = DB(elastic)
    return _DB


def is_inited(elastic):
    return bool(_DB)


class DB(object):

    _CATALOG = {
        "settings": {
            "index": {
                "number_of_shards": 3,
                "number_of_replicas": 3
            }
        },
        "mappings": {
            "clients": {
                "properties": {
                    "host": {
                        "type": "keyword"
                    },
                    "mac": {
                        "type": "keyword"
                    },
                    "private_ip": {
                        "type": "ip"
                    },
                    "az": {
                        "type": "keyword"
                    },
                    "dc": {
                        "type": "keyword"
                    },
                    "registered_at": {
                        "type": "date"
                    },
                    "running": {
                        "type": "boolean"
                    },
                    "configured": {
                        "type": "boolean"
                    }
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
            "internet": {
                "properties": {
                    "src": {
                        "type": "nested",
                        "properties": {
                            "client_ip": {
                                "type": "text"
                            },
                            "host_mac": {
                                "type": "text"
                            },
                            "az": {
                                "type": "text"
                            },
                            "dc": {
                                "type": "text"
                            }
                        }
                    },
                    "dest_host": {
                        "type": "keyword"
                    },
                    "az": {
                        "type": "text"
                    },
                    "dc": {
                        "type": "text"
                    },
                    "protocol": {
                        "type": "text"
                    },
                    "timestamp": {
                        "type": "date"
                    },
                    "transmitted": {
                        "type": "integer"
                    },
                    "lost": {
                        "type": "integer"
                    },
                    "latency": {
                        "type": "float"
                    },
                    "ret_code": {
                        "type": "integer"
                    }
                }
            },
            "internal": {
                "properties": {
                    "protocol": {
                        "type": "text"
                    },
                    "src": {
                        "type": "nested",
                        "properties": {
                            "client_ip": {
                                "type": "text"
                            },
                            "host_mac": {
                                "type": "text"
                            },
                            "az": {
                                "type": "text"
                            },
                            "dc": {
                                "type": "text"
                            }
                        }
                    },
                    "dest": {
                        "type": "nested",
                        "properties": {
                            "cleint_ip": {
                                "type": "text"
                            },
                            "host_mac": {
                                "type": "text"
                            },
                            "az": {
                                "type": "text"
                            },
                            "dc": {
                                "type": "text"
                            }
                        }
                    },
                    "timestamp": {
                        "type": "date"
                    },
                    "transmitted": {
                        "type": "integer"
                    },
                    "latency": {
                        "type": "float"
                    },
                    "ret_code": {
                        "type": "integer"
                    }
                }
            }
        }
    }

    def __init__(self, elastic):
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

    def get_catalog(self):
        return self.elastic.search(index="netmet_catalog",
                                   doc_type="clients",
                                   size=MAX_AMOUNT_OF_SERVERS)["hits"]["hits"]

    def set_catalog(self, catalog):
        bulk_body = []
        for c in catalog:
            bulk_body.append("{}\n")
            bulk_body.append(json.dumps(c))
            bulk_body.append("\n")

        self.elastic.delete_by_query(index="netmet_catalog",
                                     doc_type="clients",
                                     body={"query": {"match_all": {}}})

        self.elastic.bulk(index="netmet_catalog", doc_type="clients",
                          body="".join(bulk_body))

    def lock_accuire(self, name, ttl):
        # release old one if ttl hit
        addr, port = self.elastic_urls[0].rsplit(":", 1)

        data = {
            "updated_at": datetime.datetime.now().isoformat(),
            "host": net.get_hostname(addr, int(port)),
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
