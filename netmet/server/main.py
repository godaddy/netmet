# Copyright 2017: GoDaddy Inc.

import logging
import os

import flask
from flask_helpers import routing
import jsonschema

from netmet import db
from netmet.server import deployer
from netmet.server import mesher
from netmet.utils import status


app = flask.Flask(__name__, static_folder=None)


@app.errorhandler(404)
def not_found(error):
    return flask.jsonify({"error": "Not Found"}), 404


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
    config = flask.request.get_json(silent=False, force=True)

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
        jsonschema.validate(config, CONFIG_SCHEMA)
    except (ValueError, jsonschema.exceptions.ValidationError) as e:
        return flask.jsonify({"error": "Bad request: %s" % e}), 400

    db.get().server_config_add(config)
    return flask.jsonify({"message": "Config was updated"}), 201


@app.route("/api/v1/clients", methods=["GET"])
def clients_list():
    """List all hosts."""
    return flask.jsonify(db.get().clients_get()), 200


@app.route("/api/v1/metrics", methods=["PUT"])
def metrics_add():
    """Stores metrics to elastic."""
    # data = flask.request.get_json(silent=False, force=True)

    return flask.jsonify({"message": "noop"}), 200


@app.route("/api/v1/metrics/<period>", methods=["GET"])
def metrics_get(period):
    """Get metrics for period."""
    return flask.jsonify({"message": "noop"}), 200


app = routing.add_routing_map(app, html_uri=None, json_uri="/")


def main():
    logging.basicConfig(level=logging.INFO)
    HOST = app.config.get("HOST", "0.0.0.0")
    PORT = app.config.get("PORT", 5005)

    db.init(os.getenv("elastic_urls").split(","))
    deployer.Deployer().create()
    mesher.Mesher().create("%s:%s" % (HOST, PORT))

    app.run(host=HOST, port=PORT)


if __name__ == "__main__":
    main()
