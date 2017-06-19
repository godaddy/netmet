# Copyright 2017: GoDaddy Inc.

import logging
import os
import signal
import sys

from gevent import wsgi

from netmet.client import main as client_main
from netmet import config
from netmet.server import main as server_main
from netmet.utils import asyncer


LOG = logging.getLogger(__name__)


def _parse_auth_info():
    auth = os.getenv("NETMET_AUTH", "")

    if not auth:
        return {}

    users = {}
    for pairs in auth.split(","):
        user_password = pairs.split(":")

        if len(user_password) != 2:
            raise ValueError("NETMET_AUTH has wrong format at '%s'" % pairs)

        if user_password[0] in users:
            raise ValueError("NETMET_AUTH has duplicated user: '%s'"
                             % user_password[0])

        password_strength_checks = {
            "Password should have at least 6 symbols": lambda x: len(x) < 6,
            "Use upper and lower case": lambda x: x.lower() == x,
            "Use at least one number": lambda x: all(
                ord(c) < 48 and ord(c) > 57 for c in x)
        }

        user, password = user_password

        for reason, check in password_strength_checks.iteritems():
            if check(user_password[1]):
                raise ValueError("NETMET_AUTH has invalid password '%s': %s "
                                 % (user_password[1], reason))

        users[user_password[0]] = user_password[1]

    return users


def _parse_hmac():
    skip_check = os.getenv("NETMET_HMAC_SKIP", False)
    hmacs = os.getenv("NETMET_HMACS", "").strip()

    if not hmacs and not skip_check:
        raise ValueError("Set NETMET_HMAC_SKIP=True or Set NETMET_HMACS")

    hmacs = hmacs and hmacs.split(",") or []
    if not all(hmacs):
        raise ValueError("One of HMAC is empty in NETMET_HMACS env variable.")

    return hmacs, skip_check


def load():
    level = logging.DEBUG if os.getenv("DEBUG") else logging.INFO
    logging.basicConfig(level=level,
                        format="%(asctime)s %(levelname)-8s %(message)s",
                        stream=sys.stdout)

    if not os.getenv("APP") or os.getenv("APP") not in ["server", "client"]:
        raise ValueError("Set APP env variable to 'server' or 'client'")
    elif os.getenv("APP") == "server":
        mode = server_main
    else:
        mode = client_main

    port = int(os.getenv("PORT", 5000))
    config.set("port", port)
    config.set("users", _parse_auth_info())
    hmacs, check_hmac = _parse_hmac()
    config.set("hmac_keys", hmacs)
    config.set("hmac_skip_check", check_hmac)

    app = mode.load()
    http_server = wsgi.WSGIServer((os.getenv("HOST", ""), port), app)

    def die(*args, **kwargs):
        LOG.info("Stopping netmet %s" % os.getenv("APP"))
        if os.getenv("APP") == "server":
            LOG.info("Stopping HTTP server")
            http_server.stop()
        LOG.info("Joining internal threads")
        mode.die()
        asyncer.die()
        if os.getenv("APP") == "client":
            LOG.info("Stopping HTTP server")
            http_server.stop()
        LOG.info("Bye Bye!")

    signal.signal(signal.SIGTERM, die)
    signal.signal(signal.SIGINT, die)
    return http_server


def run():
    load().serve_forever()


if __name__ == "__main__":
    run()
