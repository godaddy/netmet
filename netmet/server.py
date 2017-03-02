# Copyright 2017: GoDaddy Inc.

import flask
from flask_helpers import routing

from netmet.utils import status


app = flask.Flask(__name__, static_folder=None)


@app.errorhandler(404)
def not_found(error):
    return flask.jsonify({"error": "Not Found"}), 404


@app.route("/api/v1/status", methods=["GET"])
def get_status():
    """Returns status of servers."""
    return flask.jsonify(status.status()), 200


@app.route("/api/v1/hosts", methods=["GET"])
def hosts_list():
    """List all hosts."""
    return flask.jsonify({"hosts": []}), 200


@app.route("/api/v1//hosts/<ip>", methods=["POST"])
def hosts_remove(ip):
    """Remove host."""
    # Removes host from elastic
    # Ask client stop
    return flask.jsonify({"details": "Host was removed", "ip": ip}), 200


@app.route("/api/v1/hosts/", methods=["PUT"])
def hosts_add():
    """Add new host."""
    # flask.requests
    # Adds new Host to catalog
    return flask.jsonify({"noop": "noop"}), 200


@app.route("/api/v1/metrics", methods=["PUT"])
def metrics_add():
    """Stores metrics to elastic."""
    return flask.jsonify({"noop": "noop"}), 200


@app.route("/api/v1//metrics/<period>", methods=["GET"])
def metrics_get(period):
    """Get metrics for period."""
    return flask.jsonify({"noop": "noop"}), 200


@app.route("/api/v1//map", methods=["GET"])
def map_get():
    """Returns map of servers."""
    return flask.jsonify({"noop": "noop"}), 200


app = routing.add_routing_map(app, html_uri=None, json_uri="/")


def main():
    app.run(host=app.config.get("HOST", "0.0.0.0"),
            port=app.config.get("PORT", 5005))


if __name__ == "__main__":
    main()
