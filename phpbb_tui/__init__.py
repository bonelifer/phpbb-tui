"""phpBB terminal client, requiring Python 3.11 or newer."""

import sys


if sys.version_info < (3, 11):
    raise SystemExit("phpbb-tui requires Python 3.11 or newer.")
