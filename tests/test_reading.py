"""Unread jump, subscriptions/bookmarks and mark-read, with synthetic pages."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from phpbb_tui.board import Board, BoardError
from phpbb_tui.i18n import t


UNREAD_THREAD = """
<link rel="canonical" href="https://example.invalid/viewtopic.php?t=42&amp;start=15">
<h2 class="topic-title">Topic</h2>
<div id="p201" class="post has-profile bg2">
<a class="username">Alice</a><time>Mon</time><h3>Old</h3>
<div class="content">Read already.</div></div>
<a id="unread" class="anchor" data-url="./viewtopic.php?p=202#p202"></a>
<div id="p202" class="post has-profile bg1 unreadpost">
<a class="username">Bob</a><time>Tue</time><h3>New</h3>
<div class="content">First new one.</div></div>
<div id="p203" class="post has-profile bg2 unreadpost">
<a class="username">Carol</a><time>Wed</time><h3>Newer</h3>
<div class="content">Second new one.</div></div>
<div class="action-bar bar-bottom"></div>
Page 2 of 2
"""

SUBSCRIBED = """
<h2>Manage subscriptions</h2>
<ul class="topiclist cplist">
<li class="row bg1"><dl class="row-item forum_read"><dt>
<a href="./viewforum.php?f=7" class="forumtitle">Watched forum</a></dt></dl></li>
</ul>
<ul class="topiclist cplist">
<li class="row bg2"><dl class="row-item topic_unread"><dt>
<a href="./viewtopic.php?t=55" class="topictitle">Watched topic</a>
<div class="topic-poster">by <a class="username">Dora</a></div></dt></dl></li>
</ul>
"""

INDEX = """
<a href="./index.php?hash=abc123&amp;mark=forums&amp;mark_time=1700000000">Mark forums read</a>
<a href="./ucp.php?mode=logout&amp;sid=x">Logout</a>
"""


class ReadingTests(unittest.TestCase):

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Mock()
        self.session.headers = {}
        patcher = patch("phpbb_tui.board.requests.Session",
                        return_value=self.session)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.board = Board("https://example.invalid/",
                           Path(self.temp.name) / "c.txt")

    def answer(self, *pages: str) -> None:
        responses = []
        for page in pages:
            response = Mock()
            response.text = page
            responses.append(response)
        self.session.get.side_effect = responses

    def test_unread_view_finds_first_new_post_and_page_offset(self) -> None:
        self.answer(UNREAD_THREAD)
        thread = self.board.thread(42, ungelesen=True)
        _, kwargs = self.session.get.call_args
        self.assertEqual(kwargs["params"], {"t": 42, "view": "unread"})
        self.assertEqual(thread.start, 15)
        self.assertEqual(thread.erster_neuer, 1)
        self.assertEqual([p.unread for p in thread.posts], [False, True, True])
        # Paging continues from the page the board jumped to.
        self.assertEqual(self.board.page_params, {"t": 42, "start": 15})

    def test_normal_view_without_unread_posts(self) -> None:
        self.answer(UNREAD_THREAD.replace(" unreadpost", "").replace(
            '<a id="unread" class="anchor" data-url="./viewtopic.php?p=202#p202"></a>', ""))
        thread = self.board.thread(42, start=15)
        self.assertIsNone(thread.erster_neuer)
        self.assertFalse(any(p.unread for p in thread.posts))

    def test_subscriptions_list_topics_and_forums(self) -> None:
        self.answer(SUBSCRIBED)
        topics, forums, title, page, pages = self.board.ucp_themen("subscribed")
        _, kwargs = self.session.get.call_args
        self.assertEqual(kwargs["params"],
                         {"i": "ucp_main", "mode": "subscribed", "start": 0})
        self.assertEqual([(t.tid, t.title, t.unread) for t in topics],
                         [(55, "Watched topic", True)])
        self.assertEqual([(f.fid, f.name) for f in forums], [(7, "Watched forum")])
        self.assertTrue(title)
        self.assertEqual((page, pages), (1, 1))

    def test_mark_all_read_follows_the_hashed_link(self) -> None:
        self.answer(INDEX, "<p>Marked</p>")
        self.board.als_gelesen_markieren()
        first, second = self.session.get.call_args_list
        self.assertEqual(first.args[0], "https://example.invalid/index.php")
        self.assertEqual(second.args[0], "https://example.invalid/index.php")
        self.assertEqual(second.kwargs["params"],
                         {"hash": "abc123", "mark": "forums",
                          "mark_time": "1700000000"})

    def test_mark_forum_read_uses_topics_link(self) -> None:
        forum = ('<a href="./viewforum.php?hash=h1&amp;f=3&amp;mark=forums">x</a>'
                 '<a href="./viewforum.php?hash=h2&amp;f=3&amp;mark=topics'
                 '&amp;mark_time=5">y</a>')
        self.answer(forum, "<p>Marked</p>")
        self.board.als_gelesen_markieren(3)
        second = self.session.get.call_args_list[1]
        self.assertEqual(second.kwargs["params"],
                         {"hash": "h2", "f": "3", "mark": "topics", "mark_time": "5"})

    def test_mark_read_without_hash_link_is_refused(self) -> None:
        self.answer('<a href="./index.php?mark=forums">no hash</a>')
        with self.assertRaises(BoardError):
            self.board.als_gelesen_markieren()
        self.assertEqual(self.session.get.call_count, 1)


    def test_page_count_from_pagination_bar_without_page_text(self) -> None:
        page = ('<li class="row"><div class="pagination"><ul>'
                '<li><a href="./viewtopic.php?t=9&amp;start=15">2</a></li></ul></div></li>'
                '<div class="pagination"> 18 posts <ul>'
                '<li><a class="button" href="./viewtopic.php?t=7">1</a></li>'
                '<li class="active"><span>2</span></li>'
                '<li><a class="button" href="./viewtopic.php?t=7&amp;start=30">3</a></li>'
                '<li class="ellipsis"><span>…</span></li>'
                '<li><a class="button" href="./viewtopic.php?t=7&amp;start=90">7</a></li>'
                '</ul></div>')
        self.assertEqual(Board._pagination(page), (2, 7))
        self.assertEqual(Board._pagination("<p>nothing</p>"), (1, 1))

class UnreadTuiTests(unittest.TestCase):

    def test_opening_unread_topic_starts_at_first_new_post(self) -> None:
        from types import SimpleNamespace
        from phpbb_tui.ui import Oberflaeche

        calls = []
        b = SimpleNamespace(base="https://example.invalid", page_path="viewtopic.php",
                            page_params={}, page_html="")

        def fetch(tid, start, ungelesen=False):
            calls.append((start, ungelesen))
            return SimpleNamespace(title="Topic", page=2, pages=2, posts=[],
                                   start=15, erster_neuer=1 if ungelesen else None)

        b.thread = fetch
        screen = Mock()
        screen.getmaxyx.return_value = (24, 80)
        seen = []
        keys = iter([ord("R"), ord("q")])

        def key():
            seen.append(ui_pos())
            return next(keys)

        screen.getch.side_effect = key
        ui = Oberflaeche(screen, b, Mock())
        ui.warten = ui.kopf = ui.fuss = Mock()
        drawn = []
        ui._zeile = lambda y, text, attr=0, x=0: drawn.append((y, text))
        ui._thread_zeilen = Mock(return_value=[
            ("old", 0, 0), ("", 0, 0), ("new", 0, 1), ("text", 0, 1)])

        def ui_pos():
            first = [text for y, text in drawn if y == 1]
            drawn.clear()
            return first[0] if first else None

        ui.thread_zeigen(42, ungelesen=True)
        # First load jumps to the unread page, reload keeps that page normally.
        self.assertEqual(calls, [(0, True), (15, False)])
        self.assertEqual(seen, ["new", "old"])


class NextUnreadTests(unittest.TestCase):
    """`u` walks through unread topics without returning to the list."""

    def run_list(self, pages, thread_answers, keys):
        from types import SimpleNamespace
        from phpbb_tui.board import Topic
        from phpbb_tui.ui import Oberflaeche

        b = SimpleNamespace(base="https://example.invalid", page_path="search.php",
                            page_params={}, page_html="", username="me")
        loads = []

        def search(sid, start):
            loads.append(start)
            topics = [Topic(tid, f"T{tid}", unread=unread)
                      for tid, unread in pages(start, len(loads))]
            return topics, [], "Unread", 1, 1

        b.search = search
        screen = Mock()
        screen.getmaxyx.return_value = (24, 100)
        ui = Oberflaeche(screen, b, Mock())
        ui.warten = Mock()
        ui.liste = Mock(side_effect=[(k, 0) for k in keys])
        opened = []

        def thread(tid, ungelesen=False):
            opened.append((tid, ungelesen))
            return next(thread_answers)

        ui.thread_zeigen = thread
        with patch("phpbb_tui.ui.navigation", return_value={}):
            ui.themenliste(such_id="unreadposts")
        return opened, loads, ui

    def test_u_chains_unread_topics_then_reports_the_end(self):
        page = lambda start, n: [(1, True), (2, False), (3, True)]
        opened, loads, ui = self.run_list(page, iter([True, True]), ["u", "q"])
        self.assertEqual(opened, [(1, True), (3, True)])
        # Once through, a fresh load finds only visited topics: stop there.
        self.assertEqual(ui.meldung, t("keine_ungelesenen_mehr"))

    def test_leaving_a_topic_with_q_returns_to_the_reloaded_list(self):
        page = lambda start, n: [(1, True), (3, True)]
        opened, loads, _ = self.run_list(page, iter([False]), ["u", "q"])
        self.assertEqual(opened, [(1, True)])
        self.assertEqual(len(loads), 2)

    def test_search_lists_are_reloaded_before_giving_up(self):
        # Unread searches shrink as topics are read; new ones move up.
        page = lambda start, n: [(1, True)] if n == 1 else [(1, True), (5, True)]
        opened, _, _ = self.run_list(page, iter([True, False]), ["u", "q"])
        self.assertEqual(opened, [(1, True), (5, True)])


if __name__ == "__main__":
    unittest.main()
