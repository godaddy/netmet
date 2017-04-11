# Copyright 2017: GoDaddy Inc.

import datetime
import random
import select
import socket
import struct

import monotonic


class EXIT_STATUS(object):
    SUCCESS = 0
    ERROR_HOST_NOT_FOUND = 1
    ERROR_TIMEOUT = 2
    ERROR_ROOT_REQUIRED = 3
    ERROR_CANT_OPEN_SOCKET = 4
    ERROR_SOCKET_ERROR = 5


class Ping(object):

    def __init__(self, dest, timeout=1, packet_size=55):
        self.ret_code = 0
        self.sock = None
        self.dest = dest
        self.dest_ip = None
        self.timeout = timeout
        self.packet_size = packet_size
        self._create_socket()

    def _create_socket(self):
        try:
            socket.inet_pton(socket.AF_INET, self.dest)
            dest_ip = self.dest
        except socket.error:
            try:
                dest_ip = socket.gethostbyname(self.dest)
            except socket.gaierror:
                self.ret_code = EXIT_STATUS.ERROR_HOST_NOT_FOUND
                return
        self.dest_ip = dest_ip

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                                      socket.getprotobyname("icmp"))
        except socket.error, (errno, msg):
            if errno == 1:
                self.ret_code = EXIT_STATUS.ERROR_ROOT_REQUIRED
            else:
                self.ret_code = EXIT_STATUS.ERROR_CANT_OPEN_SOCKET
            return

    def __del__(self):
        if getattr(self, "sock", False):
            self.sock.close()

    def ping(self):
        result = {
            "rtt": None,
            "ret_code": None,
            "packet_size": self.packet_size,
            "timeout": self.timeout,
            "timestamp": datetime.datetime.now().isoformat(),
            "dest": self.dest_ip,
            "dest_ip": None
        }

        if not self.sock:
            self._create_socket()

        if self.ret_code:
            result["ret_code"] = self.ret_code
            return result

        try:
            packet_id = random.randint(0, 65534)
            packet = self._create_packet(packet_id)
            while packet:
                strated_at = monotonic.monotonic()
                sent = self.sock.sendto(packet, (self.dest_ip, 1))
                packet = packet[sent:]

            delay = self._response_handler(packet_id, strated_at)
            if delay:
                result["ret_code"] = EXIT_STATUS.SUCCESS
                result["rtt"] = delay
            else:
                result["ret_code"] = EXIT_STATUS.ERROR_TIMEOUT
        except socket.error:
            result["ret_code"] = EXIT_STATUS.ERROR_SOCKET_ERROR

        return result

    def _checksum(self, src):
        checksum = 0
        count_to = len(src) & -2
        count = 0
        while count < count_to:
            this_val = ord(src[count + 1]) * 256 + ord(src[count])
            checksum += this_val
            checksum &= 0xffffffff
            count += 2
        if count_to < len(src):
            checksum += ord(src[len(src) - 1])
            checksum &= 0xffffffff
        checksum = (checksum >> 16) + (checksum & 0xffff)
        checksum += checksum >> 16
        answer = ~checksum
        answer &= 0xffff
        return answer >> 8 | (answer << 8 & 0xff00)

    def _create_packet(self, packet_id):
        """Creates a new echo request packet based on the given id."""
        # Builds Dummy Header
        # Header is type (8), code (8), checksum (16), id (16), sequence (16)
        header = struct.pack("bbHHh", 8, 0, 0, packet_id, 1)
        data = self.packet_size * "Q"

        # Builds Real Header
        header = struct.pack(
            "bbHHh", 8, 0, socket.htons(self._checksum(header + data)),
            packet_id, 1)
        return header + data

    def _response_handler(self, packet_id, sent_at):
        """Handles packet response, returns delay or None if timeout."""
        while monotonic.monotonic() < sent_at + self.timeout:
            ready = select.select([self.sock], [], [], self.timeout)
            received_at = monotonic.monotonic()
            if ready[0] == [] or received_at > sent_at + self.timeout:
                return None

            rec_packet, addr = self.sock.recvfrom(1024)
            received_at = monotonic.monotonic()
            icmp_header = rec_packet[20:28]
            type_, code, checksum, rec_id, sequence = struct.unpack(
                "bbHHh", icmp_header)

            if type_ == 0 and rec_id == packet_id:
                return (received_at - sent_at) * 1000

        return None
