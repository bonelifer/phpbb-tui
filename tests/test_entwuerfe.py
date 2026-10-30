"""Written text survives failures and comes back at the same target."""

import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from phpbb_tui import entwuerfe
from phpbb_tui.board import Board, Entwurf
from phpbb_tui.i18n import t
from phpbb_tui.ui import Oberflaeche


class StoreTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def test_round_trip_is_private_and_per_target(self):
        reply = ("duria", "posting.php", {"mode": "reply", "t": 7})
        other = ("duria", "posting.php", {"mode": "reply", "t": 8})
        datei = entwuerfe.sichern(*reply, "Re: Hallo", "Text\n\nZweiter Absatz",
                                  ordner=self.dir)
        self.assertEqual(stat.S_IMODE(datei.stat().st_mode), 0o600)
        self.assertEqual(entwuerfe.laden(*reply, ordner=self.dir),
                         ("Re: Hallo", "Text\n\nZweiter Absatz"))
        self.assertIsNone(entwuerfe.laden(*other, ordner=self.dir))
        # Parameter order and value types do not change the target.
        self.assertEqual(
            entwuerfe.pfad("duria", "posting.php", {"t": "7", "mode": "reply"},
                           self.dir), datei)
        entwuerfe.loeschen(*reply, ordner=self.dir)
        self.assertIsNone(entwuerfe.laden(*reply, ordner=self.dir))
        entwuerfe.loeschen(*reply, ordner=self.dir)      # missing is fine

    def test_boards_do_not_share_drafts(self):
        entwuerfe.sichern("a", "posting.php", {"t": 1}, "S", "x", ordner=self.dir)
        self.assertIsNone(entwuerfe.laden("b", "posting.php", {"t": 1},
                                          ordner=self.dir))

    def test_empty_draft_counts_as_none(self):
        entwuerfe.sichern("a", "posting.php", {}, "S", "  ", ordner=self.dir)
        self.assertIsNone(entwuerfe.laden("a", "posting.php", {}, ordner=self.dir))


class ComposeTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name) / "drafts"
        drafts = patch("phpbb_tui.entwuerfe.ORDNER", self.dir)
        drafts.start()
        self.addCleanup(drafts.stop)
        with patch("phpbb_tui.board.requests.Session", return_value=Mock(headers={})):
            self.board = Board("https://example.invalid/forum",
                               Path(self.temp.name) / "c.txt", "test")
        self.board.preview_text = Mock(return_value="Preview")
        self.form = Entwurf({"subject": "Re: Topic", "message": ""},
                            "posting.php", {"mode": "reply", "t": 7})

    def ui(self, preview_keys, confirm=False):
        ui = Oberflaeche(Mock(), self.board, Mock())
        ui.scr.getmaxyx.return_value = (24, 100)
        ui._editor = Mock(return_value=("Re: Topic", "My answer"))
        ui.warten = Mock()
        ui.bestaetigen = Mock(return_value=confirm)
        ui.seite_zeigen = Mock(side_effect=preview_keys)
        return ui

    def saved(self):
        return entwuerfe.laden("test", "posting.php", {"mode": "reply", "t": 7})

    def test_success_removes_the_draft(self):
        ui = self.ui(["a"])
        with patch("phpbb_tui.ui.tui_submission.submit",
                   return_value=("success", "ok")):
            self.board.submit = Mock(return_value="preview")
            self.assertTrue(ui._verfassen(self.form))
        self.assertIsNone(self.saved())

    def test_uncertain_and_rejected_keep_the_draft(self):
        for outcome, keys in (("uncertain", ["a", "q"]), ("rejected", ["a"])):
            with self.subTest(outcome=outcome):
                ui = self.ui(keys)
                with patch("phpbb_tui.ui.tui_submission.submit",
                           return_value=(outcome, "hm")):
                    self.board.submit = Mock(return_value="preview")
                    self.assertFalse(ui._verfassen(self.form))
                self.assertEqual(self.saved(), ("Re: Topic", "My answer"))

    def test_next_attempt_restores_text_with_a_note(self):
        entwuerfe.sichern("test", "posting.php", {"mode": "reply", "t": 7},
                          "Re: Topic", "Earlier text")
        ui = self.ui(["q"], confirm=True)
        self.board.submit = Mock(return_value="preview")
        ui._verfassen(self.form)
        betreff, vorlage, hinweis = ui._editor.call_args.args
        self.assertEqual((betreff, vorlage, hinweis),
                         ("Re: Topic", "Earlier text", t("entwurf_zurueck")))

    def test_q_in_preview_asks_and_no_keeps_composing(self):
        ui = self.ui(["q", "q"])
        ui.bestaetigen = Mock(side_effect=[False, True])
        self.board.submit = Mock(return_value="preview")
        self.assertFalse(ui._verfassen(self.form))
        self.assertEqual(ui.bestaetigen.call_count, 2)
        self.assertEqual(ui.seite_zeigen.call_count, 2)
        # Discarding on purpose removes the draft.
        self.assertIsNone(self.saved())

    def test_editor_closed_empty_discards(self):
        entwuerfe.sichern("test", "posting.php", {"mode": "reply", "t": 7},
                          "Re: Topic", "Old")
        ui = self.ui([])
        ui._editor = Mock(return_value=("Re: Topic", ""))
        self.assertFalse(ui._verfassen(self.form))
        self.assertIsNone(self.saved())


if __name__ == "__main__":
    unittest.main()
