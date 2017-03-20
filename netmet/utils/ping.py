# Copyright 2017: GoDaddy Inc.

# Pure ptyhon ping implementation that uses raw sockets. Based on
# :homepage: https://github.com/socketubs/Pyping/
# :copyleft: 1989-2011 by the python-ping team, see AUTHORS for more details.
# :license: GNU GPL v2, see LICENSE for more details.

import collections
import datetime
import logging
import select
import socket
import struct
import threading

import enum
import monotonic


LOG = logging.getLogger(__name__)


def _repeating_count(max_val=65534):
    i = 0
    while True:
        yield i
        i = i + 1
        if i > max_val:
            i = 0


def _find_dest_ip(dest):
    dest_ip = None
    try:
        socket.inet_pton(socket.AF_INET, dest)
        dest_ip = dest
    except socket.error:
        try:
            dest_ip = socket.gethostbyname(dest)
        except socket.gaierror:
            pass
    return dest_ip


def _checksum(src_string):
    checksum = 0
    count_to = len(src_string) & -2
    count = 0
    while count < count_to:
        this_val = ord(src_string[count + 1]) * 256 + ord(src_string[count])
        checksum += this_val
        checksum &= 0xffffffff  # Necessary?
        count += 2
    if count_to < len(src_string):
        checksum += ord(src_string[len(src_string) - 1])
        checksum &= 0xffffffff  # Necessary?
    checksum = (checksum >> 16) + (checksum & 0xffff)
    checksum += checksum >> 16
    answer = ~checksum
    answer &= 0xffff
    return answer >> 8 | (answer << 8 & 0xff00)


class ExitStatus(enum.IntEnum):
    SUCCESS = 0
    ERROR_HOST_NOT_FOUND = 1
    ERROR_TIMEOUT = 2
    ERROR_ROOT_REQUIRED = 3
    ERROR_CANT_OPEN_SOCKET = 4
    ERROR_SOCKET_SEND_ERROR = 5
    ERROR_SOCKET_READ_ERROR = 6
    ERROR_CANCELLED = 7


class Ping(object):
    def __init__(self, dest,
                 timeout=1, packet_size=55, src_addr=False,
                 packet_id=None, dest_ip=None):
        self.packet_size = packet_size
        self.timeout = timeout
        self.created_on = datetime.datetime.now().isoformat()
        self.src_addr = src_addr
        self.packet_size = packet_size
        self.dest = dest
        self.packet_id = packet_id
        self.dest_ip = dest_ip
        # Filled in at runtime...
        self.ret_code = None
        self.started_at = None
        self.ended_at = None

    @property
    def rtt(self):
        _rtt = None
        if self.started_at is not None and self.ended_at is not None:
            _rtt = max(0, self.ended_at - self.started_at)
        return _rtt

    def expired(self):
        if self.ret_code is not None or self.timeout is None:
            return False

        if self.started_at is not None:
            elapsed = max(0, monotonic.monotonic() - self.started_at)
            return self.timeout < elapsed

        return False

    def create_packet(self):
        """Creates a new echo request packet."""
        # See: https://tools.ietf.org/html/rfc792
        #
        # Builds Dummy Header
        # Header is type (8), code (8), checksum (16), id (16), sequence (16)
        header = struct.pack("bbHHh", 8, 0, 0, self.packet_id, 1)
        data = self.packet_size * "Q"
        # Builds Real Header
        header = struct.pack(
            "bbHHh", 8, 0, socket.htons(_checksum(header + data)),
            self.packet_id, 1)
        return header + data


