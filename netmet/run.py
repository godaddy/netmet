# Copyright 2017: GoDaddy Inc.

import logging
import os
import signal

from gevent import wsgi

from netmet.client import main as client_main
from netmet.server import main as server_main
from netmet.utils import asyncer


LOG = logging.getLogger(__name__)


def load():
    level = logging.DEBUG if os.getenv("DEBUG") else logging.INFO
    logging.basicConfig(level=level,
                        format='%(asctime)s %(levelname)-8s %(message)s')

    if not os.getenv("APP") or os.getenv("APP") not in ["server", "client"]:
        raise ValueError("Set APP env variable to 'server' or 'client'")
    elif os.getenv("APP") == "server":
        mode = server_main
    else:
        mode = client_main

    port = int(os.getenv("PORT", 5000))
    app = mode.load(port)
    http_server = wsgi.WSGIServer((os.getenv("HOST", ""), port), app)
    app.port = port

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
