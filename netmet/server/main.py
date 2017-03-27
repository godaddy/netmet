# Copyright 2017: GoDaddy Inc.

import json
import logging
import os

import flask
from flask_helpers import routing
import jsonschema

from netmet.server import db
from netmet.server import deployer
from netmet.server import mesher
from netmet.utils import status


LOG = logging.getLogger(__name__)
app = flask.Flask(__name__, static_folder=None)


@app.errorhandler(404)
def not_found(error):
    return flask.jsonify({"error": "Not Found"}), 404


@app.errorhandler(500)
def internal_server_error(error):
    """500 Handle Internal Errors."""
    return flask.jsonify({"error": "Internal Server Error"}), 500


@app.route("/api/v1/status", methods=["GET"])
def get_status():
    """Returns status of servers."""
    return flask.jsonify(status.status()), 200


@app.route("/api/v1/config", methods=["GET"])
def config_get():
    """Returns netmet server configuration."""
    config = db.get().server_config_get()

    if not config:
        return flask.jsonify({
            "message": "Netmet server has not been setup yet"}), 404

    return flask.jsonify(config), 200


@app.route("/api/v1/config", methods=["POST"])
def config_set():
    """Sets netmet server configuration."""

    CONFIG_SCHEMA = {
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
                                "mac": {"type": "string"},
                                "az": {"type": "string"},
                                "dc": {"type": "string"}
                            },
                            "required": ["host", "ip", "az", "dc"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["clients"],
                "additionalProperties": False,
            }
        },
        "required": ["static"],
        "additionalProperties": False
    }
    try:
        config = flask.request.get_json(silent=False, force=True)
        jsonschema.validate(config, CONFIG_SCHEMA)
    except (ValueError, jsonschema.exceptions.ValidationError) as e:
        return flask.jsonify({"error": "Bad request: %s" % e}), 400

    db.get().server_config_add(config)
    deployer.Deployer.force_update()
    mesher.Mesher.force_update()
    return flask.jsonify({"message": "Config was updated"}), 201


@app.route("/api/v1/clients", methods=["GET"])
def clients_list():
    """List all hosts."""
    return flask.jsonify(db.get().clients_get()), 200


@app.route("/api/v1/metrics", methods=["POST", "PUT"])
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
        data = {"south-north": [], "east-west": []}
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
def metrics_get(period):
    """Get metrics for period."""
    return flask.jsonify({"message": "noop"}), 200


app = routing.add_routing_map(app, html_uri=None, json_uri="/")


@app.after_request
def add_request_stats(response):
    status.count_requests(response.status_code)
    return response


def load():
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

    db.init(NETMET_OWN_URL, ELASTIC.split(","))
    deployer.Deployer.create()
    mesher.Mesher.create(NETMET_SERVER)

    return app


if __name__ == "__main__":
    load()
    app.run(host="0.0.0.0", port=5005)
