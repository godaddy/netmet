# Copyright 2017: GoDaddy Inc.

import collections
import datetime
import logging
import threading
import time

import futurist
import futurist.rejection
import monotonic
import requests

from netmet.utils import ping
from netmet.utils import pusher

LOG = logging.getLogger(__name__)


class Collector(object):
    pinger_failed_msg = "Pinger failed to ping"

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
        self.processing_thread = None

    def gen_periodic_ping(self, host):
        pinger = ping.Ping(host["ip"],
                           timeout=self.timeout, packet_size=self.packet_size)

        def ping_():
            try:
                result = pinger.ping()
                self.queue.append({
                    "east-west": {
                        "client_src": self.client_host,
                        "client_dest": host,
                        "protocol": "icmp",
                        "timestamp": result["timestamp"],
                        "latency": result["rtt"],
                        "packet_size": result["packet_size"],
                        "lost":  int(bool(result["ret_code"])),
                        "transmitted": int(not bool(result["ret_code"])),
                        "ret_code": result["ret_code"]
                    }
                })
            except Exception:
                LOG.exception(self.pinger_failed_msg)

        return ping_

    def gen_periodic_http_ping(self, host):

        def http_ping():
            try:
                started_at = monotonic.monotonic()
                packet = {
                    "east-west": {
                        "client_src": self.client_host,
                        "client_dest": host,
                        "protocol": "http",
                        "timestamp": datetime.datetime.now().isoformat(),
                        "packet_size": 0,
                        "latency": 0,
                        "lost": 1,
                        "transmitted": 0,
                        "ret_code": 504
                    }
                }

                r = requests.get("http://%s:%s" % (host["host"], host["port"]),
                                 timeout=self.timeout)

                packet["east-west"].update({
                    "latency": (monotonic.monotonic() - started_at) * 1000,
                    "packet_size": len(r.content),
                    "lost":  int(r.status_code != 200),
                    "transmitted": int(r.status_code == 200),
                    "ret_code": r.status_code
                })
            except requests.exceptions.ConnectionError:
                pass
            except Exception:
                LOG.exception("Collector failed to call another clinet API")
            finally:
                self.queue.append(packet)

        return http_ping

    def process_results(self):
        while self.queue or self.running:
            while self.queue:
                item = self.queue.popleft()
                if self.pusher:
                    self.pusher.add(item)   # push to netmet server data
                else:
                    print(item)   # netmet client standalone mode

            time.sleep(0.1)

    def _job(self):
        callables = []
        for i, h in enumerate(self.hosts):
            callables.append(self.gen_periodic_ping(h))
        for i, h in enumerate(self.hosts):
            callables.append(self.gen_periodic_http_ping(h))

        period = self.period / float(len(callables))
        pool = futurist.ThreadPoolExecutor(
            max_workers=50,
            check_and_reject=futurist.rejection.reject_when_reached(50))

        while self.running:
            for item in callables:
                while self.running:
                    try:
                        pool.submit(item)
                        break
                    except futurist.RejectedSubmission:
                        LOG.warning("Collector: Feed me! Mreee threads!")
                        time.sleep(period)

                time.sleep(period)

    def start(self):
        with self.lock:
            if self.running:
                return False
            self.running = True

        if self.pusher:
            self.pusher.start()

        self.main_thread = threading.Thread(target=self._job)
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
                self.main_thread.join()
                self.processing_thread.join()
                if self.pusher:
                    self.pusher.stop()
