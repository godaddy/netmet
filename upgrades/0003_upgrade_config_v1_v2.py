# Copyright 2017: GoDaddy Inc.

import json
import sys

import elasticsearch
import elasticsearch.helpers


def upgrade(elastic, dry_run=False):
    elastic = elasticsearch.Elasticsearch(elastic)
    print(json.dumps(elastic.info(), indent=2))

    if dry_run:
        print("Exit from dry mode")
        return

    body = []
    for hit in elasticsearch.helpers.scan(elastic,
                                          index="netmet_catalog",
                                          doc_type="config"):

        config = json.loads(hit["_source"]["config"])
        if "static" in config:
            print("Updating record %s" % hit["_id"])
            new_config = json.dumps({
                "deployment": config,
                "mesher": {"full_mesh": {}},
                "external": []
            })

            body.append(json.dumps({"update": {"_id": hit["_id"]}}))
            body.append(json.dumps({"doc": {"config": new_config}}))

    if body:
        elastic.bulk(index="netmet_catalog", doc_type="config",
                     body="\n".join(body))
        print("Upgrade finished. %s records changed" % len(body) / 2)
    else:
        print("Everything is up to date.")


def main():
    if (len(sys.argv) == 1
       or len(sys.argv) > 3
       or len(sys.argv) == 3 and sys.argv[2] != "--check"):
        print("Invalid input. Usage:")
        print("python 0003_upgrade_config_v1_v2.py <elastic_url> [--check]")
        return 1
    else:
        upgrade(sys.argv[1], dry_run=len(sys.argv) == 3)


if __name__ == "__main__":
    main()
