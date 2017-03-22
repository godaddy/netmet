# Copyright 2017: GoDaddy Inc.

import copy
import datetime
import threading


started_at = datetime.datetime.now()
stats = {
    "requests": {
        "total": 0,
        "success": 0,
        "success_rate": 1,
        "per_code": {}
    }
}

lock = threading.Lock()


def count_requests(status_code):
    with lock:
        s = stats["requests"]
        s["total"] += 1
        if status_code < 500:
            s["success"] += 1
        else:
            s["failed"] += 1
        s["success_rate"] = s["success"] / float(s["total"])
        s["per_code"].setdefault(status_code, 0)
        s["per_code"][status_code] += 1


def status():
    return {
        "stats": copy.deepcopy(stats),
        "started_at": started_at,
        "runtime":  (datetime.datetime.now() - started_at).seconds
    }