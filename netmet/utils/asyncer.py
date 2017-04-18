# Copyright 2017: GoDaddy Inc.

import threading


_THREADS = []
_DIE = threading.Event()


def async(func):
    func._die = _DIE

    def async(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        _THREADS.append(thread)

    func.async = async
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
