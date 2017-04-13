# Copyright 2017: GoDaddy Inc.

import threading

import flask
from flask_helpers import routing
import jsonschema

from netmet.client import collector
from netmet.utils import status


app = flask.Flask(__name__, static_folder=None)
app.wsgi_app = status.StatusMiddleware(app)


# TOOD(boris-42): Move this to the Collector (unify with server).
_lock = threading.Lock()
_collector = None
_config = None


def _destroy_collector():
    global _lock, _collector, _config

    locked = False
    try:
        locked = _lock.acquire(False)
        if locked:
            if _collector:
                _collector.stop()
                _collector = None
                _config = None
    finally:
        if locked:
            _lock.release()


@app.errorhandler(404)
def not_found(error):
    """404 Page in case of failures."""
    return flask.jsonify({"error": "Not Found"}), 404


@app.errorhandler(500)
def internal_server_error(error):
    """500 Handle Internal Errors."""
    return flask.jsonify({"error": "Internal Server Error"}), 500


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

    schema = {
        "type": "object",
        "definitions": {
            "client": {
                "type": "object",
                "properties": {
                    "host": {"type": "string"},
                    "ip": {"type": "string"},
                    "port": {"type": "integer"},
                    "mac": {"type": "string"},
                    "az": {"type": "string"},
                    "dc": {"type": "string"}
                },
                "required": ["ip", "host", "az", "dc", "port"],
                "additionProperties": False
            }
        },
        "properties": {
            "netmet_server": {"type": "string"},
            "client_host": {
                "$ref": "#/definitions/client"
            },
            "hosts": {
                "type": "array",
                "items": {"$ref": "#/definitions/client"}
            },
            "period": {"type": "number", "minimum": 0.1},
            "timeout": {"type": "number", "minimum": 0.01}
        },
        "required": ["netmet_server", "client_host", "hosts"]
    }

    try:
        data = flask.request.get_json(silent=False, force=True)
        jsonschema.validate(data, schema)
        data["period"] = data.get("period", 5)
        data["timeout"] = data.get("timeout", 1)
        if data["period"] <= data["timeout"]:
            raise ValueError("timeout should be smaller then period.")
    except (ValueError, jsonschema.exceptions.ValidationError) as e:
        return flask.jsonify({"error": "Bad request: %s" % e}), 400

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
    _destroy_collector()
    return flask.jsonify({"message": "Netmet clinet is unregistered."}), 201


app = routing.add_routing_map(app, html_uri=None, json_uri="/")


def die():
    _destroy_collector()


def load():
    return app
