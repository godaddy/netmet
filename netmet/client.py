# Copyright 2017: GoDaddy Inc.

import flask
from flask_helpers import routing

from netmet.utils import status


app = flask.Flask(__name__, static_folder=None)


@app.errorhandler(404)
def not_found(error):
    return flask.jsonify({"error": "Not Found"}), 404


@app.route("/api/v1/status", methods=['GET'])
def get_status():
    # Return status of service
    return flask.jsonify(status.status()), 200


@app.route("/api/v1/hosts/refresh", methods=['POST'])
def refresh_hosts():
    # Force to refresh hosts list
    return flask.jsonify({"noop": "noop"}), 201


@app.route("/api/v1/unregister", methods=['POST'])
def unregister():
    # unregister
    # system.exit()
    return flask.jsonify({"noop": "noop"}), 201


app = routing.add_routing_map(app, html_uri=None, json_uri="/")


def main():
    app.run(host=app.config.get("HOST", "0.0.0.0"),
            port=app.config.get("PORT", 5000))


if __name__ == "__main__":
    main()
