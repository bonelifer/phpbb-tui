"""Keep keyword search responses compatible with the shared topic parser."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from phpbb_tui.board import Board


class KeywordSearchTests(unittest.TestCase):
    """phpBB defaults to post results unless topic results are requested."""

    def test_keyword_search_requests_topics_and_preserves_offset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("phpbb_tui.board.requests.Session"):
                board = Board("https://example.invalid",
                              Path(directory) / "cookies.txt")
            # A post-result page has no topictitle links for _parse_topics.
            topic_page = (
                '<h2 class="searchresults-title">Search</h2>'
                '<li class="row"><a href="viewtopic.php?t=42" '
                'class="topictitle">Café</a></li>')
            board.get = Mock(side_effect=lambda path, **params:
                             topic_page if params.get("sr") == "topics"
                             else '<div class="postbody">Café</div>')
            topics, subforums, title, page, pages = board.suche(
                "café", start=7)
            self.assertEqual([(t.tid, t.title) for t in topics],
                             [(42, "Café")])
            self.assertEqual(subforums, [])
            self.assertEqual(title, "Suche: café")
            self.assertEqual((page, pages), (1, 1))
            board.get.assert_called_once_with(
                "search.php", keywords="café", sr="topics", start=7)
