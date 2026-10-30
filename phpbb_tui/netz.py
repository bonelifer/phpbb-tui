"""IPv4 zuerst: kaputte IPv6-Adressen von Boards nicht 30 Sekunden abwarten.

Manche Boards veröffentlichen eine IPv6-Adresse, die nicht antwortet.
Browser und curl merken das kaum, sie probieren beide Wege gleichzeitig
(„Happy Eyeballs“). urllib3 dagegen geht die Adressen der Reihe nach durch
und wartet bei jeder bis zum Zeitlimit. Bei duria.de kostete das jeden Start
30 Sekunden. Deshalb hier: erst IPv4, dann IPv6, jede Adresse nur einmal.
"""

from __future__ import annotations

import socket

import urllib3.util.connection as _verbindung

_original = _verbindung.create_connection


def _adressen(host: str, port: int, familie: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, familie, socket.SOCK_STREAM)
    except OSError:
        return []
    return list(dict.fromkeys(info[4][0] for info in infos))


def verbinden(address, *args, **kwargs):
    host, port = address
    ziele = (_adressen(host, port, socket.AF_INET)
             + _adressen(host, port, socket.AF_INET6))
    if not ziele:
        # Namensfehler soll urllib3 selbst melden, wie bisher.
        return _original(address, *args, **kwargs)
    fehler: OSError | None = None
    for ziel in ziele:
        try:
            # TLS prüft weiter den Hostnamen; hier geht nur die Adresse rein.
            return _original((ziel, port), *args, **kwargs)
        except OSError as e:
            fehler = e
    assert fehler is not None
    raise fehler


def einrichten() -> None:
    """Einmalig in urllib3 einhängen (wirkt für den ganzen Prozess)."""
    _verbindung.create_connection = verbinden
