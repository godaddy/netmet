# Copyright 2017: GoDaddy Inc.

import logging
import socket

import cachetools


_HOST_NAME = None
LOG = logging.getLogger(__name__)


@cachetools.cached(cache={})
def get_hostname(addr, port):
    """Returns the host name of service it self."""
    global _HOST_NAME

    if not _HOST_NAME:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((addr, port))
            _HOST_NAME = s.getsockname()[0]
        except socket.error as e:
            LOG.warning("Netmet server can't obtain own host address: %s" % e)
            return None
        finally:
            s.close()

    return _HOST_NAME
