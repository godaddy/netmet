# Copyright 2017: GoDaddy Inc.

import copy
import datetime
import threading

import flask
import monotonic
from webob import dec


class Stats(object):

    def __init__(self):
        self.started_at = datetime.datetime.now()
        self.stats = {
            "requests": {
                "total": 0,
                "total_duration": 0,
                "avg_duration": 0,
                "success": 0,
                "success_rate": 1,
                "per_code": {}
            }
        }
        self.lock = threading.Lock()

    def count_request(self, status_code, duration):
        with self.lock:
            s = self.stats["requests"]
            s["total"] += 1
            s["total_duration"] += duration
            if status_code < 500:
                s["success"] += 1
            s["success_rate"] = s["success"] / float(s["total"])
            s["avg_duration"] = s["total_duration"] / float(s["total"])
            s["per_code"].setdefault(status_code, 0)
            s["per_code"][status_code] += 1

    def status(self):
        return {
            "stats": copy.deepcopy(self.stats),
            "started_at": self.started_at.isoformat(),
            "runtime":  (datetime.datetime.now() - self.started_at).seconds
        }


class StatusMiddleware(object):

    def __init__(self, flask_app):
        self.app = flask_app.wsgi_app
        self.stats = Stats()

        @flask_app.route("/status", methods=["GET"])
        def status():
            return flask.jsonify(self.stats.status()), 200

    @dec.wsgify
    def __call__(self, request):
        started_at = monotonic.monotonic()
        response = request.get_response(self.app)
        self.stats.count_request(response.status_code,
                                 monotonic.monotonic() - started_at)
        return response
