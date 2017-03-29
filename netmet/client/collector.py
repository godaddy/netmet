# Copyright 2017: GoDaddy Inc.

import collections
import logging
import threading
import time

import futurist
import futurist.periodics

from netmet.utils import ping
from netmet.utils import pusher

LOG = logging.getLogger(__name__)


class Collector(object):

    def __init__(self, netmet_server, client_host, hosts,
                 period=5, timeout=1, packet_size=55):
        self.client_host = client_host
        self.hosts = hosts
        self.period = period
        self.timeout = timeout
        self.packet_size = packet_size
        self.pusher = None
        if netmet_server:
            netmet_server = netmet_server.rstrip("/")
            self.pusher = pusher.Pusher("%s/api/v1/metrics" % netmet_server)

        self.lock = threading.Lock()
        self.queue = collections.deque()
        self.running = False
        self.main_thread = None
        self.main_worker = None
        self.processing_thread = None
        self.pinger = ping.Pinger()

    def gen_periodic_ping(self, host):
        @futurist.periodics.periodic(self.period)
        def ping_():
            try:
                result = self.pinger.ping(host["ip"],
                                          timeout=self.timeout,
                                          packet_size=self.packet_size)
                self.queue.append({
                    "east-west": {
                        "client_src": self.client_host,
                        "client_dest": host,
                        "protocol": "icmp",
                        "timestamp": result.created_on,
                        "latency": result.rtt and result.rtt * 1000,
                        "packet_size": result.packet_size,
                        "lost":  int(bool(result.ret_code.value)),
                        "transmitted": int(not bool(result.ret_code.value)),
                        "ret_code": result.ret_code.value
                    }
                })
            except Exception:
                LOG.exception("Pinger failed to ping")

        return ping_

    def process_results(self):
        while self.queue or self.running:
            while self.queue:
                item = self.queue.popleft()
                if self.pusher:
                    self.pusher.add(item)   # push to netmet server data
                else:
                    print(item)   # netmet client standalone mode

            time.sleep(0.5)

    def start(self):
        with self.lock:
            if self.running:
                return False
            self.running = True

        self.pinger.start()
        self.pusher.start()
        callables = [(self.gen_periodic_ping(h), (), {}) for h in self.hosts]
        executor_factory = lambda: futurist.ThreadPoolExecutor(max_workers=50)
        self.main_worker = futurist.periodics.PeriodicWorker(
            callables, executor_factory=executor_factory)
        self.main_thread = threading.Thread(target=self.main_worker.start)
        self.main_thread.daemon = True
        self.main_thread.start()

        self.processing_thread = threading.Thread(target=self.process_results)
        self.processing_thread.deamon = True
        self.processing_thread.start()
        return True

    def stop(self):
        with self.lock:
            if self.running:
                self.running = False
                self.main_worker.stop()
                self.main_worker.wait()
                self.main_thread.join()
                self.processing_thread.join()
                self.pinger.stop()
                self.pusher.stop()
