# Copyright 2017: GoDaddy Inc.

import six


class NetmetException(Exception):

    msg_fmt = "%(message)s"

    def __init__(self, message=None, **kwargs):
        self.kwargs = kwargs

        if "%(message)s" in self.msg_fmt:
            kwargs.update({"message": message})

        super(NetmetException, self).__init__(self.msg_fmt % kwargs)

    def format_message(self):
        return six.text_type(self)


class GlobalLockException(NetmetException):
    msg_fmt = "Global Lock Exception: %(message)s"


class DBNotInitialized(NetmetException):
    msg_fmt = "Try to use DB before it's initialized: %(message)s"


class DBInitFailure(NetmetException):
    msg_fmt = "Can't initialize DB %(elastic)s: %(message)s"
