"""Classify a single final TUI submission without suggesting unsafe retries."""

import re

import requests

from .board import Board, Entwurf
from .i18n import t
from .posting import submission_error


def submit(board: Board, form: Entwurf, subject: str,
           message: str) -> tuple[str, str]:
    """Return success, rejected, or uncertain plus a localized explanation.

    Final POSTs are attempted once. Only positive confirmations establish
    success; lost or unrecognized responses must be checked on the board.
    This path does not save raw diagnostic HTML or echo network exceptions.
    """
    try:
        page = board.submit(form, subject, message)
    except Exception as cause:
        error = submission_error(cause)
        network = (cause if isinstance(cause, requests.RequestException)
                   else cause.__cause__)
        response = getattr(network, "response", None)
        redirected = bool(response is not None and response.history)
        if error.status == 10 or redirected:
            return "uncertain", t("senden_unklar")
        key = ("senden_keine_verbindung" if error.status == 9
               else "senden_abgelehnt")
        return "rejected", t(key)

    try:
        error = board._fehlertext(page)
        if error:
            return "rejected", error
        if re.search(r'<form\b[^>]*\bid="postform"', page):
            return "rejected", t("senden_formular")
        if form.ziel == "ucp.php":
            if board.pm_submission_id(page) is not None:
                return "success", t("pm_gesendet_kurz")
        else:
            success, explanation = board.submission_success(page)
            confirmed = (board._redirected_post_id(page)
                         or re.search(r'\bid="message"', page)
                         or re.search(r'<meta\b[^>]*http-equiv="refresh"',
                                      page, re.I))
            if success and confirmed:
                return "success", explanation
    except Exception:
        # Failure while interpreting a response cannot prove it was rejected.
        pass
    return "uncertain", t("senden_unklar")
