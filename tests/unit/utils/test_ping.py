# Copyright 2017: GoDaddy Inc.

import socket
import struct

import mock

from netmet.utils import ping
from tests.unit import test


class PingTestCase(test.TestCase):

    @mock.patch("netmet.utils.ping.socket")
    def test_init_created_socket_success_ip(self, mock_socket):
        mock_socket.inet_pton.return_value = "1.1.1.1"
        p = ping.Ping("1.1.1.1")
        self.assertEqual(0, p.ret_code)
        self.assertEqual("1.1.1.1", p.dest)
        self.assertEqual(1, p.timeout)
        self.assertEqual(55, p.packet_size)
        self.assertEqual("1.1.1.1", p.dest_ip)
        self.assertEqual(mock_socket.socket.return_value, p.sock)

    @mock.patch("netmet.utils.ping.socket.inet_pton")
    @mock.patch("netmet.utils.ping.socket.gethostbyname")
    @mock.patch("netmet.utils.ping.socket.socket")
    def test_init_created_socket_success_host(
            self, mock_socket, mock_gethostbyname, mock_inet_pton):
        mock_inet_pton.side_effect = socket.error
        mock_gethostbyname.return_value = "2.2.2.2"
        p = ping.Ping("host", packet_size=100, timeout=5)
        self.assertEqual(0, p.ret_code)
        self.assertEqual("host", p.dest)
        self.assertEqual(5, p.timeout)
        self.assertEqual(100, p.packet_size)
        self.assertEqual("2.2.2.2", p.dest_ip)
        self.assertEqual(mock_socket.return_value, p.sock)

    @mock.patch("netmet.utils.ping.socket.inet_pton")
    @mock.patch("netmet.utils.ping.socket.gethostbyname")
    def test_init_created_socket_failed_not_found(
            self, mock_gethostbyname, mock_inet_pton):
        mock_inet_pton.side_effect = socket.error
        mock_gethostbyname.side_effect = socket.gaierror
        p = ping.Ping("host")
        self.assertEqual(ping.EXIT_STATUS.ERROR_HOST_NOT_FOUND, p.ret_code)
        self.assertEqual(None, p.sock)

    def test_ping(self):
        pass

    def test_ping_recreate_socket(self):
        pass

    @mock.patch("netmet.utils.ping.socket")
    def test_create_packet(self, mock_socket):
        p = ping.Ping("127.0.0.1")
        packet = p._create_packet(10)
        self.assertEqual(8 + 55, len(packet))
        type_, code, checksum, id_, seq = struct.unpack("bbHHh", packet[:8])
        self.assertEqual(8, type_)
        self.assertEqual(0, code)
        self.assertEqual(10, id_)
        self.assertEqual(1, seq)

        p = ping.Ping("127.0.0.1", packet_size=100)
        packet = p._create_packet(20)
        self.assertEqual(8 + 100, len(packet))
        type_, code, checksum, id_, seq = struct.unpack("bbHHh", packet[:8])
        self.assertEqual(8, type_)
        self.assertEqual(0, code)
        self.assertEqual(20, id_)
        self.assertEqual(1, seq)

    @mock.patch("netmet.utils.ping.socket")
    @mock.patch("netmet.utils.ping.select")
    @mock.patch("netmet.utils.ping.monotonic.monotonic")
    def test_handle_response(self, mock_monotonic, mock_select, mock_socket):
        p = ping.Ping("127.0.0.1")
        id_ = 10
        resp = "_" * 20   # NOTE(boris-42) We don't check header
        # NOTE(boris-42) Check checksum (fix me please)
        resp += struct.pack("bbHHh", 0, 0, 1, id_, 1) + "Q" * p.packet_size

        p.sock.recvfrom.return_value = (resp, "addr")
        mock_select.select.return_value == [[p.sock], [], []]
        mock_monotonic.side_effect = [0.1, 0.2, 0.25]
        self.assertEqual(150.0, p._response_handler(id_, 0.1))

    @mock.patch("netmet.utils.ping.socket")
    @mock.patch("netmet.utils.ping.select")
    @mock.patch("netmet.utils.ping.monotonic.monotonic")
    def test_handle_response_timeout(self, mock_monotonic, mock_select,
                                     mock_socket):
        p = ping.Ping("127.0.0.1")
        mock_monotonic.side_effect = [2]
        self.assertEqual(None, p._response_handler(10, 0.1))
