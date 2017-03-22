# Copyright 2017: GoDaddy Inc.

import logging

import futurist
import requests

from netmet import exceptions
from netmet.server import db
from netmet.server.utils import eslock
from netmet.utils import worker


LOG = logging.getLogger(__name__)


class Deployer(worker.LonelyWorker):

    def __init__(self):
        """Do not use this method directly. Use create() instead."""

    def _job(self):
        get_conf = db.get().server_config_get
        is_applied = lambda cfg: not cfg or (cfg and cfg["applied"])

        no_changes_msg = "Deployer: no changes in config detected."

        try:
            if is_applied(get_conf()):
                LOG.info(no_changes_msg)
            else:
                with eslock.Glock("update_config"):
                    config = get_conf()   # Refresh config after lock
                    if not is_applied(config):
                        LOG.info("Deployer detect new config: "
                                 "Updating deployment")
                        clients = db.get().clients_get()

                        # TODO(boris-42): Add support of multi drivers
                        new_clients = StaticDeployer().redeploy(
                            config["config"]["static"], clients)

                        db.get().clients_set(new_clients)
                        db.get().server_config_apply(config["id"])
                    else:
                        LOG.info(no_changes_msg)

        except exceptions.GlobalLockException:
            pass   # can't accuire lock, someone else is working on it

        except Exception:
            LOG.exception("Deployer update failed")

    def redeploy(self, config, clients):
        """Should update deployment based on change in config."""
        raise NotImplemented()


class StaticDeployer(Deployer):

    def redeploy(self, config, old_clients):
        new_clients = config["clients"]

        old_idx = {c["host"]: c for c in old_clients}
        new_idx = {c["host"]: c for c in new_clients}

        for c in new_clients:
            c["running"] = c["host"] in old_idx
            c["configured"] = False

        unregister = ["%s/api/v1/unregister" % h for h in old_idx
                      if h not in new_idx]
        with futurist.ThreadPoolExecutor(max_workers=10) as e:
            e.map(requests.post, unregister)

        return new_clients