class Pinger(object):
    MAX_WAIT = 0.1
    MAX_PACKET_SIZE = 1024

    def __init__(self, ):
        self._dead = threading.Event()
        self._processor = None
        self._lock = threading.Lock()
        self._id_lock = threading.Lock()
        self._sock = None
        self._to_read = {}
        self._to_send = collections.deque()
        self._packet_id_maker = _repeating_count()

    def start(self):

        def process_write():
            try:
                ping, on_done = self._to_send.popleft()
            except IndexError:
                pass
            else:
                packet = ping.create_packet()
                ping.started_at = monotonic.monotonic()
                try:
                    while packet:
                        sent = self._sock.sendto(packet, (ping.dest_ip, 1))
                        packet = packet[sent:]
                except socket.error:
                    ping.ret_code = ExitStatus.ERROR_SOCKET_SEND_ERROR
                else:
                    with self._lock:
                        self._to_read[ping.packet_id] = (ping, on_done)

        def process_read():
            try:
                rec_packet, addr = self._sock.recvfrom(1024)
            except socket.error:
                pass
            else:
                icmp_header = rec_packet[20:28]
                type_, code, checksum, rec_id, sequence = struct.unpack(
                    "bbHHh", icmp_header)
                if type_ != 0:
                    return
                try:
                    ping, _on_done = self._to_read[rec_id]
                except KeyError:
                    # Got back a rec_id for something that does not exist
                    # anymore, or something unknown, so skip it...
                    pass
                else:
                    ping.ended_at = monotonic.monotonic()
                    ping.ret_code = ExitStatus.SUCCESS

        def loop_forever():
            while not self._dead.is_set():
                timeout = self.MAX_WAIT
                if self._to_read or self._to_send:
                    res = select.select(
                        [self._sock], [self._sock], [], timeout)
                    if res[0]:
                        process_read()
                    if res[1]:
                        process_write()
                    finished_ids = set()
                    with self._lock:
                        for id, (ping, on_done) in self._to_read.items():
                            if ping.expired():
                                ping.ret_code = ExitStatus.ERROR_TIMEOUT
                            if ping.ret_code is not None:
                                finished_ids.add(id)
                    if finished_ids:
                        # Capture all that was done, but don't trigger
                        # the *user specified* callbacks while holding
                        # the lock...
                        on_dones = []
                        with self._lock:
                            for id in finished_ids:
                                on_dones.append(self._to_read.pop(id))
                        for ping, on_done in on_dones:
                            on_done(ping)
                else:
                    self._dead.wait(timeout)

        if self._processor is not None:
            raise RuntimeError("Already started")
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                                       socket.getprotobyname("icmp"))
        self._processor = threading.Thread(target=loop_forever)
        self._processor.daemon = True
        self._processor.start()

    def stop(self):
        self._dead.set()
        if self._processor is not None:
            self._processor.join()
            self._processor = None
        if self._sock is None:
            self._sock.close()
            self._sock = None
        while self._to_read:
            _id, (ping, on_done) = self._to_read.popitem()
            if ping.ret_code is not None:
                ping.ret_code = ExitStatus.ERROR_CANCELLED
            on_done(ping.to_munch())
        while self._to_send:
            ping, on_done = self._to_send.popleft()
            ping.ret_code = ExitStatus.ERROR_CANCELLED
            on_done(ping.to_munch())

    def ping(self, dest, timeout=1, packet_size=55, src_addr=False):
        cap = {}
        cap['result'] = None
        ev = threading.Event()

        def on_ping_done(result):
            cap['result'] = result
            ev.set()

        self.async_ping(dest, on_ping_done,
                        timeout=timeout, packet_size=packet_size,
                        src_addr=src_addr)
        ev.wait()
        return cap['result']

    def async_ping(self, dest, on_ping_done,
                   timeout=1, packet_size=55, src_addr=False):
        if packet_size > self.MAX_PACKET_SIZE:
            raise ValueError("Packet size limited"
                             " to %s" % self.MAX_PACKET_SIZE)
        if self._processor is None or self._dead.is_set():
            raise RuntimeError("Start has not been called, can not ping")
        src_addr = src_addr and socket.gethostbyname(src_addr)
        with self._id_lock:
            packet_id = self._packet_id_maker.next()
        ping = Ping(dest, timeout=timeout, packet_size=packet_size,
                    src_addr=src_addr,
                    packet_id=packet_id,
                    dest_ip=_find_dest_ip(dest))
        if not ping.dest_ip:
            ping.ret_code = ExitStatus.ERROR_HOST_NOT_FOUND
            on_ping_done(ping)
        else:
            self._to_send.append((ping, on_ping_done))
