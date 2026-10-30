"""Entwürfe sichern, damit kein geschriebener Text verloren geht.

Gesichert wird jedes Mal, wenn der Editor zugeht. Gelöscht wird erst, wenn
das Forum den Beitrag eindeutig bestätigt oder der Nutzer ausdrücklich
verwirft. Ein Absturz, eine Ablehnung oder ein unklares Ergebnis lassen den
Text also liegen; beim nächsten Schreiben an dieselbe Stelle ist er wieder da.

Ein Entwurf gehört zu seinem Ziel: Board, Formular und die Parameter, mit
denen abgeschickt wird. Antwort und Zitat im selben Thema teilen sich das
Ziel (beide gehen als `mode=reply` raus), das ist gewollt.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .config import STATE_DIR

ORDNER = STATE_DIR / "entwuerfe"


def _ziel(board: str, ziel: str, params: dict) -> str:
    teile = {k: str(v) for k, v in sorted(params.items())}
    return json.dumps([board, ziel, teile], ensure_ascii=False)


def pfad(board: str, ziel: str, params: dict, ordner: Path | None = None) -> Path:
    kennung = hashlib.sha1(_ziel(board, ziel, params).encode()).hexdigest()[:16]
    return (ordner or ORDNER) / f"{kennung}.md"


def sichern(board: str, ziel: str, params: dict, betreff: str, text: str,
            ordner: Path | None = None) -> Path:
    datei = pfad(board, ziel, params, ordner)
    datei.parent.mkdir(parents=True, exist_ok=True)
    beschreibung = " ".join(f"{k}={v}" for k, v in sorted(params.items()))
    inhalt = (f"<!-- phpbb-tui: {board} {ziel} {beschreibung} -->\n"
              f"# {betreff}\n\n{text}\n")
    neu = datei.with_suffix(".tmp")
    # Erst vollständig schreiben, dann umbenennen: ein Absturz mitten im
    # Schreiben darf den vorigen Stand nicht zerstören.
    fd = os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(inhalt)
    os.replace(neu, datei)
    return datei


def laden(board: str, ziel: str, params: dict,
          ordner: Path | None = None) -> tuple[str, str] | None:
    datei = pfad(board, ziel, params, ordner)
    try:
        zeilen = datei.read_text(encoding="utf-8").split("\n")
    except OSError:
        return None
    if zeilen and zeilen[0].startswith("<!-- phpbb-tui:"):
        zeilen = zeilen[1:]
    betreff = ""
    if zeilen and zeilen[0].startswith("# "):
        betreff, zeilen = zeilen[0][2:].strip(), zeilen[1:]
    text = "\n".join(zeilen).strip()
    return (betreff, text) if text else None


def loeschen(board: str, ziel: str, params: dict,
             ordner: Path | None = None) -> None:
    pfad(board, ziel, params, ordner).unlink(missing_ok=True)

