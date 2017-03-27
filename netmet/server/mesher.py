# Copyright 2017: GoDaddy Inc.

import logging

import requests

from netmet import exceptions
from netmet.server import db
from netmet.server.utils import eslock
from netmet.utils import worker


LOG = logging.getLogger(__name__)


class Mesher(worker.LonelyWorker):

    def __init__(self):
        """Do not use this method directly. Use create() instead."""

    @classmethod
    def create(cls, netmet_server_url):
        super(Mesher, cls).create()
        cls._self.netmet_server_url = netmet_server_url

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
                                requests.post("%s:%s/api/v1/config"
                                              % (c[0]["host"], c[0]["port"]),
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
