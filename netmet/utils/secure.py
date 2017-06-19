# Copyright 2017: GoDaddy Inc.

import datetime
import functools
import hashlib
import hmac

import flask

from netmet import config


def generate_digest(data, hmac_key):
    """Generate a hmac using a known key given the provided content."""
    h = hmac.new(hmac_key, data, digestmod=hashlib.sha384)
    h = hmac.new(h.hexdigest(), data, digestmod=hashlib.sha384)
    return h.hexdigest()


def is_valid_digest(hexdigest, data, valid_hmacs):
    """Check whatever hexdigest is valid for data and any of valid_hmacs

    :param hexdigest: Hex digest that should be checked
    :param data: Original Data that was signed
    :param valid_hmacs: List of valid hmacs
    """
    for valid_hmac in valid_hmacs:
        if hmac.compare_digest(hexdigest, generate_digest(data, valid_hmac)):
            return True
    return False


def gen_hmac_headers(data, hmac=None):
    """Generates and returns valid headers for HMAC auth as dicts

    Generates timestamp place it in X-AUTH-HMAC-TIMESTAMP
    Adds timestamp to data and generates hmac digest and puts it to
    X-AUTH-HMAC-DIGEST.
    """
    if not (hmac or config.get("hmac_keys")):
        return {}

    timestamp = datetime.datetime.now().strftime("%s")
    headers = {}
    headers["X-AUTH-HMAC-TIMESTAMP"] = timestamp
    headers["X-AUTH-HMAC-DIGEST"] = generate_digest(
        data + timestamp, hmac or config.get("hmac_keys")[0])
    return headers


def check_hmac_auth(f):
    """Flask decorator for checking hmac auth."""

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not config.get("hmac_skip_check"):
            data = flask.request.get_data()
            digest = str(flask.request.headers.get("X-AUTH-HMAC-DIGEST"))
            timestamp = flask.request.headers.get("X-AUTH-HMAC-TIMESTAMP")

            if not timestamp or not digest:
                msg = ("Invalid or Missing headers "
                       "X-AUTH-HMAC-DIGEST or X-AUTH-HMAC-TIMESTAMP")
                return flask.jsonify({"error": msg}), 403

            now = datetime.datetime.now().strftime("%s")
            if int(now) - int(timestamp) > 30:
                return flask.jsonify({"error": "HMAC digest expired"}), 403

            if not is_valid_digest(digest, data + timestamp,
                                   config.get("hmac_keys")):
                return flask.jsonify({"error": "Wrong or missing digest"}), 403

        return f(*args, **kwargs)

    return wrapper


def check_basic_auth(f):
    """Basic authentication checker."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        users = config.get("users")
        if users:
            auth = flask.request.authorization
            if not (auth and auth.username in users
                    and users[auth.username] == auth.password):
                return flask.Response(
                    "Could not verify your access level for that URL.\n"
                    "You have to login with proper credentials", 401,
                    {"WWW-Authenticate": "Basic realm=\"Login Required\""})

        return f(*args, **kwargs)

    return decorated
