# Copyright 2017: GoDaddy Inc.

import logging

from netmet import exceptions
from netmet.server import db


LOG = logging.getLogger(__name__)


class Glock(object):

    def __init__(self, name, ttl=10):
        self.name = name
        self.accuired = False
        self.ttl = 10

    def __enter__(self):
        if self.accuired:
            raise exceptions.GlobalLockException("Lock already in use %s"
                                                 % self.name)
        if db.get().lock_accuire(self.name, self.ttl):
            self.accuired = True
        else:
            raise exceptions.GlobalLockException("Can't lock %s" % self.name)

    def __exit__(self, exception_type, exception_value, traceback):
        if not db.get().lock_release(self.name):
            logging.warning("Can't release lock %(name)s."
                            % {"name": self.name})

        self.accuired = False
