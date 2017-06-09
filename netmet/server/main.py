# Copyright 2017: GoDaddy Inc.

import functools
import json
import logging
import os

import elasticsearch
import flask
from flask_helpers import routing
import jsonschema

from netmet import exceptions
from netmet.server import db
from netmet.server import deployer
from netmet.server import mesher
from netmet.utils import status


LOG = logging.getLogger(__name__)
app = flask.Flask(__name__, static_folder=None)
app.wsgi_app = status.StatusMiddleware(app)


@app.errorhandler(404)
def not_found(error):
    return flask.jsonify({"error": "Not Found"}), 404


@app.errorhandler(500)
def internal_server_error(error):
    """500 Handle Internal Errors."""
    return flask.jsonify({"error": "Internal Server Error"}), 500


def db_errors_handler(f):

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except exceptions.DBRecordNotFound as e:
            return flask.jsonify({"error": str(e)}), 404
        except (exceptions.DBConflict,
                elasticsearch.exceptions.ConflictError) as e:
            return flask.jsonify({"error": str(e)}), 409

    return wrapper


@app.route("/api/v1/config", methods=["GET"])
@db_errors_handler
def config_get():
    """Returns netmet server configuration."""
    config = db.get().server_config_get()

    if not config:
        return flask.jsonify({
            "message": "Netmet server has not been setup yet"}), 404

    return flask.jsonify(config), 200


@app.route("/api/v2/config", methods=["POST"])
@db_errors_handler
def config_set():
    """Sets netmet server configuration."""

    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "deployment": {
                "type": "object",
                "properties": {
                    "static": {
                        "type": "object",
                        "properties": {
                            "clients": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "host": {"type": "string"},
                                        "ip": {"type": "string"},
                                        "port": {"type": "integer"},
                                        "az": {"type": "string"},
                                        "dc": {"type": "string"},
                                        "hypervisor": {"type": "string"}
                                    },
                                    "required": ["host", "ip", "az", "dc"],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": ["clients"],
                        "additionalProperties": False
                    }
                },
                "required": ["static"],
                "additionalProperties": False
            },
            "mesher": mesher.Mesher.get_jsonschema(),
            "external": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dest": {"type": "string"},
                        "protocol": {"enum": ["http", "icmp"]},
                        "period": {"type": "number"},
                        "timeout": {"type": "number"}
                    },
                    "required": ["dest", "protocol", "period", "timeout"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["deployment", "mesher"],
        "additionalProperties": False
    }
    try:
        config = flask.request.get_json(silent=False, force=True)
        jsonschema.validate(config, CONFIG_SCHEMA)
    except (ValueError, jsonschema.exceptions.ValidationError) as e:
        return flask.jsonify({"error": "Bad request: %s" % e}), 400

    db.get().server_config_add(config)
    deployer.Deployer.force_update()
    return flask.jsonify({"message": "Config was updated"}), 201


@app.route("/api/v1/clients", methods=["GET"])
@db_errors_handler
def clients_list():
    """List all hosts."""
    return flask.jsonify(db.get().clients_get()), 200


@app.route("/api/v1/clients/<host>/<port>", methods=["POST"])
@db_errors_handler
def client_refresh(host, port):
    result = mesher.Mesher.get().refresh_client(host, int(port))
    key = "message" if result[0] else "error"
    return flask.jsonify({key: result[2]}), result[1]


