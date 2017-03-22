# Copyright 2017: GoDaddy Inc.

import threading

import flask
from flask_helpers import routing

from netmet.client import collector
from netmet.utils import status


app = flask.Flask(__name__, static_folder=None)
_lock = threading.Lock()
_collector = None
_config = None


@app.errorhandler(404)
def not_found(error):
    """404 Page in case of failures."""
    return flask.jsonify({"error": "Not Found"}), 404


@app.route("/api/v1/status", methods=['GET'])
def get_status():
    """Return uptime of API service."""
    # Return status of service
    return flask.jsonify(status.status()), 200


@app.route("/api/v1/config", methods=['GET'])
def get_config():
    """Returns netmet config."""
    global _config

    if _config:
        return flask.jsonify({"config": _config}), 200
    else:
        return flask.jsonify({"error": "Netmet is not configured"}), 404


@app.route("/api/v1/config", methods=['POST'])
def set_config():
    """Recreates collector instance providing list of new hosts."""
    global _lock, _collector, _config

    data = flask.request.get_json(silent=False, force=True)

    # jsonshceme validation here

    with _lock:
        if _collector:
            _collector.stop()

        _config = data
        _collector = collector.Collector(**data)
        _collector.start()

    return flask.jsonify({"message": "Succesfully update netmet config"}), 201


@app.route("/api/v1/unregister", methods=['POST'])
def unregister():
    """Stops collector system."""
    global _lock, _collector, _config

    with _lock:
        if _collector:
            _collector.stop()
            _collector = None
            _config = None

    return flask.jsonify({"message": "Netmet clinet is unregistered."}), 201


app = routing.add_routing_map(app, html_uri=None, json_uri="/")


@app.after_request
def add_request_stats(response):
    status.count_requests(response.status_code)
    return response


def main():
    app.run(host=app.config.get("HOST", "0.0.0.0"),
            port=app.config.get("PORT", 5000))


if __name__ == "__main__":
    main()
