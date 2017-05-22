# Copyright 2017: GoDaddy Inc.

import json
import logging
import os

import requests

from netmet.utils import asyncer


LOG = logging.getLogger(__name__)

_RUNTIME_CONF_DIR = "/var/run/netmet/"
_RUNTIME_CONF_FILE = _RUNTIME_CONF_DIR + "restore_api_%s"
_RESTORE_API = "%(server)s/api/v1/clients/%(host)s/%(port)s"


@asyncer.async
def restore(port):
    url = restore_url_get(port)
    if not url:
        return

    restore._die.wait(0.25)   # note(boris-42): Let NetMet client start
    while not restore._die.is_set():
        try:
            r = requests.post(url)
            if r.status_code == 404:
                restore_url_clear(port)
            if r.status_code in [200, 404]:
                return
        except requests.exceptions.RequestException as e:
            LOG.warning("Netmet Server API %s is not available %s" % (url, e))
        except Exception:
            LOG.exception("Something went wrong during the attempt "
                          "to call netmet server to referesh config.")
            return

        if url != restore_url_get(port):
            break

        restore._die.wait(1)


def restore_url_get(port):
    try:
        path = _RUNTIME_CONF_FILE % port

        with open(path, "rw") as f:
            LOG.info("Loading restore conf url from previous run: %s" % path)
            return json.load(f).get("refresh_conf_url", None)
    except IOError:
        LOG.info("Didn't find previous config: %s" % path)

    except Exception:
        LOG.exception("Failed to load restore_conf_url from previous run")
        return None


def restore_url_set(netmet_server, host, port):
    LOG.info("Setting new netmet restore_conf_url % s"
             % _RUNTIME_CONF_FILE % port)
    try:
        if not os.path.exists(_RUNTIME_CONF_DIR):
            LOG.info("Creating directory: %s" % _RUNTIME_CONF_DIR)
            os.makedirs(_RUNTIME_CONF_DIR)

        with open(_RUNTIME_CONF_FILE % port, "w+") as f:
            if netmet_server:
                data = {"server": netmet_server, "host": host, "port": port}
                json.dump({"refresh_conf_url": _RESTORE_API % data}, f)
            else:
                json.dump({"refresh_conf_url": None}, f)

    except Exception:
        LOG.exception("Failed to store runntime info refresh_conf_url")


def restore_url_clear(port):
    try:
        os.remove(_RUNTIME_CONF_FILE % port)
    except OSError:
        pass
