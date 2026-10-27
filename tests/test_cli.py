"""Exercise read-only commands without real accounts or public board writes."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from phpbb_tui import __main__ as entry
from phpbb_tui import cli, config
from phpbb_tui.board import BoardError, LoginRequired


def page(number: int = 1, size: int = 7,
         path: str = "viewtopic.php") -> str:
    """Synthetic board HTML with non-default pagination and Unicode text."""
    identifier = "f=42" if path == "viewforum.php" else "t=42"
    return f'''
<a href="ucp.php?mode=logout">Logout</a>
<h2 class="forum-title">Café topics</h2>
<a href="viewforum.php?f=2" class="jumpbox-forum-link">Café</a>
<li class="row topic_unread sticky">
<a href="viewtopic.php?t=42" class="topictitle">Café &amp; support</a>
<div class="topic-poster"><a class="username">Alice</a></div>
<dd class="posts">3</dd><dd class="views">8</dd></li>
<h2 class="topic-title">Café thread</h2>
<a href="viewforum.php?f=2">Forum</a>
<div id="p101" class="post"><a class="username">Alice</a>
<time>Today</time><h3>Subject</h3>
<div class="content">Hello café.</div></div>
<div class="action-bar bar-bottom"></div>
<div class="pagination">Page <strong>{number}</strong> of <strong>4</strong>
<ul><li><a href="{path}?{identifier}&amp;start={size}">2</a></li>
<li><a href="{path}?{identifier}&amp;start={3 * size}">4</a></li></ul></div>
'''


class CliTests(unittest.TestCase):
    """Exercise the real Board parsers with an isolated mocked HTTP session."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bc = config.BoardConfig("Example", "https://example.invalid")
        self.cfg = config.Config([self.bc], self.root / "downloads", "browser")
        self.session = Mock(headers={})
        self.session.get.side_effect = lambda *a, **kw: Mock(text=page(
            (kw.get("params") or {}).get("start", 0) // 7 + 1,
            path=a[0].rsplit("/", 1)[-1]))
        for manager in (
            patch.object(config, "laden", return_value=self.cfg),
            patch.object(config, "STATE_DIR", self.root),
            patch("phpbb_tui.board.requests.Session",
                  return_value=self.session),
            patch("builtins.input", side_effect=AssertionError("Prompt")),
            patch("getpass.getpass", side_effect=AssertionError("Password")),
        ):
            manager.start()
            self.addCleanup(manager.stop)

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            status = entry.main(list(args))
        self.session.post.assert_not_called()
        return status, stdout.getvalue(), stderr.getvalue()

    def test_all_commands_return_clean_json(self) -> None:
        for args, collection in (
            (("forums", "Example"), "forums"),
            (("topics", "Example", "--forum", "2"), "topics"),
            (("topic", "Example", "--topic", "42"), "posts"),
            (("search", "Example", "--unread"), "topics"),
        ):
            with self.subTest(args=args):
                status, stdout, stderr = self.run_cli(*args, "--json")
                self.assertEqual((status, stderr), (0, ""))
                data = json.loads(stdout)
                self.assertTrue(data["success"])
                self.assertTrue(data[collection])
                self.assertNotIn("\x1b", stdout)
        self.assertIs(json.loads(self.run_cli(
            "topics", "Example", "--forum", "2", "--json")[1])[
                "topics"][0]["unread"], True)

    def test_page_uses_server_offset_and_can_derive_hidden_page(self) -> None:
        for command, option in (("topics", "--forum"),
                                ("topic", "--topic"),
                                ("search", "--query")):
            with self.subTest(command=command):
                status, stdout, _ = self.run_cli(
                    command, "Example", option, "42", "--page", "3", "--json")
                self.assertEqual(status, 0)
                self.assertEqual(json.loads(stdout)["pagination"],
                                 {"page": 3, "pages": 4, "start": 14})

    def test_bad_arguments_fail_before_http(self) -> None:
        cases = [
            ("topics", "Example"),
            ("topics", "Example", "--forum", "0"),
            ("topic", "Example", "--topic", "-1"),
            ("topic", "Example", "--topic", "42", "--page", "0"),
            ("search", "Example"),
            ("search", "Example", "--unread", "--mine"),
            ("search", "Example", "--query", "  "),
            ("forums", "missing"),
            ("forums", "Example", "--quiet"),
        ]
        for args in cases:
            with self.subTest(args=args):
                status, stdout, _ = self.run_cli(*args, "--json")
                self.assertEqual(status, 2)
                self.assertFalse(json.loads(stdout)["success"])
        self.session.get.assert_not_called()

    def test_missing_and_expired_sessions_do_not_prompt(self) -> None:
        for response in ("<title>Guest index</title>",
                         '<title>Login</title>ucp.php?mode=login'):
            with self.subTest(response=response):
                self.session.get.side_effect = None
                self.session.get.return_value.text = response
                status, stdout, _ = self.run_cli("forums", "Example", "--json")
                self.assertEqual(status, 3)
                self.assertEqual(json.loads(stdout)["error"],
                                 "authentication_required")
        with patch.object(cli.ReadBoard, "foren", side_effect=LoginRequired()):
            self.session.get.return_value.text = page()
            self.assertEqual(self.run_cli("forums", "Example", "--json")[0], 3)

    def test_guest_does_not_load_or_change_saved_session(self) -> None:
        jar = MozillaCookieJar(str(self.bc.cookie_path))
        jar.set_cookie(Cookie(
            0, "synthetic", "fixture", None, False, "example.invalid", False,
            False, "/", True, False, None, True, None, None, {}, False))
        jar.save(ignore_discard=True, ignore_expires=True)
        original = self.bc.cookie_path.read_bytes()
        self.assertEqual(self.run_cli("forums", "Example", "--guest")[0], 0)
        self.assertEqual(list(self.session.cookies), [])
        self.assertEqual(self.bc.cookie_path.read_bytes(), original)
        self.assertFalse(Path(self.session.cookies.filename).exists())
        self.assertEqual(self.run_cli("forums", "Example", "--json")[0], 0)
        self.assertEqual([c.name for c in self.session.cookies], ["synthetic"])

    def test_filter_and_quiet_modes(self) -> None:
        status, stdout, _ = self.run_cli(
            "topics", "Example", "--forum", "2", "--filter", "missing", "-j")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout)["topics"], [])
        status, stdout, stderr = self.run_cli("forums", "Example", "--quiet")
        self.assertEqual((status, stdout, stderr), (0, "", ""))

    def test_search_modes_reuse_existing_operations(self) -> None:
        for mode, search_id in cli.SEARCHES.items():
            with self.subTest(mode=mode):
                self.assertEqual(self.run_cli(
                    "search", "Example", "--" + mode, "--quiet")[0], 0)
                self.assertEqual(self.session.get.call_args.kwargs["params"],
                                 {"search_id": search_id, "start": 0})
        self.assertEqual(self.run_cli(
            "search", "Example", "--query", "café", "--quiet")[0], 0)
        params = self.session.get.call_args.kwargs["params"]
        self.assertEqual(params["keywords"], "café")
        self.assertEqual(params["start"], 0)

    def test_failures_do_not_echo_network_secrets(self) -> None:
        secret = "SENSITIVE_COOKIE_OR_TOKEN"
        error = BoardError(secret)
        error.__cause__ = requests.ConnectionError(secret)
        with patch.object(cli.ReadBoard, "foren", side_effect=error):
            status, stdout, stderr = self.run_cli(
                "forums", "Example", "--json")
        self.assertEqual(status, 9)
        self.assertNotIn(secret, stdout + stderr)
        self.session.close.assert_called()

    def test_http_status_errors_have_meaningful_exit_codes(self) -> None:
        for http_status, expected in ((403, 8), (404, 7), (500, 9)):
            with self.subTest(http_status=http_status):
                response = requests.Response()
                response.status_code = http_status
                error = BoardError("fixture")
                error.__cause__ = requests.HTTPError(response=response)
                with patch.object(cli.ReadBoard, "foren", side_effect=error):
                    self.assertEqual(self.run_cli(
                        "forums", "Example", "--json")[0], expected)

    def test_credentials_are_not_accepted_or_echoed(self) -> None:
        status, stdout, stderr = self.run_cli(
            "forums", "Example", "--password", "SENSITIVE", "--json")
        self.assertEqual(status, 2)
        self.assertNotIn("SENSITIVE", stdout + stderr)
        self.session.get.assert_not_called()

    def test_bad_config_and_url_fail_without_network(self) -> None:
        for url in ("file:///etc/passwd", "http://[", "http://host:bad",
                    "http://user:SECRET@example.invalid"):
            with self.subTest(url=url):
                self.bc.url = url
                status, stdout, stderr = self.run_cli(
                    "forums", "Example", "--json")
                self.assertEqual(status, 5)
                self.assertNotIn("SECRET", stdout + stderr)
        self.session.get.assert_not_called()
        with patch.object(config, "laden", side_effect=ValueError("SECRET")):
            status, stdout, _ = self.run_cli("forums", "Example", "--json")
        self.assertEqual(status, 5)
        self.assertNotIn("SECRET", stdout)

    def test_bare_command_with_bad_config_has_no_traceback(self) -> None:
        with patch.object(config, "laden", side_effect=ValueError("SECRET")):
            status, stdout, stderr = self.run_cli("forums")
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertNotIn("SECRET", stderr)

    def test_phpbb_information_page_is_not_an_empty_topic(self) -> None:
        self.session.get.side_effect = None
        self.session.get.return_value.text = (
            '<a href="ucp.php?mode=logout">Logout</a>'
            '<div id="message"><h2>Information</h2>'
            '<p>The requested topic does not exist.</p></div>')
        self.assertEqual(self.run_cli(
            "topic", "Example", "--topic", "999", "--json")[0], 8)

    def test_ambiguous_board_is_rejected(self) -> None:
        self.cfg.boards.append(config.BoardConfig(
            "Example", "https://other.invalid"))
        self.assertEqual(self.run_cli("forums", "Example", "--json")[0], 2)
        self.session.get.assert_not_called()

    def test_command_named_board_keeps_legacy_launch(self) -> None:
        self.bc.name = "forums"
        start = Mock(return_value="done")
        ui = types.ModuleType("phpbb_tui.ui")
        ui.starten = start
        with patch.dict("sys.modules", {"phpbb_tui.ui": ui}):
            for args in (("forums",), ("forums", "--guest"),
                         ("tui", "forums", "--guest")):
                with self.subTest(args=args):
                    self.assertEqual(self.run_cli(*args)[0], 0)
        self.assertEqual(start.call_count, 3)

    def test_help_never_loads_configuration(self) -> None:
        with patch.object(config, "laden",
                          side_effect=AssertionError("Config")):
            for command in cli.COMMANDS:
                with self.subTest(command=command):
                    with self.assertRaises(SystemExit) as raised:
                        self.run_cli(command, "--help")
                    self.assertEqual(raised.exception.code, 0)

    def test_automation_import_does_not_load_curses(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import sys; import phpbb_tui.cli; "
             "assert 'curses' not in sys.modules; "
             "assert 'phpbb_tui.ui' not in sys.modules"],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


