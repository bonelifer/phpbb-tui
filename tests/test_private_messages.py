"""Exercise PM automation through existing forms and mocked HTTP responses."""

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


SECRET = "SYNTHETIC_PM_FORM_TOKEN"
USERS = {"Alice": 77, "Bob": 88}


def form(names: tuple[str, ...] = ()) -> str:
    fields = ''.join(
        f'<input type="hidden" name="address_list[u][{USERS[n]}]" value="to">'
        f'<input type="submit" name="remove_u[{USERS[n]}]" value="x">'
        f'<a class="username">{n}</a>' for n in names)
    return (f'<form id="postform">{fields}'
            f'<input type="hidden" name="form_token" value="{SECRET}">'
            '<input name="creation_time" value="1">'
            '<input name="subject" value="Original subject">'
            '<textarea name="message">[quote="Alice"]PM quote[/quote]'
            '</textarea>'
            '</form>')


def listing(folder: str = "inbox", start: int = 0) -> str:
    fid = {"inbox": 0, "sentbox": -1, "outbox": -2}[folder]
    return (f'<h2>Mailbox</h2><p>10% used</p><li class="row pm_unread">'
            f'<a href="ucp.php?i=pm&amp;mode=view&amp;f={fid}&amp;p=7" '
            'class="topictitle">Café PM</a><a class="username">Alice</a>'
            '&raquo; Today</li><div class="pagination">'
            f'Page {start // 5 + 1} of 3<ul><li>'
            f'<a href="ucp.php?i=pm&amp;folder={folder}&amp;start=5">2</a>'
            f'</li><li><a href="ucp.php?i=pm&amp;folder={folder}'
            '&amp;start=10">3</a>'
            '</li></ul></div>')


VIEW = ('<div id="post-7" class="post pm"><h3 class="first">Café PM</h3>'
        '<p class="author"><strong>Sent:</strong> Today '
        '<a class="username">Alice</a><a class="username">Bob</a></p>'
        '<div class="content">Private café body.</div></div>')
SENT = ('<div id="message">PM stored.</div><meta http-equiv="refresh" '
        'content="3; url=./ucp.php?i=pm&amp;mode=view&amp;p=42">')
CONFIRM = ('<form id="confirm" action="./ucp.php?i=pm&amp;mode=compose'
           f'&amp;action=delete&amp;confirm_key={SECRET}">'
           '<input type="hidden" name="p" value="7">'
           '<input type="submit" name="confirm" value="Yes"></form>')
DELETED = ('<div id="message">PM deleted.</div><meta http-equiv="refresh" '
           'content="3; url=./ucp.php?i=pm&amp;folder=0">')


