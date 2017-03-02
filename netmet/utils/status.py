# Copyright 2017: GoDaddy Inc.

import datetime


started_at = datetime.datetime.now()


def status():
    return {
        "started_at": started_at,
        "runtime":  (datetime.datetime.now() - started_at).seconds
    }