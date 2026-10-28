"""Resolve topic forum IDs from the forum breadcrumb hierarchy."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from phpbb_tui.board import Board


class TopicForumIdTests(unittest.TestCase):
    """Exercise the shared thread parser without network or saved sessions."""

    def parse(self, markup):
        with tempfile.TemporaryDirectory() as directory:
            board = Board("https://example.invalid",
                          Path(directory) / "cookies")
            with patch.object(board, "get", return_value=markup):
                return board.thread(42)

    def test_deepest_breadcrumb_beats_category_and_unrelated_links(self):
        thread = self.parse('''<a href="viewforum.php?f=99">Unrelated</a>
            <li class="breadcrumbs">
            <a class="crumb" href="./viewforum.php?f=3">Category</a>
            <span class="crumb"><a href="./viewforum.php?f=6">Forum</a></span>
            </li><a href="viewforum.php?f=88">Jumpbox</a>''')
        self.assertEqual(thread.forum_id, 6)

    def test_nested_forum_with_extra_query_parameters(self):
        thread = self.parse('''<li class="breadcrumbs extra">
            <a href="./viewforum.php?f=3">Category</a>
            <a href="./viewforum.php?f=6">Parent</a>
            <a href="./viewforum.php?start=0&amp;f=12&amp;sid=x">Child</a>
            </li>''')
        self.assertEqual(thread.forum_id, 12)

    def test_footer_breadcrumb_without_forums_does_not_erase_header(self):
        thread = self.parse('''<li class="breadcrumbs">
            <a href="./viewforum.php?f=6">Forum</a></li>
            <li class="breadcrumbs"><a href="index.php">Home</a></li>''')
        self.assertEqual(thread.forum_id, 6)

    def test_legacy_markup_keeps_first_forum_link_fallback(self):
        self.assertEqual(self.parse(
            '<a href="viewforum.php?f=7">Forum</a>').forum_id, 7)

    def test_missing_forum_keeps_zero_default(self):
        self.assertEqual(self.parse('<h2>Topic</h2>').forum_id, 0)
