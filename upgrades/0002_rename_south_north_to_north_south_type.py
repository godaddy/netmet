# Copyright 2017: GoDaddy Inc.

import sys

import elasticsearch
import requests


def upgrade(elastic_url, dry_run=False):
    elastic = elasticsearch.Elasticsearch(elastic_url)
    print(elastic.info())

    if dry_run:
        print("Exit from dry mode")
        return

    mapping = {
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
    }

    requests.delete("%s/*/south-north" % elastic_url)
    elastic.indices.put_mapping(
        index="netmet_data_v2-*", doc_type="north-south", body=mapping)


def main():
    if (len(sys.argv) == 1
       or len(sys.argv) > 3
       or len(sys.argv) == 3 and sys.argv[2] != "--check"):
        print("Invalid input. Usage:")
        print("python 0002_rename_south_north_to_north_south.py <elastic_url> "
              "[--check]")
        return 1
    else:
        upgrade(sys.argv[1], dry_run=len(sys.argv) == 3)


if __name__ == "__main__":
    main()
