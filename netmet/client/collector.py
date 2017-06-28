# Copyright 2017: GoDaddy Inc.

import collections
import datetime
import logging
import random
import threading

import futurist
import futurist.rejection
import monotonic
import requests

from netmet.utils import ping
from netmet.utils import pusher
from netmet.utils import secure

LOG = logging.getLogger(__name__)


class Collector(object):
    pinger_failed_msg = "Pinger failed to ping"

    def __init__(self, netmet_server, client_host, tasks):
        self.client_host = client_host
        self.tasks = tasks
        self.pusher = None
        if netmet_server:
            netmet_server = netmet_server.rstrip("/")
            self.pusher = pusher.Pusher("%s/api/v1/metrics" % netmet_server,
                                        extra_headers=secure.gen_hmac_headers)

        self.lock = threading.Lock()
        self.queue = collections.deque()
        self.death = threading.Event()
        self.started = False
        self.main_thread = None
        self.processing_thread = None

    def gen_periodic_ping(self, task):

        ip = (task["north-south"]["dest"] if "north-south" in task else
              task["east-west"]["dest"]["ip"])
        settings = task[task.keys()[0]]["settings"]
        pinger = ping.Ping(ip, timeout=settings["timeout"],
                           packet_size=settings["packet_size"])

        def ping_():
            try:
                result = pinger.ping()

                metric = {
                    "client_src": self.client_host,
                    "protocol": "icmp",
                    "timestamp": result["timestamp"],
                    "latency": result["rtt"],
                    "packet_size": result["packet_size"],
                    "lost": int(bool(result["ret_code"])),
                    "transmitted": int(not bool(result["ret_code"])),
                    "ret_code": result["ret_code"]
                }

                if "north-south" in task:
                    metric["dest"] = task["north-south"]["dest"]
                    self.queue.append({"north-south": metric})

                else:
                    metric["client_dest"] = task["east-west"]["dest"]
                    self.queue.append({"east-west": metric})

            except Exception:
                LOG.exception(self.pinger_failed_msg)

        return ping_

    def gen_periodic_http_ping(self, task):

        def http_ping():
            try:
                started_at = monotonic.monotonic()

                metric = {
                    "client_src": self.client_host,
                    "protocol": "http",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "packet_size": 0,
                    "latency": 0,
                    "lost": 1,
                    "transmitted": 0,
                    "ret_code": 504
                }
                settings = task[task.keys()[0]]["settings"]

                if "east-west" in task:
                    dest = task["east-west"]["dest"]
                    metric["client_dest"] = dest
                    dest = "http://%s:%s" % (dest["host"], dest["port"])
                else:
                    dest = task["north-south"]["dest"]
                    metric["dest"] = dest

                r = requests.get(dest, timeout=settings["timeout"])
                metric.update({
                    "latency": (monotonic.monotonic() - started_at) * 1000,
                    "packet_size": len(r.content),
                    "lost": int(r.status_code != 200),
                    "transmitted": int(r.status_code == 200),
                    "ret_code": r.status_code
                })
            except requests.exceptions.ConnectionError:
                pass
            except Exception:
                LOG.exception("Collector failed to call another clinet API")
            finally:
                type_ = "east-west" if "east-west" in task else "north-south"
                self.queue.append({type_: metric})

        return http_ping

    def process_results(self):
        while self.queue or not self.death.is_set():
            while self.queue:
                item = self.queue.popleft()
                if self.pusher:
                    self.pusher.add(item)   # push to netmet server data
                else:
                    print(item)   # netmet client standalone mode

            self.death.wait(0.1)

    def _job_per_period(self, callables, period):

        def helper():
            delay = period / float(len(callables))
            pool = futurist.ThreadPoolExecutor(
                max_workers=50,
                check_and_reject=futurist.rejection.reject_when_reached(50))

            with pool:
                while not self.death.is_set():
                    for item in callables:
                        while not self.death.is_set():
                            try:
                                pool.submit(item)
                                break
                            except futurist.RejectedSubmission:
                                LOG.warning("Collector: Feed me! Mre threads!")
                                self.death.wait(delay)

                        self.death.wait(delay)

                    # up to 0.1 second delay  between runs of tasks
                    self.death.wait(random.random() * min(delay, 1) / 10.0)
        return helper

    def _job(self):
        generators = {
            "icmp": self.gen_periodic_ping,
            "http": self.gen_periodic_http_ping
        }

        period_tasks = {}
        for task in self.tasks:
            task_data = task.values()[0]
            period_ = task_data["settings"]["period"]
            protocol = task_data["protocol"]
            period_tasks.setdefault(period_, [])
            if protocol in generators:
                period_tasks[period_].append(generators[protocol](task))
            else:
                LOG.warning("Allowed protocols are: %s" % generators.keys())

        pool = futurist.ThreadPoolExecutor(max_workers=len(period_tasks))
        with pool:
            min_period = min(period_tasks)
            min_lag = float(min_period) / len(period_tasks[min_period])
            lag = min(min_lag / len(period_tasks), 1)

            LOG.info(period_tasks)
            for period, callables in period_tasks.iteritems():
                pool.submit(self._job_per_period(callables, period))
                self.death.wait(lag)

    def start(self):
        with self.lock:
            if not self.started:
                self.started = True
                self.death = threading.Event()
            else:
                return

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
            if self.started and not self.death.is_set():
                self.death.set()
                self.main_thread.join()
                self.processing_thread.join()
                if self.pusher:
                    self.pusher.stop()
                self.started = False
