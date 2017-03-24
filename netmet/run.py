# Copyright 2017: GoDaddy Inc.

import logging
import os

from gevent import wsgi

from netmet.client import main as client_main
from netmet.server import main as server_main


def run():
    level = logging.DEBUG if os.getenv("DEBUG") else logging.INFO
    logging.basicConfig(level=level)

    if not os.getenv("APP") or os.getenv("APP") not in ["server", "client"]:
        raise ValueError("Set APP env variable to 'server' or 'client'")

    elif os.getenv("APP") == "server":
        app = server_main.load()
    else:
        app = client_main.load()

    http_server = wsgi.WSGIServer(
        (os.getenv("HOST", ""), int(os.getenv("PORT", 5000))), app)
    http_server.serve_forever()


if __name__ == "__main__":
    run()
