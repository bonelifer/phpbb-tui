"""Preserve phpBB quote attribution and actual HTML quotation boundaries."""

import unittest

from phpbb_tui.markup import html_to_text


class QuoteTextTests(unittest.TestCase):
    """Check shared display conversion without changing stored post content."""

    def test_english_attribution_is_not_given_a_german_suffix(self):
        self.assertEqual(html_to_text(
            '<blockquote><div><cite>Alice wrote:</cite>Quoted text</div>'
            '</blockquote>Reply text'),
            '│ Alice wrote:\n│ Quoted text\nReply text')

    def test_german_attribution_is_not_duplicated(self):
        self.assertEqual(html_to_text(
            '<blockquote><cite>Alice schrieb:</cite>Zitat</blockquote>'
            'Antwort'),
            '│ Alice schrieb:\n│ Zitat\nAntwort')

    def test_blank_line_inside_quote_does_not_end_quotation(self):
        self.assertEqual(html_to_text(
            '<blockquote><cite>Alice wrote:</cite>First<br><br>Second'
            '</blockquote>Reply'),
            '│ Alice wrote:\n│ First\n\n│ Second\nReply')

    def test_nested_quote_restores_the_outer_quote_depth(self):
        self.assertEqual(html_to_text(
            '<blockquote><cite>Alice wrote:</cite>Outer'
            '<blockquote><cite>Bob wrote:</cite>Inner</blockquote>'
            'Outer again</blockquote>Reply'),
            '│ Alice wrote:\n│ Outer\n│ │ Bob wrote:\n│ │ Inner\n'
            '│ Outer again\nReply')

    def test_anonymous_quote_uses_its_block_boundary(self):
        self.assertEqual(html_to_text(
            '<blockquote>Quoted</blockquote>Reply'), '│ Quoted\nReply')

    def test_nonquote_paragraphs_keep_their_existing_output(self):
        self.assertEqual(html_to_text('<p>First</p><p>Second</p>'),
                         'First\nSecond')
