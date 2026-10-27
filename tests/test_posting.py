"""Test unattended posting, shared form handling, and uncertain outcomes."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from phpbb_tui import __main__ as entry
from phpbb_tui import config
from phpbb_tui.board import Board
from phpbb_tui.i18n import t


TOKEN = "SYNTHETIC_FORM_SECRET"
FORM = f'''<form id="postform">
<input type="hidden" name="form_token" value="{TOKEN}">
<input type="hidden" name="creation_time" value="1">
<input type="text" name="subject" value="Original subject">
<textarea name="message">[quote="Alice"]Original text[/quote]</textarea>
<input type="submit" name="post" value="Submit"></form>'''
SUCCESS = (
    '<div id="message">Your message has been successfully posted.</div>'
    '<meta http-equiv="refresh" content="3; url=./viewtopic.php?'
    't=42&amp;p=101&amp;sid=SECRET#p101">')


class PostingTests(unittest.TestCase):
    """Run real CLI/Board code with mocked requests and temporary state."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = config.Config(
            [config.BoardConfig("Example", "https://example.invalid")],
            self.root, "browser")
        self.session = Mock(headers={})
        self.session.get.side_effect = lambda url, **params: Mock(
            text='<a href="ucp.php?mode=logout">Logout</a>'
            if url.endswith("index.php") else FORM)
        self.session.post.return_value.text = SUCCESS
        self.stdin = io.StringIO("")
        for manager in (
            patch.object(config, "laden", return_value=self.cfg),
            patch.object(config, "STATE_DIR", self.root),
            patch("phpbb_tui.board.requests.Session",
                  return_value=self.session),
            patch("builtins.input", side_effect=AssertionError("Prompt")),
            patch("getpass.getpass", side_effect=AssertionError("Password")),
            patch("sys.stdin", self.stdin),
        ):
            manager.start()
            self.addCleanup(manager.stop)

    def invoke(self, *args: str) -> tuple[int, dict]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            status = entry.main([*args, "--json"])
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn(TOKEN, stdout.getvalue())
        self.assertNotIn("sid=SECRET", stdout.getvalue())
        return status, json.loads(stdout.getvalue())

    def post(self, *extra: str) -> tuple[int, dict]:
        return self.invoke("post", "Example", "--forum", "2",
                           "--subject", "A subject", "--body", "**Café**",
                           *extra)

    def test_post_reuses_form_conversion_and_submission(self) -> None:
        status, data = self.post()
        self.assertEqual(status, 0)
        self.assertTrue(data["submitted"])
        self.assertEqual((data["topic_id"], data["post_id"]), (42, 101))
        self.assertEqual(data["url"],
                         "https://example.invalid/viewtopic.php?p=101#p101")
        self.session.post.assert_called_once()
        kwargs = self.session.post.call_args.kwargs
        self.assertEqual(kwargs["params"], {"mode": "post", "f": 2})
        self.assertEqual(kwargs["data"]["form_token"], TOKEN)
        self.assertEqual(kwargs["data"]["message"], "[b]Café[/b]")
        self.assertEqual(kwargs["data"]["subject"], "A subject")

    def test_redirected_topic_returns_verified_ids(self) -> None:
        self.session.post.return_value = Mock(
            text='<div id="p101" class="post bg2">Stored</div>',
            history=[Mock(status_code=302)],
            url="https://example.invalid/viewtopic.php?t=42")
        status, data = self.post()
        self.assertEqual(status, 0)
        self.assertEqual((data["topic_id"], data["post_id"]), (42, 101))
        self.assertEqual(data["url"],
                         "https://example.invalid/viewtopic.php?p=101#p101")

    def test_unexpected_returned_target_is_uncertain(self) -> None:
        self.session.post.return_value = Mock(
            text='<div id="p101" class="post bg2">Stored</div>',
            history=[Mock(status_code=302)],
            url="https://example.invalid/viewtopic.php?t=99#p101")
        self.assertEqual(self.invoke(
            "reply", "Example", "--topic", "42", "--body", "Reply")[0], 10)

    def test_reply_preserves_form_subject(self) -> None:
        status, data = self.invoke("reply", "Example", "--topic", "42",
                                   "--body", "A reply")
        self.assertEqual(status, 0)
        self.assertEqual(data["subject"], "Original subject")
        self.assertEqual(self.session.post.call_args.kwargs["params"],
                         {"mode": "reply", "t": 42})

    def test_quote_uses_phpbb_form_and_existing_converters(self) -> None:
        status, _ = self.invoke("reply", "Example", "--topic", "42",
                                "--quote", "101", "--body", "My response")
        self.assertEqual(status, 0)
        self.assertEqual(self.session.get.call_args.kwargs["params"],
                         {"mode": "quote", "t": 42, "p": 101})
        message = self.session.post.call_args.kwargs["data"]["message"]
        self.assertIn("Alice", message)
        self.assertIn("Original text", message)
        self.assertIn("My response", message)

    def test_edit_replaces_entire_body_and_preserves_subject(self) -> None:
        status, _ = self.invoke("edit", "Example", "--post", "101",
                                "--body", "Replacement")
        self.assertEqual(status, 0)
        fields = self.session.post.call_args.kwargs["data"]
        self.assertEqual(fields["message"], "Replacement")
        self.assertEqual(fields["subject"], "Original subject")
        self.assertEqual(self.session.post.call_args.kwargs["params"],
                         {"mode": "edit", "p": 101})

    def test_edit_can_change_subject(self) -> None:
        status, _ = self.invoke(
            "edit", "Example", "--post", "101",
            "--subject", "New subject", "--body", "New body")
        self.assertEqual(status, 0)
        self.assertEqual(self.session.post.call_args.kwargs["data"]["subject"],
                         "New subject")

    def test_dry_run_fetches_form_without_posting(self) -> None:
        status, data = self.post("--dry-run")
        self.assertEqual(status, 0)
        self.assertTrue(data["dry_run"])
        self.assertFalse(data["submitted"])
        self.assertEqual(data["body_bbcode"], "[b]Café[/b]")
        self.assertEqual(self.session.get.call_args.kwargs["params"],
                         {"mode": "post", "f": 2})
        self.session.post.assert_not_called()

    def test_preview_is_distinct_from_final_submit(self) -> None:
        self.session.post.return_value.text = (
            '<div class="post" id="preview"><div class="content">'
            '<strong>Café</strong></div></div>' + FORM)
        status, data = self.post("--preview")
        self.assertEqual(status, 0)
        self.assertTrue(data["preview"])
        self.assertFalse(data["submitted"])
        self.assertIn("Café", data["preview_text"])
        fields = self.session.post.call_args.kwargs["data"]
        self.assertIn("preview", fields)
        self.assertNotIn("post", fields)
        self.session.post.assert_called_once()

    def test_body_files_and_piped_stdin(self) -> None:
        path = self.root / "body.txt"
        path.write_text("Café — UTF-8", encoding="utf-8")
        for body_args in (("--body-file", str(path)),
                          ("--body-file", "-"), ()):
            with self.subTest(body_args=body_args):
                self.stdin.seek(0)
                self.stdin.write("Café — UTF-8")
                self.stdin.seek(0)
                status, data = self.invoke(
                    "edit", "Example", "--post", "101", "--dry-run",
                    *body_args)
                self.assertEqual(status, 0)
                self.assertEqual(data["body_bbcode"], "Café — UTF-8")

    def test_invalid_input_fails_before_network(self) -> None:
        cases = [
            ("post", "Example", "--forum", "2", "--body", "Body"),
            ("post", "Example", "--forum", "2", "--subject", " ",
             "--body", "Body"),
            ("reply", "Example", "--topic", "0", "--body", "Body"),
            ("edit", "Example", "--post", "101", "--body", ""),
            ("edit", "Example", "--post", "101", "--body", "Body",
             "--body-file", "missing"),
            ("edit", "Example", "--post", "101", "--body", "Body",
             "--dry-run", "--preview"),
            ("edit", "Example", "--post", "101", "--body", "Body", "--guest"),
        ]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args)[0], 2)
        self.session.get.assert_not_called()
        self.session.post.assert_not_called()

    def test_unreadable_or_invalid_utf8_body_is_local_failure(self) -> None:
        invalid = self.root / "invalid.txt"
        invalid.write_bytes(b"\xff")
        for path in (self.root / "missing", invalid):
            with self.subTest(path=path):
                self.assertEqual(self.invoke(
                    "edit", "Example", "--post", "101",
                    "--body-file", str(path))[0], 5)
        self.session.get.assert_not_called()

    def test_missing_body_and_terminal_stdin_do_not_prompt(self) -> None:
        with patch.object(self.stdin, "isatty", return_value=True):
            for extra in ((), ("--body-file", "-")):
                with self.subTest(extra=extra):
                    self.assertEqual(self.invoke(
                        "edit", "Example", "--post", "101", *extra)[0], 2)
        self.session.get.assert_not_called()

    def test_missing_session_and_unavailable_forms_never_submit(self) -> None:
        self.session.get.side_effect = lambda *a, **kw: Mock(text="Guest")
        self.assertEqual(self.post()[0], 3)
        self.session.get.side_effect = lambda url, **kw: Mock(
            text='<a href="ucp.php?mode=logout">Logout</a>'
            if url.endswith("index.php") else '<div>No form</div>')
        self.assertEqual(self.post()[0], 8)
        self.session.post.assert_not_called()

    def test_session_expiring_at_submit_is_reported(self) -> None:
        self.session.post.return_value.text = (
            '<title>Login</title>ucp.php?mode=login')
        self.assertEqual(self.post()[0], 3)
        self.session.post.assert_called_once()

    def test_form_key_timing_is_still_shared(self) -> None:
        with patch.object(Board, "_formular_reifen") as timing:
            self.assertEqual(self.post()[0], 0)
        timing.assert_called_once()
        self.assertEqual(timing.call_args.args[0]["form_token"], TOKEN)

    def test_post_failures_are_never_retried(self) -> None:
        for error, expected in ((requests.ConnectTimeout, 9),
                                (requests.ConnectionError, 10),
                                (requests.ReadTimeout, 10)):
            with self.subTest(error=error):
                self.session.post.reset_mock(side_effect=True)
                self.session.post.side_effect = error(TOKEN)
                status, data = self.post()
                self.assertEqual(status, expected)
                self.assertFalse(data["success"])
                self.session.post.assert_called_once()

    def test_http_rejection_and_uncertain_server_errors(self) -> None:
        for http_status, expected in ((403, 4), (429, 4), (500, 10)):
            with self.subTest(http_status=http_status):
                self.session.post.reset_mock(side_effect=True)
                response = requests.Response()
                response.status_code = http_status
                self.session.post.side_effect = requests.HTTPError(
                    TOKEN, response=response)
                self.assertEqual(self.post()[0], expected)
                self.session.post.assert_called_once()

    def test_session_save_failure_after_post_is_uncertain(self) -> None:
        with patch.object(Board, "_save", side_effect=[None, None, OSError()]):
            self.assertEqual(self.post()[0], 10)
        self.session.post.assert_called_once()

    def test_failure_responses_never_save_raw_html(self) -> None:
        for response, expected in (
            ('<p class="error">phpBB rejected this post</p>', 4),
            (FORM + "successfully posted", 4),
            ("Unrecognized response " + TOKEN, 10),
            ("Echoed successfully posted without a confirmation panel", 10),
        ):
            with self.subTest(response=response):
                self.session.post.return_value.text = response
                with patch.object(Board, "dump", side_effect=AssertionError(
                        "Sensitive response must not be saved")):
                    self.assertEqual(self.post()[0], expected)

    def test_missing_preview_does_not_claim_success(self) -> None:
        self.session.post.return_value.text = FORM
        self.assertEqual(self.post("--preview")[0], 8)

    def test_preview_network_failure_is_not_a_final_submission(self) -> None:
        self.session.post.side_effect = requests.ReadTimeout(TOKEN)
        status, data = self.post("--preview")
        self.assertEqual(status, 9)
        self.assertEqual(data["error"], "preview_failed")
        self.session.post.assert_called_once()

    def test_human_and_quiet_success_output(self) -> None:
        for quiet in (False, True):
            with self.subTest(quiet=quiet):
                stdout, stderr = io.StringIO(), io.StringIO()
                args = ["post", "Example", "--forum", "2", "--subject",
                        "Subject", "--body", "Body"]
                with contextlib.redirect_stdout(stdout), \
                        contextlib.redirect_stderr(stderr):
                    status = entry.main(args + (["--quiet"] if quiet else []))
                self.assertEqual((status, stderr.getvalue()), (0, ""))
                if quiet:
                    self.assertEqual(stdout.getvalue(), "")
                else:
                    self.assertIn("Submitted post", stdout.getvalue())

    def test_shared_success_preserves_interactive_messages(self) -> None:
        board = Board.__new__(Board)
        with patch.object(Board, "dump", side_effect=AssertionError("Dump")):
            for page, message in (
                (SUCCESS, t("beitrag_da")),
                ('<meta http-equiv="refresh" content="viewtopic.php#p101">',
                 t("beitrag_da_nr", pid="101")),
            ):
                with self.subTest(page=page):
                    self.assertEqual(board.submit_result(page),
                                     (True, message))
