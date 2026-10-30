"""TUI navigation follows scoped server offsets instead of fixed page sizes."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from phpbb_tui.tui_pagination import navigation
from phpbb_tui.ui import Oberflaeche


def board(path='viewforum.php', params=None, links=''):
    """Supply only the response metadata used by navigation."""
    return SimpleNamespace(base='https://example.invalid/forum',
                           page_path=path, page_params=params or {'f': 2},
                           page_html='<div class="pagination">' + links
                           + '</div>')


def link(page, path='viewforum.php', query='f=2', start=None):
    """Render synthetic phpBB numeric navigation."""
    offset = '' if start is None else f'&amp;start={start}'
    return f'<a href="./{path}?{query}{offset}">{page}</a>'


class NavigationTests(unittest.TestCase):
    def test_nonstandard_offsets_and_page_one_without_start(self):
        b = board(params={'f': 2, 'start': 7}, links=(
            link(1) + link(3, start=19) + link(8, start=73)))
        self.assertEqual(navigation(b, 2, 8), {'n': 19, 'p': 0, 'last': 73})

    def test_no_links_never_guesses_an_offset(self):
        self.assertEqual(navigation(board(), 1, 5), {})

    def test_unrelated_inline_and_external_links_are_ignored(self):
        b = board(links=link(2, 'viewtopic.php', 't=3', 17)
                  + link(2, query='f=9', start=22)
                  + '<a href="https://other.invalid/forum/viewforum.php?'
                    'f=2&amp;start=9">2</a>')
        b.page_html += link(2, start=12)
        self.assertEqual(navigation(b, 1, 2), {})

    def test_conflicting_or_invalid_offsets_are_not_used(self):
        for links in (link(2, start=7) + link(2, start=9),
                      link(2, start=-1), link(2, start=0),
                      link(2, start='7&amp;start=9')):
            with self.subTest(links=links):
                self.assertNotIn('n', navigation(board(links=links), 1, 2))

    def test_pm_navigation_uses_numeric_folder_id(self):
        for name, fid in [('inbox', 0), ('sentbox', -1), ('outbox', -2)]:
            b = board('ucp.php', {'i': 'pm', 'folder': name, 'start': 0},
                      link(2, 'ucp.php', f'i=pm&amp;f={fid}', 7))
            self.assertEqual(navigation(b, 1, 2)['n'], 7)

    def test_search_modes_preserve_query_scope(self):
        for params, query in [({'search_id': 'unreadposts'},
                               'search_id=unreadposts'),
                              ({'keywords': 'two words'},
                               'keywords=two+words')]:
            b = board('search.php', params,
                      link(2, 'search.php', query, 11))
            self.assertEqual(navigation(b, 1, 2)['n'], 11)

    def test_active_page_marker_supports_localized_page_count(self):
        b = board(params={'f': 2, 'start': 7}, links=(
            '<li class="active"><span>2</span></li>' + link(1)
            + link(3, start=19)))
        self.assertEqual(navigation(b, 1, 3), {'n': 19, 'p': 0, 'last': 19})

    def test_forum_and_search_tui_next_previous_use_server_offsets(self):
        for mode in ('forum', 'search', 'keywords'):
            b = board()
            calls = []

            def fetch(*args):
                start = args[-1]
                calls.append(start)
                b.page_params = {'f': 2, 'start': start}
                b.page_html = '<div class="pagination">' + (
                    link(2, start=7) if start == 0 else link(1)) + '</div>'
                return [], [], 'Topics', 1 if start == 0 else 2, 2

            b.topics = b.search = b.suche = fetch
            ui = Oberflaeche(Mock(), b, Mock())
            ui.warten = Mock()
            ui.liste = Mock(side_effect=[('n', 0), ('p', 0), ('q', 0)])
            ui.themenliste(fid=2 if mode == 'forum' else None,
                           such_id='unreadposts',
                           worte='words' if mode == 'keywords' else '')
            self.assertEqual(calls, [0, 7, 0])

    def test_thread_tui_navigation_and_after_reply_use_server_offsets(self):
        for keys, expected in [(["n", "p", "q"], [0, 7, 0]),
                               (["r", "q"], [0, 77])]:
            b = board("viewtopic.php")
            calls = []

            def fetch(tid, start):
                calls.append(start)
                b.page_params = {"t": tid, "start": start}
                b.page_html = '<div class="pagination">' + (
                    link(2, "viewtopic.php", "t=42", 7)
                    + link(9, "viewtopic.php", "t=42", 77)
                    if start == 0 else link(1, "viewtopic.php", "t=42"))
                b.page_html += '</div>'
                return SimpleNamespace(title="Topic", page=1 if start == 0
                                       else 2, pages=9, posts=[])

            b.thread = fetch
            screen = Mock()
            screen.getmaxyx.return_value = (24, 80)
            screen.getch.side_effect = [ord(key) for key in keys]
            ui = Oberflaeche(screen, b, Mock())
            ui.warten = ui.kopf = ui.fuss = ui._zeile = Mock()
            ui._thread_zeilen = Mock(return_value=[])
            ui.schreiben = Mock(return_value=True)
            ui.thread_zeigen(42)
            self.assertEqual(calls, expected)

    def test_pm_tui_navigation_uses_small_page_size(self):
        b = board('ucp.php')
        calls = []

        def fetch(folder, start):
            calls.append(start)
            b.page_params = {'folder': folder, 'start': start}
            b.page_html = '<div class="pagination">' + (
                link(2, 'ucp.php', 'f=0', 7) if start == 0
                else link(1, 'ucp.php', 'f=0')) + '</div>'
            return [], 'Inbox', '', 1 if start == 0 else 2, 2

        b.pm_liste = fetch
        ui = Oberflaeche(Mock(), b, Mock())
        ui.warten = Mock()
        ui.liste = Mock(side_effect=[('n', 0), ('p', 0), ('q', 0)])
        ui.postfach()
        self.assertEqual(calls, [0, 7, 0])
