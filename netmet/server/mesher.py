# Copyright 2017: GoDaddy Inc.

import logging
import random
import threading

from netmet import exceptions
from netmet.server import db
from netmet.server.utils import eslock

import futurist
import futurist.periodics
import requests

LOG = logging.getLogger(__name__)


class Mesher(object):
    _self = None
    _lock = threading.Lock()

    def __init__(self):
        """Do not call this method directly."""

    @classmethod
    def create(cls, netmet_server_url):
        with cls._lock:
            if not cls._self:
                cls._self = cls()
                cls._self.db = db.get()
                cls._self.netmet_server_url = netmet_server_url
                cls._self.worker = futurist.ThreadPoolExecutor()
                cls._self._death = threading.Event()
                cls._self.worker.submit(cls._self._job)

        return cls._self

    @classmethod
    def get(cls):
        return cls._self

    @classmethod
    def destory(cls):
        with cls._lock:
            if cls._self is not None:
                if not cls._self.death.is_set():
                    cls._self.death.set()
                    cls._self.worker.shutdown()
                    cls._self = None

    def _full_mesh(self, clients):
        mesh = []
        for i in xrange(len(clients)):
            mesh.append([clients[i], clients[:i] + clients[i + 1:]])
        return mesh

    def _job(self):
        get_conf = db.get().server_config_get
        is_meshed = lambda cfg: (not cfg or (cfg and not cfg["applied"]) or
                                 (cfg and cfg["meshed"]))

        no_changes_msg = "Mesher: no changes in config detected."

        while not self._death.is_set():
            try:
                if is_meshed(get_conf()):
                    LOG.info(no_changes_msg)
                else:
                    with eslock.Glock("update_config"):
                        # TODO(boris-42): Alogrithm should be a bit smarter
                        # even if it is meshed try to update all not configured
                        # clients.
                        config = get_conf()
                        if not is_meshed(config):
                            LOG.info("Mesher detect new config: "
                                     "Remeshing clients")
                            for c in self._full_mesh(self.db.clients_get()):
                                # TODO(boris-42): Run this in parallel
                                try:
                                    requests.post(
                                        "%s/api/v1/config" % c[0]["host"],
                                        json=c[1])
                                    # Set client configured
                                except Exception:
                                    exc = bool(LOG.isEnabledFor(logging.DEBUG))
                                    LOG.warning(
                                        "Failed to update client config %s "
                                        % c[0]["host"], exc_info=int(exc))

                            self.db.server_config_meshed(config["id"])
                        else:
                            LOG.info(no_changes_msg)

            except exceptions.GlobalLockException:
                pass   # can't accuire lock, someone else is working on it

            except Exception:
                LOG.exception("Mesher update failed")

            self._death.wait(9 + random.random())