class PaginationTests(unittest.TestCase):
    """Never silently apply the TUI's hardcoded page-size increments."""

    def test_single_page_does_not_invent_total(self) -> None:
        self.assertEqual(cli.pagination("No page metadata", 1), (1, None, 0))

    def test_post_content_is_not_page_metadata(self) -> None:
        self.assertEqual(cli.pagination(
            '<div class="content">Page 9 of 10</div>', 1), (1, None, 0))

    def test_out_of_range_and_missing_navigation(self) -> None:
        for html, number, code in ((page(), 5, "page_not_found"),
                                   ("No links", 2, "pagination_unavailable")):
            with self.subTest(code=code):
                with self.assertRaises(cli.CommandError) as raised:
                    cli.pagination(html, number)
                self.assertEqual(raised.exception.code, code)

    def test_links_outside_pagination_are_ignored(self) -> None:
        with self.assertRaises(cli.CommandError):
            cli.pagination('<a href="viewtopic.php?start=99">2</a>', 2)

    def test_active_marker_and_inline_topic_links(self) -> None:
        html = '''<div class="pagination"><ul>
<li class="active"><span>3</span></li>
<li><a href="viewforum.php?f=2&amp;start=7">2</a></li>
<li><a href="viewforum.php?f=2&amp;start=21">4</a></li></ul></div>
<div class="pagination"><ul>
<li><a href="viewtopic.php?t=42&amp;start=99">2</a></li></ul></div>'''
        self.assertEqual(cli.pagination(
            html, 3, "viewforum.php", {"f": 2}), (3, None, 14))
