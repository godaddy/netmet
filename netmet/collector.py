# Copyright 2017: GoDaddy Inc.

import collections
import threading
import time

import futurist
import futurist.periodics

from netmet.utils import ping


class Collector(object):

    def __init__(self, netmet_server, client_host, hosts,
                 period=5, timeout=1, packet_size=55):
        self.netmet_server = netmet_server
        self.client_host = client_host
        self.hosts = hosts
        self.period = period
        self.timeout = timeout
        self.packet_size = packet_size

        self.lock = threading.Lock()
        self.queue = collections.deque()
        self.running = False
        self.main_thread = None
        self.main_worker = None
        self.processing_thread = None

    def gen_periodic_ping(self, host):

        @futurist.periodics.periodic(self.period)
        def ping_():
            result = ping.ping(host["client_ip"],
                               timeout=self.timeout,
                               packet_size=self.packet_size)
            self.queue.append({
                "src": self.client_host,
                "dest": host,
                "timestamp": result["timestamp"],
                "latency": result["rtt"],
                "packet_size": result["packet_size"],
                "transmitted":  1 if result["ret_code"] == 0 else 0,
                "ret_code": result["ret_code"]
            })

        return ping_

    def process_results(self):
        while self.queue or self.running:
            while self.queue:
                print(self.queue.popleft())
            time.sleep(0.5)

    def start(self):
        with self.lock:
            if self.running:
                return False
            self.running = True

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