@app.route("/api/v1/metrics", methods=["POST", "PUT"])
@db_errors_handler
def metrics_add():
    """Stores metrics to elastic."""

    # Check just basic schema, let elastic check everything else
    schema = {
        "type": "array",
        "items": {"type": "object"}
    }

    try:
        req_data = flask.request.get_json(silent=False, force=True)
        jsonschema.validate(req_data, schema)
    except (ValueError, jsonschema.exceptions.ValidationError) as e:
        return flask.jsonify({"error": "Bad request: %s" % e}), 400
    else:
        data = {"north-south": [], "east-west": []}
        for d in req_data:
            for key in data:
                if key in d:
                    data[key].append(d[key])
                    break
            else:
                LOG.warning("Ignoring wrong object %s" % json.dumps(d))

        # TODO(boris-42): Use pusher here, to reduce amount of quires
        # from netmet server to elastic, join data from different netmet
        # clients requests before pushing them to elastic
        for k, v in data.iteritems():
            if v:
                db.get().metrics_add(k, v)

    return flask.jsonify({"message": "successfully stored metrics"}), 201


@app.route("/api/v1/metrics/<period>", methods=["GET"])
@db_errors_handler
def metrics_get(period):
    """Get metrics for period."""
    return flask.jsonify({"message": "noop"}), 200


@app.route("/api/v1/events", methods=["GET"])
@db_errors_handler
def events_list():
    offset = flask.request.args.get('offset', 0)
    limit = flask.request.args.get('limit', 100)
    active_only = flask.request.args.get('active_only')
    return flask.jsonify(db.get().events_list(offset, limit, active_only)), 200


@app.route("/api/v1/events/<event_id>", methods=["GET"])
@db_errors_handler
def event_get(event_id):
    return flask.jsonify(db.event_get(event_id)[1]), 200


@app.route("/api/v1/events/<event_id>", methods=["POST"])
@db_errors_handler
def event_create(event_id):
    """If event already exists it recreates it."""
    schema = {
        "type": "object",

        "definitions": {
            "traffic": {
                "type": "object",
                "properties": {
                    "type": {"enum": ["host", "az", "dc"]},
                    "value": {"type": "string"}
                },
                "required": ["type", "value"]
            }
        },
        "properties": {
            "name": {"type": "string"},
            "started_at": {"type": "string"},
            "finished_at": {"type": "string"},
            "traffic_from": {"$ref": "#/definitions/traffic"},
            "traffic_to": {"$ref": "#/definitions/traffic"}
        },
        "required": ["started_at", "name"],
        "additionalProperties": False
    }
    try:
        data = flask.request.get_json(silent=False, force=True)
        jsonschema.validate(data, schema)

    except (ValueError, jsonschema.exceptions.ValidationError) as e:
        return flask.jsonify({"error": "Bad request: %s" % e}), 400

    db.get().event_create(event_id, data)
    return flask.jsonify({"message": "Event created %s" % event_id}), 201


@app.route("/api/v1/events/<event_id>/_stop", methods=["POST"])
@db_errors_handler
def event_stop(event_id):
    db.get().event_stop(event_id)
    return flask.jsonify({"message": "event %s stopped" % event_id}), 200


@app.route("/api/v1/events/<event_id>", methods=["DELETE"])
@db_errors_handler
def event_delete(event_id):
    db.get().event_delete(event_id)
    return flask.jsonify({"message": "event %s deleted" % event_id}), 202


app = routing.add_routing_map(app, html_uri=None, json_uri="/")


def die():
    deployer.Deployer.destroy()
    mesher.Mesher.destroy()
    db.DB.destroy()


def load(port):
    NETMET_SERVER = os.getenv("NETMET_SERVER_URL")
    if not NETMET_SERVER:
        raise ValueError("Set NETMET_SERVER_URL to NetMet server public "
                         "load balanced address")

    NETMET_OWN_URL = os.getenv("NETMET_OWN_URL")
    if not NETMET_OWN_URL:
        raise ValueError("Set NETMET_OWN_URL to NetMet server address")

    ELASTIC = os.getenv("ELASTIC", "")
    if not ELASTIC:
        raise ValueError("Set ELASTIC to list of urls of instances of cluster,"
                         " separated by comma.")

    db.DB.create(NETMET_OWN_URL, ELASTIC.split(","))
    deployer.Deployer.create(mesher.Mesher.force_update)
    mesher.Mesher.create(NETMET_SERVER)

    return app
