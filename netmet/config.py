# Copyright 2017: GoDaddy Inc.

_DATA = {}


def set(key, value):
    _DATA[key] = value


def get(key):
    return _DATA[key]
