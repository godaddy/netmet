# Copyright 2017: GoDaddy Inc.

# Pure ptyhon ping implementation that uses raw sockets. Based on
# :homepage: https://github.com/socketubs/Pyping/
# :copyleft: 1989-2011 by the python-ping team, see AUTHORS for more details.
# :license: GNU GPL v2, see LICENSE for more details.

import datetime
import random
import select
import socket
import struct
import time


class EXIT_STATUS(object):
    SUCCESS = 0
    ERROR_HOST_NOT_FOUND = 1
    ERROR_TIMEOUT = 2
    ERROR_ROOT_REQUIRED = 3
    ERROR_CANT_OPEN_SOCKET = 4
    ERROR_SOCKET_ERROR = 5


def ping(dest, timeout=1, packet_size=55, src_addr=False):
    result = {
        "rtt": None,
        "ret_code": None,
        "packet_size": packet_size,
        "timeout": timeout,
        "timestamp": datetime.datetime.now().isoformat(),
        "src": src_addr,
        "dest": dest,
        "packet_size": packet_size,
        "dest_ip": None
    }

    src_addr = src_addr and socket.gethostbyname(src_addr)

    # Check whatever is passed IP or hostname, if hostname translate to IP
    try:
        socket.inet_pton(socket.AF_INET, dest)
        dest_ip = dest
    except socket.error:
        try:
            dest_ip = socket.gethostbyname(dest)
        except socket.gaierror:
            result["ret_code"] = EXIT_STATUS.ERROR_HOST_NOT_FOUND
            return result
    result["dest_ip"] = dest_ip

    # Open RAW socket to send ICMP packet
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                             socket.getprotobyname("icmp"))
    except socket.error, (errno, msg):
        if errno == 1:
            result["ret_code"] = EXIT_STATUS.ERROR_ROOT_REQUIRED
        else:
            result["ret_code"] = EXIT_STATUS.ERROR_CANT_OPEN_SOCKET
        return result

    # Send echo request and resive echo reply
    try:
        packet_id = random.randint(0, 65534)
        packet = _create_packet(packet_id, packet_size)
        while packet:
            sent = sock.sendto(packet, (dest_ip, 1))
            packet = packet[sent:]

        delay = _response_handler(sock, packet_id, time.time(), timeout)
        if delay:
            result["ret_code"] = EXIT_STATUS.SUCCESS
            result["rtt"] = delay
        else:
            result["ret_code"] = EXIT_STATUS.ERROR_TIMEOUT
    except socket.error:
        result["ret_code"] = EXIT_STATUS.ERROR_SOCKET_ERROR
    finally:
        sock.close()

    return result


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


def _create_packet(packet_id, packet_size):
    """Creates a new echo request packet based on the given id."""
    # Builds Dummy Header
    # Header is type (8), code (8), checksum (16), id (16), sequence (16)
    header = struct.pack("bbHHh", 8, 0, 0, packet_id, 1)
    data = packet_size * "Q"

    # Builds Real Header
    header = struct.pack("bbHHh", 8, 0,
                         socket.htons(_checksum(header + data)), packet_id, 1)
    return header + data


def _response_handler(sock, packet_id, sent_at, timeout):
    """Handles packet response, returns delay or None in case of timeout."""

    while time.time() < sent_at + timeout:
        ready = select.select([sock], [], [], timeout)
        received_at = time.time()
        if ready[0] == [] or received_at > sent_at + timeout:  # Timeout
            return

        rec_packet, addr = sock.recvfrom(1024)
        icmp_header = rec_packet[20:28]
        type_, code, checksum, rec_id, sequence = struct.unpack("bbHHh",
                                                                icmp_header)
        # why do we need to check packet_id
        if type_ == 0 and rec_id == packet_id:
            return (received_at - sent_at) * 1000

    return None
