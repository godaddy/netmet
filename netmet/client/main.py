# Copyright 2017: GoDaddy Inc.

import threading

import flask
from flask_helpers import routing
import jsonschema

from netmet.client import collector
from netmet.client import conf
from netmet.utils import status


APP = flask.Flask(__name__, static_folder=None)
APP.wsgi_app = status.StatusMiddleware(APP)


# TOOD(boris-42): Move this to the Collector (unify with server).
_LOCK = threading.Lock()
_COLLECTOR = None
_CONFIG = None
_DEAD = False


def _destroy_collector():
    global _LOCK, _COLLECTOR, _CONFIG

    locked = False
    try:
        locked = _LOCK.acquire(False)
        if locked:
            if _COLLECTOR:
                _COLLECTOR.stop()
                _COLLECTOR = None
                _CONFIG = None
    finally:
        if locked:
            _LOCK.release()


@APP.errorhandler(404)
def not_found(error):
    """404 Page in case of failures."""
    return flask.jsonify({"error": "Not Found"}), 404


@APP.errorhandler(500)
def internal_server_error(error):
    """500 Handle Internal Errors."""
    return flask.jsonify({"error": "Internal Server Error"}), 500


@APP.route("/api/v1/config", methods=['GET'])
def get_config():
    """Returns netmet config."""
    global _CONFIG

    if _CONFIG:
        return flask.jsonify({"config": _CONFIG}), 200
    else:
        return flask.jsonify({"error": "Netmet is not configured"}), 404


@APP.route("/api/v1/config", methods=['POST'])
def set_config():
    """Recreates collector instance providing list of new hosts."""
    global _LOCK, _COLLECTOR, _CONFIG

    if _DEAD:
        flask.abort(500)

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

    # NOTE(boris-42): Transform data for new Collector
    data["client_host"].pop("mac", "")
    hosts = data.pop("hosts")
    s = {
        "timeout": data.pop("timeout"),
        "packet_size": 55,
        "period": data["period"]
    }
    data["tasks"] = []
    for host in hosts:
        host.pop("mac", "")
        data["tasks"].extend([
            {"east-west": {"dest": host, "protocol": "icmp", "settings": s}},
            {"east-west": {"dest": host, "protocol": "http", "settings": s}}
        ])

    with _LOCK:
        if _COLLECTOR:
            _COLLECTOR.stop()

        _CONFIG = data
        conf.restore_url_set(data["netmet_server"],
                             data["client_host"]["host"],
                             data["client_host"]["port"])
        _COLLECTOR = collector.Collector(**data)
        _COLLECTOR.start()

    return flask.jsonify({"message": "Succesfully update netmet config"}), 201


@APP.route("/api/v2/config", methods=['POST'])
def set_config_v2():
    global _LOCK, _COLLECTOR, _CONFIG

    if _DEAD:
        flask.abort(500)

    schema = {
        "type": "object",
        "definitions": {
            "client": {
                "type": "object",
                "properties": {
                    "host": {"type": "string"},
                    "ip": {"type": "string"},
                    "port": {"type": "integer"},
                    "hypervisor": {"type": "string"},
                    "az": {"type": "string"},
                    "dc": {"type": "string"}
                },
                "required": ["ip", "host", "az", "dc", "port"],
                "additionProperties": False
            },
            "settings": {
                "type": "object",
                "properties": {
                    "packet_size": {"type": "number", "minimum": 1},
                    "period": {"type": "number", "minimum": 0.1},
                    "timeout": {"type": "number", "minimum": 0.01}
                },
                "required": ["period", "timeout"],
                "additionProperties": False
            }
        },
        "properties": {
            "netmet_server": {"type": "string"},
            "client_host": {"$ref": "#/definitions/client"},
            "settings": {"$ref": "#/definitions/settings"},
            "tasks": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {
                                "north-south": {
                                    "type": "object",
                                    "properties": {
                                        "dest": {"type": "string"},
                                        "protocol": {"enum": ["http", "icmp"]},
                                        "settings": {
                                            "$ref": "#/definitions/settings"
                                        }
                                    },
                                    "required": ["dest", "protocol"],
                                    "additionalProperties": False
                                }
                            },
                            "required": ["north-south"],
                            "additionalProperties": False
                        },
                        {
                            "type": "object",
                            "properties": {
                                "east-west": {
                                    "type": "object",
                                    "properties": {
                                        "dest":  {
                                            "$ref": "#/definitions/client"
                                        },
                                        "protocol": {"enum": ["http", "icmp"]},
                                        "settings": {
                                            "$ref": "#/definitions/settings"
                                        }
                                    },
                                    "required": ["dest", "protocol"],
                                    "additionalProperties": False
                                }
                            },
                            "required": ["east-west"],
                            "additionalProperties": False
                        }
                    ]
                }
            }
        },
        "required": ["netmet_server", "client_host", "tasks", "settings"],
        "additionalProperties": False
    }

    try:
        data = flask.request.get_json(silent=False, force=True)
        jsonschema.validate(data, schema)
        settings = data.pop("settings")
        settings.setdefault("packet_size", 55)
        # TODO(boris-42): Make configuration of period flexible in future
        data["period"] = settings["period"]
        for task in data["tasks"]:
            if "settings" not in task:
                task[task.keys()[0]]["settings"] = settings
    except (ValueError, jsonschema.exceptions.ValidationError) as e:
        return flask.jsonify({"error": "Bad request: %s" % e}), 400

    with _LOCK:
        if _COLLECTOR:
            _COLLECTOR.stop()

        _CONFIG = data
        conf.restore_url_set(data["netmet_server"],
                             data["client_host"]["host"],
                             data["client_host"]["port"])
        _COLLECTOR = collector.Collector(**data)
        _COLLECTOR.start()

    return flask.jsonify({"message": "Succesfully update netmet config"}), 201


@APP.route("/api/v1/unregister", methods=['POST'])
def unregister():
    """Stops collector system."""
    conf.restore_url_clear(APP.port)
    _destroy_collector()
    return flask.jsonify({"message": "Netmet clinet is unregistered."}), 201


APP = routing.add_routing_map(APP, html_uri=None, json_uri="/")


def die():
    global _DEAD
    _DEAD = True
    _destroy_collector()


def load(port):
    conf.restore.async(port)

    return APP
