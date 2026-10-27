"""Keep filenames for text and image-only attachment links."""

import unittest

from phpbb_tui.board import Board


class AttachmentNameTests(unittest.TestCase):
    """Exercise shared attachment parsing with phpBB-style HTML fragments."""

    def test_thumbnail_image_alt_supplies_filename(self):
        block = '''<dl class="thumbnail"><dt>
            <a href="./download/file.php?id=66&amp;mode=view">
            <img src="./download/file.php?id=66&amp;t=1"
                 alt="phpBB Bear Mascot in Blue Polo.png"></a></dt></dl>'''
        item, = Board._parse_anhaenge(block)
        self.assertEqual(item.name, "phpBB Bear Mascot in Blue Polo.png")
        self.assertEqual(item.aid, 66)
        self.assertTrue(item.bild)

    def test_alt_filename_decodes_entities_and_preserves_unicode(self):
        block = '''<dl class="thumbnail">
            <a href="./download/file.php?id=7"><img
            alt="café &amp; tea.png"></a></dl>'''
        self.assertEqual(Board._parse_anhaenge(block)[0].name,
                         "café & tea.png")

    def test_regular_link_text_takes_precedence(self):
        block = '''<dl class="file"><a href="./download/file.php?id=7">
            report &amp; notes.txt</a><img alt="Download"> (2 KiB)</dl>'''
        item, = Board._parse_anhaenge(block)
        self.assertEqual(item.name, "report & notes.txt")
        self.assertEqual(item.groesse, "2 KiB")

    def test_empty_link_and_alt_use_existing_id_fallback(self):
        block = '''<dl class="thumbnail"><a href="./download/file.php?id=7">
            <img alt=" "></a></dl>'''
        self.assertEqual(Board._parse_anhaenge(block)[0].name, "Datei 7")

    def test_duplicate_image_links_still_return_one_attachment(self):
        block = '''<dl class="thumbnail"><a href="./download/file.php?id=7">
            <img src="./download/file.php?id=7" alt="bear.png"></a></dl>'''
        self.assertEqual(len(Board._parse_anhaenge(block + block)), 1)
