"""IPv4 first, IPv6 as fallback, each address tried once."""

import socket
import unittest
from unittest.mock import patch

from phpbb_tui import netz


def infos(*addresses):
    return [(socket.AF_INET6 if ":" in a else socket.AF_INET,
             socket.SOCK_STREAM, 6, "", (a, 443)) for a in addresses]


class NetzTests(unittest.TestCase):

    def resolve(self, host, port, family, kind):
        table = {socket.AF_INET: infos("192.0.2.1"),
                 socket.AF_INET6: infos("2001:db8::1")}
        return table[family]

    def test_ipv4_is_tried_before_ipv6(self):
        tried = []
        with patch("socket.getaddrinfo", side_effect=self.resolve), \
             patch.object(netz, "_original",
                          side_effect=lambda a, *x, **k: tried.append(a[0]) or "sock"):
            self.assertEqual(netz.verbinden(("board.example", 443), 30), "sock")
        self.assertEqual(tried, ["192.0.2.1"])

    def test_falls_back_to_ipv6_when_ipv4_fails(self):
        tried = []

        def connect(address, *args, **kwargs):
            tried.append(address[0])
            if address[0] == "192.0.2.1":
                raise TimeoutError("no answer")
            return "sock6"

        with patch("socket.getaddrinfo", side_effect=self.resolve), \
             patch.object(netz, "_original", side_effect=connect):
            self.assertEqual(netz.verbinden(("board.example", 443), 30), "sock6")
        self.assertEqual(tried, ["192.0.2.1", "2001:db8::1"])

    def test_last_error_is_raised_when_nothing_answers(self):
        with patch("socket.getaddrinfo", side_effect=self.resolve), \
             patch.object(netz, "_original", side_effect=ConnectionRefusedError()):
            with self.assertRaises(ConnectionRefusedError):
                netz.verbinden(("board.example", 443), 30)

    def test_unresolvable_host_is_left_to_urllib3(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror()), \
             patch.object(netz, "_original", return_value="orig") as original:
            self.assertEqual(netz.verbinden(("nowhere.invalid", 443), 30), "orig")
        original.assert_called_once_with(("nowhere.invalid", 443), 30)


if __name__ == "__main__":
    unittest.main()
