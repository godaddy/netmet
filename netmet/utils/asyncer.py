# Copyright 2017: GoDaddy Inc.

import threading


_THREADS = []
_DIE = threading.Event()


def asyncme(func):
    func._die = _DIE

    def async_call(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        _THREADS.append(thread)

    func.async_call = async_call
    return func


def die(*args, **kwargs):
    global _DIE, _THREADS

    if not _DIE.is_set():
        _DIE.set()
        for t in _THREADS:
            if t:
                t.join()
        _THREADS = []
        _DIE = threading.Event()
