# Copyright 2017: GoDaddy Inc.

from __future__ import print_function

import json
import sys
import time

import elasticsearch


MAPPING = {
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


def upgrade(elastic, dry_run=False):
    elastic = elasticsearch.Elasticsearch(elastic)
    print(elastic.info())

    all_idxs = elastic.indices.get_mapping().keys()
    do_for_idx = [k for k in all_idxs if k.startswith("netmet_data-")
                  if "netmet_data_v2-%s" % k.split("-", 1)[1]
                  not in all_idxs]

    print("All indexes: %s" % all_idxs)
    print("Reindex required for: %s" % do_for_idx)

    if dry_run:
        print("Exit from dry mode")
        return

    for source_idx in do_for_idx:
        target_idx = "netmet_data_v2-%s" % source_idx.split("-", 1)[1]
        elastic.indices.create(index=target_idx, body=MAPPING)

        body = {
            "source": {"index": source_idx},
            "dest": {"index": target_idx},
            "script": {
                "inline": "ctx._source.events = []; ctx._source.remove('mac')"
            }
        }
        task_id = elastic.reindex(body=json.dumps(body),
                                  requests_per_second=5000,
                                  wait_for_completion=False)["task"]

        print("Reindexing task id %s for index: %s" % (task_id, source_idx))

        while True:
            time.sleep(2)
            t = elastic.tasks.get(task_id=task_id)
            status = t["task"]["status"]
            done, total = status["created"], status["total"]

            print("Status: %s from %s (%s%%)"
                  % (done, total, 100 * float(done) / total),
                  end="\r")
            sys.stdout.flush()

            if t.get("completed", False):
                print()
                break

        print("Done")


def main():
    if (len(sys.argv) == 1
       or len(sys.argv) > 3
       or len(sys.argv) == 3 and sys.argv[2] != "--check"):
        print("Invalid input. Usage:")
        print("python upgrade_v1_v2.py <elastic_url> [--check]")
        return 1
    else:
        upgrade(sys.argv[1], dry_run=len(sys.argv) == 3)


if __name__ == "__main__":
    main()
