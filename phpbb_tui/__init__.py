"""phpBB terminal client, requiring Python 3.11 or newer."""

import sys

__version__ = "1.0.0"


if sys.version_info < (3, 11):
    raise SystemExit("phpbb-tui requires Python 3.11 or newer.")
