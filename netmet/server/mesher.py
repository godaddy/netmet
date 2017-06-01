# Copyright 2017: GoDaddy Inc.

import logging

import requests

from netmet import exceptions
from netmet.server import db
from netmet.server.utils import eslock
from netmet.utils import worker


LOG = logging.getLogger(__name__)


class MeshPlugin(object):

    def mesh(self, config, clients, external):
        return []


class FullMesh(MeshPlugin):

    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "north-south": {
                "type": "object",
                "patternProperties": {
                    "(http)|(icmp)": {
                        "type": "object",
                        "properties": {
                            "period": {"type": "number"},
                            "timeout": {"type": "number"},
                            "packet_size": {"type": "number"}
                        }
                    }
                }
            },
        },
        "additionalProperties": False
    }

    def mesh(self, mesh_config, clients, external):

        for client in clients:
            tasks = []

            for other_client in clients:
                if client == other_client:
                    continue

                for protocol in ["http", "icmp"]:
                    task = {"dest": other_client, "protocol": protocol}
                    if mesh_config.get("north-south", {}).get(protocol):
                        task["settings"] = mesh_config["north-south"][protocol]

                    tasks.append({"east-west": task})

            for ext in external:
                tasks.append({
                    "north-south": {
                        "dest": ext["dest"],
                        "protocol": ext["protocol"],
                        "settings": {
                            "period": ext["period"],
                            "timeout": ext["timeout"]
                        }
                    }
                })

            yield client, tasks


class DistributedMesh(MeshPlugin):

    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "distributed_mesh": {
                "type": "object",
                "properties": {
                    "north-south": {
                        "type": "object",
                        "properties": {
                            "spread": {
                                "enum": ["hypervisor", "dc", "az", "all"]
                            },
                            "repeat": {"type": "number", "minimum": 1},
                            "period": {"type": "number", "minimum": 1},
                            "timeout": {"type": "number", "minimum": 1}
                        }
                    },
                    "east-west": {
                        "type": "object",
                        "properties": {
                            "repeat_inside_az": {
                                "type": "number",
                                "minimum": 1
                            },
                            "repeat_between_az": {
                                "type": "number",
                                "minimum": 1
                            },
                        }
                    }
                }
            }
        }
    }

    def mesh(self, config, clients, external):
        pass


class Mesher(worker.LonelyWorker):
    no_changes_msg = "Mesher: no changes in config detected."
    new_config_msg = "Mesher detect new config: Remeshing clients."
    update_failed_msg = "Mesher update failed."
    lock_name = "update_config"
    client_api = "http://%s:%s/api/v2/config"
    # TODO(boris-42): Make this plugable
    plugins = {
        "full_mesh": FullMesh()
    }

    def __init__(self):
        """Do not use this method directly. Use create() instead."""

    @classmethod
    def get_jsonschema(cls):
        return {
            "type": "object",
            "oneOf": [
                {"properties": {name: p.CONFIG_SCHEMA}}
                for name, p in cls.plugins.iteritems()
            ]
        }

    @classmethod
    def create(cls, netmet_server_url):
        super(Mesher, cls).create()
        cls._self.netmet_server_url = netmet_server_url

    def _update_client(self, client, tasks):
        try:
            body = {
                "netmet_server": self.netmet_server_url,
                "client_host": client,
                "tasks": tasks,
                "settings": {
                    "timeout": 1,
                    "period": 5
                }
            }
            requests.post(self.client_api % (client["host"], client["port"]),
                          json=body)
            # Set client configured
        except Exception as e:
            exc = bool(LOG.isEnabledFor(logging.DEBUG))
            msg = "Failed to update client config %s. "
            if exc:
                LOG.exception(msg % client["host"])
            else:
                LOG.warning(msg % client["host"] + str(e))

            return False, (500, msg % client["host"])

        return True, 200, "Client updated"

    def _mesh(self, config):
        mesh = self.plugins[config["mesher"].keys()[0]].mesh

        allowed = set(["ip", "port", "host", "hypervisor", "dc", "az"])
        clients = [{k: x[k] for k in allowed if k in x}
                   for x in db.get().clients_get()]

        return mesh(config["mesher"].values()[0], clients, config["external"])

    def refresh_client(self, host, port):
        lock_acuired = False
        attempts = 0

        while not lock_acuired and attempts < 3:
            try:
                with eslock.Glock("update_config"):
                    config = db.get().server_config_get()
                    if not (config["applied"] and config["meshed"]):
                        return False, 404, "Configuration not found"

                    for c in self._mesh(config["config"]):
                        if c[0]["host"] == host and c[0]["port"] == port:
                            return self._update_client(c[0], c[1])

                    return False, 404, "Client not found"

            except exceptions.GlobalLockException:
                attempts += 1
                self._death.wait(0.1)

        return False, 500, "Couldn't accuire lock"

    def _job(self):
        get_conf = db.get().server_config_get
        is_meshed = lambda cfg: (not cfg or (cfg and not cfg["applied"]) or
                                 (cfg and cfg["meshed"]))
        try:
            if is_meshed(get_conf()):
                LOG.info(self.no_changes_msg)
            else:
                with eslock.Glock("update_config"):
                    # TODO(boris-42): Alogrithm should be a bit smarter
                    # even if it is meshed try to update all not configured
                    # clients.
                    config = get_conf()
                    if not is_meshed(config):
                        LOG.info(self.new_config_msg)
                        for c in self._mesh(config["config"]):
                            # TODO(boris-42): Run this in parallel
                            self._update_client(c[0], c[1])
                        db.get().server_config_meshed(config["id"])
                    else:
                        LOG.info(self.no_changes_msg)

        except exceptions.GlobalLockException:
            pass   # can't accuire lock, someone else is working on it

        except Exception:
            LOG.exception(self.update_failed_msg)