class PrivateMessageTests(unittest.TestCase):
    """Exercise shared PM form handling with mocked requests."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = Mock(headers={})
        self.session.get.side_effect = self.get_response
        self.session.post.side_effect = self.post_response
        cfg = config.Config(
            [config.BoardConfig("Example", "https://example.invalid")],
            self.root, "browser")
        for manager in (
            patch.object(config, "laden", return_value=cfg),
            patch.object(config, "STATE_DIR", self.root),
            patch("phpbb_tui.board.requests.Session",
                  return_value=self.session),
            patch("builtins.input", side_effect=AssertionError("Prompt")),
            patch("getpass.getpass", side_effect=AssertionError("Password")),
            patch("sys.stdin", io.StringIO("")),
        ):
            manager.start()
            self.addCleanup(manager.stop)

    def get_response(self, url: str, **kwargs) -> Mock:
        if url.endswith("index.php"):
            return Mock(text='<a href="ucp.php?mode=logout">Logout</a>')
        params = kwargs.get("params") or {}
        if params.get("action") == "delete":
            return Mock(text=CONFIRM)
        if params.get("mode") == "compose":
            return Mock(text=form(("Alice",) if params.get("p") else ()))
        if params.get("mode") == "view":
            return Mock(text=VIEW)
        return Mock(text=listing(params.get("folder", "inbox"),
                                 params.get("start", 0)))

    def post_response(self, url: str, **kwargs) -> Mock:
        data = kwargs["data"]
        if "confirm" in data:
            return Mock(text=DELETED)
        names = tuple(n for n, uid in USERS.items()
                      if f"address_list[u][{uid}]" in data)
        if "add_to" in data:
            name = data["username_list"]
            canonical = next((n for n in USERS
                              if n.lower() == name.lower()), None)
            if canonical is None:
                return Mock(text=form(names)
                            + '<p class="error">Unknown user</p>')
            return Mock(text=form(tuple(dict.fromkeys((*names, canonical)))))
        if "preview" in data:
            return Mock(text='<div id="preview"><div class="content">'
                        'PM preview</div></div>' + form(names))
        return Mock(text=SENT)

    def invoke(self, *args: str) -> tuple[int, dict]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            status = entry.main([*args, "--json"])
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn(SECRET, stdout.getvalue())
        self.assertNotIn("address_list", stdout.getvalue())
        return status, json.loads(stdout.getvalue())

    def send(self, *extra: str) -> tuple[int, dict]:
        return self.invoke("pm", "Example", "--to", "Alice", "--subject",
                           "A PM", "--body", "**Private café**", *extra)

    def final_sends(self) -> list:
        return [call for call in self.session.post.call_args_list
                if "post" in call.kwargs["data"]]

    def test_mailbox_folders_and_aliases(self) -> None:
        for supplied, canonical in (("inbox", "inbox"), ("outbox", "outbox"),
                                    ("sent", "sent"), ("sentbox", "sent")):
            with self.subTest(folder=supplied):
                status, data = self.invoke(
                    "pms", "Example", "--folder", supplied)
                self.assertEqual(status, 0)
                self.assertEqual(data["folder"], canonical)
                self.assertEqual(data["messages"][0]["id"], 7)
                self.assertIs(data["messages"][0]["unread"], True)
        self.session.post.assert_not_called()

    def test_mailbox_pagination_and_filtering(self) -> None:
        status, data = self.invoke("pms", "Example", "--page", "2")
        self.assertEqual(status, 0)
        self.assertEqual(data["pagination"],
                         {"page": 2, "pages": 3, "start": 5})
        status, data = self.invoke("pms", "Example", "--filter", "missing")
        self.assertEqual((status, data["messages"]), (0, []))

    def test_read_exposes_pm_content_and_folder(self) -> None:
        status, data = self.invoke("pm-read", "Example", "--message", "7",
                                   "--folder", "sent")
        self.assertEqual(status, 0)
        self.assertEqual((data["sender"], data["recipients"]),
                         ("Alice", "Bob"))
        self.assertEqual(data["body"], "Private café body.")
        self.assertEqual(data["attachments"], [])
        self.assertEqual(self.session.get.call_args.kwargs["params"]["f"], -1)

    def test_send_resolves_single_recipient_before_final_post(self) -> None:
        status, data = self.send()
        self.assertEqual(status, 0)
        self.assertEqual(data["recipients"], ["Alice"])
        self.assertEqual(data["message_id"], 42)
        self.assertTrue(data["submitted"])
        self.assertEqual(len(self.final_sends()), 1)
        self.assertEqual(self.final_sends()[0].kwargs["data"]["message"],
                         "[b]Private café[/b]")
        self.assertEqual(self.session.post.call_count, 2)

    def test_multiple_recipients_are_all_resolved(self) -> None:
        status, data = self.send("--to", "Bob")
        self.assertEqual(status, 0)
        self.assertEqual(data["recipients"], ["Alice", "Bob"])
        self.assertEqual(self.session.post.call_count, 3)
        self.assertEqual(len(self.final_sends()), 1)

    def test_duplicate_recipients_are_not_resolved_or_sent_twice(self) -> None:
        status, data = self.send("--to", "alice", "--to", " Alice ")
        self.assertEqual(status, 0)
        self.assertEqual(data["recipients"], ["Alice"])
        self.assertEqual(self.session.post.call_count, 2)

    def test_invalid_and_mixed_recipients_prevent_final_send(self) -> None:
        for names in (("Invalid",), ("Alice", "Invalid")):
            with self.subTest(names=names):
                args = ["pm", "Example", "--subject", "Subject",
                        "--body", "Body"]
                for name in names:
                    args.extend(("--to", name))
                status, data = self.invoke(*args)
                self.assertEqual(status, 6)
                self.assertEqual(data["error"], "recipient_resolution_failed")
        self.assertEqual(self.final_sends(), [])

    def test_silently_dropped_recipient_is_not_partial_success(self) -> None:
        original = self.post_response
        self.session.post.side_effect = lambda url, **kw: (
            Mock(text=form(("Alice",)))
            if kw["data"].get("username_list") == "Bob"
            else original(url, **kw))
        self.assertEqual(self.send("--to", "Bob")[0], 6)
        self.assertEqual(self.final_sends(), [])

    def test_preselected_or_missing_recipients_prevent_send(self) -> None:
        original = self.get_response
        self.session.get.side_effect = lambda url, **kw: (
            Mock(text=form(("Bob",)))
            if (kw.get("params") or {}).get("mode") == "compose"
            else original(url, **kw))
        self.assertEqual(self.send()[0], 8)
        self.session.post.assert_not_called()
        self.session.get.side_effect = lambda url, **kw: (
            Mock(text=form())
            if (kw.get("params") or {}).get("mode") == "compose"
            else original(url, **kw))
        self.assertEqual(self.invoke(
            "pm-reply", "Example", "--message", "7", "--body", "Reply")[0], 6)
        self.session.post.assert_not_called()

    def test_unrequested_group_recipient_prevents_send(self) -> None:
        self.session.post.side_effect = lambda *a, **kw: Mock(text=(
            form(("Alice",)).replace('</form>',
                                     '<input name="address_list[g][99]" '
                                     'value="to"></form>')))
        self.assertEqual(self.send()[0], 6)
        self.assertEqual(self.final_sends(), [])

    def test_dry_run_and_preview_do_not_finally_send(self) -> None:
        for mode in ("--dry-run", "--preview"):
            with self.subTest(mode=mode):
                status, data = self.send(mode)
                self.assertEqual(status, 0)
                self.assertFalse(data["submitted"])
                self.assertEqual(data["recipients"], ["Alice"])
        self.assertEqual(self.final_sends(), [])

    def test_reply_recipient_and_subject_come_from_phpbb(self) -> None:
        status, data = self.invoke("pm-reply", "Example", "--message", "7",
                                   "--body", "Reply")
        self.assertEqual(status, 0)
        self.assertEqual(data["recipients"], ["Alice"])
        self.assertEqual(data["subject"], "Original subject")
        self.assertEqual(data["in_reply_to"], 7)
        self.assertEqual(self.session.get.call_args.kwargs["params"]["action"],
                         "reply")
        self.assertEqual(self.session.post.call_count, 1)

    def test_quote_reply_uses_server_quote(self) -> None:
        status, _ = self.invoke("pm-reply", "Example", "--message", "7",
                                "--quote", "--body", "Response")
        self.assertEqual(status, 0)
        body = self.final_sends()[0].kwargs["data"]["message"]
        self.assertIn("PM quote", body)
        self.assertIn("Alice", body)
        self.assertIn("Response", body)

    def test_piped_body_uses_existing_input_reader(self) -> None:
        with patch("sys.stdin", io.StringIO("Piped PM café")):
            self.assertEqual(self.invoke(
                "pm-reply", "Example", "--message", "7")[0], 0)
        self.assertEqual(self.final_sends()[0].kwargs["data"]["message"],
                         "Piped PM café")

    def test_bad_arguments_fail_without_http(self) -> None:
        for args in (("pm-delete", "Example", "--message", "7"),
                     ("pms", "Example", "--page", "0"),
                     ("pms", "Example", "--guest"),
                     ("pms", "Example", "--folder", "custom"),
                     ("pm-read", "Example", "--message", "-1"),
                     ("pm", "Example", "--to", " ", "--subject", "S",
                      "--body", "B"),
                     ("pm", "Example", "--to", "Alice\nBob", "--subject", "S",
                      "--body", "B")):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args)[0], 2)
        self.session.get.assert_not_called()
        self.session.post.assert_not_called()

    def test_missing_session_does_not_prompt(self) -> None:
        self.session.get.side_effect = None
        self.session.get.return_value.text = "Guest"
        self.assertEqual(self.send()[0], 3)
        self.session.post.assert_not_called()

    def test_disabled_pm_resources_are_not_empty_success(self) -> None:
        original = self.get_response
        self.session.get.side_effect = lambda url, **kw: (
            original(url, **kw) if url.endswith("index.php")
            else Mock(text='<div id="message">PMs disabled</div>'))
        for args in (("pms", "Example"),
                     ("pm-read", "Example", "--message", "7"),
                     ("pm-reply", "Example", "--message", "7", "--body", "B"),
                     ("pm-delete", "Example", "--message", "7", "--yes")):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args)[0], 8)
        self.session.post.assert_not_called()

    def test_unavailable_pm_module_http_status_is_explicit(self) -> None:
        response = requests.Response()
        response.status_code = 503
        self.session.get.side_effect = requests.HTTPError(response=response)
        status, data = self.invoke("pms", "Example")
        self.assertEqual(status, 8)
        self.assertEqual(data["error"], "operation_unavailable")
        self.session.post.assert_not_called()

    def test_expired_session_during_resolution_is_auth_failure(self) -> None:
        self.session.post.side_effect = None
        self.session.post.return_value.text = (
            '<title>Login</title>ucp.php?mode=login')
        self.assertEqual(self.send()[0], 3)
        self.assertEqual(self.final_sends(), [])

    def test_resolution_network_failure_is_not_a_final_send(self) -> None:
        self.session.post.side_effect = requests.ReadTimeout(SECRET)
        self.assertEqual(self.send()[0], 9)
        self.assertEqual(self.final_sends(), [])

    def test_uncertain_send_never_retries(self) -> None:
        original = self.post_response

        def respond(url, **kwargs):
            if "post" in kwargs["data"]:
                raise requests.ReadTimeout(SECRET)
            return original(url, **kwargs)
        self.session.post.side_effect = respond
        self.assertEqual(self.send()[0], 10)
        self.assertEqual(len(self.final_sends()), 1)

    def test_rejected_and_unrecognized_final_responses(self) -> None:
        original = self.post_response
        for response, expected in ((form(("Alice",)), 4),
                                   ("Unknown response", 10)):
            with self.subTest(response=response):
                self.session.post.side_effect = lambda url, **kw: (
                    Mock(text=response) if "post" in kw["data"]
                    else original(url, **kw))
                with patch.object(Board, "dump",
                                  side_effect=AssertionError("Dump")):
                    self.assertEqual(self.send()[0], expected)

    def test_explicit_deletion_uses_existing_confirm_form_once(self) -> None:
        status, data = self.invoke("pm-delete", "Example", "--message", "7",
                                   "--yes")
        self.assertEqual(status, 0)
        self.assertTrue(data["deleted"])
        self.session.post.assert_called_once()
        self.assertIn("confirm_key=" + SECRET,
                      self.session.post.call_args.args[0])
        self.assertEqual(self.session.post.call_args.kwargs["data"]["confirm"],
                         "Yes")

    def test_deletion_network_failure_is_uncertain(self) -> None:
        self.session.post.side_effect = requests.ReadTimeout(SECRET)
        self.assertEqual(self.invoke("pm-delete", "Example", "--message", "7",
                                     "--yes")[0], 10)
        self.session.post.assert_called_once()

    def test_unconfirmed_delete_does_not_claim_success(self) -> None:
        self.session.post.side_effect = None
        self.session.post.return_value.text = CONFIRM
        self.assertEqual(self.invoke("pm-delete", "Example", "--message", "7",
                                     "--yes")[0], 10)

    def test_wrong_folder_or_origin_does_not_confirm_deletion(self) -> None:
        for response in (DELETED.replace('folder=0', 'folder=-2'),
                         DELETED.replace('./ucp.php',
                                         'https://other.invalid/ucp.php')):
            with self.subTest(response=response):
                self.session.post.side_effect = None
                self.session.post.return_value.text = response
                self.assertEqual(self.invoke(
                    "pm-delete", "Example", "--message", "7", "--yes")[0], 10)

    def test_old_interactive_delete_still_returns_none(self) -> None:
        board = Board.__new__(Board)
        with patch.object(board, "pm_loeschen_result",
                          return_value=DELETED) as delete:
            self.assertIsNone(board.pm_loeschen(7, -2))
        delete.assert_called_once_with(7, -2)

    def test_human_and_quiet_modes(self) -> None:
        for args in (("pms", "Example"),
                     ("pm-read", "Example", "--message", "7")):
            for quiet in (False, True):
                with self.subTest(args=args, quiet=quiet):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), \
                            contextlib.redirect_stderr(stderr):
                        status = entry.main(
                            [*args] + (["--quiet"] if quiet else []))
                    self.assertEqual((status, stderr.getvalue()), (0, ""))
                    self.assertEqual(bool(stdout.getvalue()), not quiet)
