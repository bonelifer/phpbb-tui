"""Resolve TUI page offsets from the board's own pagination links."""

from urllib.parse import parse_qs, urljoin, urlsplit

from .cli import Pagination


def navigation(board, current: int, pages: int = 1) -> dict[str, int]:
    """Return adjacent/last offsets; omit absent or conflicting targets.

    Only numeric links inside pagination containers, on the same board and
    resource, are accepted. No topics/posts/messages-per-page guess is used.
    """
    parser = Pagination()
    parser.feed(getattr(board, "page_html", ""))
    base = urlsplit(board.base + "/" + getattr(board, "page_path", ""))
    params = dict(getattr(board, "page_params", {}))
    folder = params.pop("folder", None)
    if folder is not None:
        params["f"] = {"inbox": 0, "sentbox": -1, "outbox": -2}.get(
            folder, folder)
    active = set(parser.current_pages)
    if len(active) == 1:
        current = active.pop()
    offsets = {}
    conflicts = set()
    for label, href in parser.links:
        if not label.isascii() or not label.isdecimal() or int(label) < 1:
            continue
        try:
            url = urlsplit(urljoin(base.geturl(), href))
            query = parse_qs(url.query)
        except ValueError:
            continue
        if (url.scheme, url.netloc, url.path) != (
                base.scheme, base.netloc, base.path):
            continue
        if any(query.get(key) != [str(value)] for key, value in params.items()
               if key in ("f", "t", "search_id", "keywords")):
            continue
        starts = query.get("start", ["0"])
        if (len(starts) != 1 or not starts[0].isascii()
                or not starts[0].isdecimal()):
            continue
        number, offset = int(label), int(starts[0])
        if number in offsets and offsets[number] != offset:
            conflicts.add(number)
        offsets[number] = offset
    for number in conflicts:
        offsets.pop(number, None)
    result = {}
    for key, number in (("n", current + 1), ("p", current - 1)):
        if number in offsets:
            start = params.get("start", 0)
            offset = offsets[number]
            if (key == "n" and offset > start) or (
                    key == "p" and offset < start):
                result[key] = offset
    if pages in offsets:
        result["last"] = offsets[pages]
    return result
