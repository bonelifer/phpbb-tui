# Regression tests

From the repository root, using Python 3.11+ with the existing `requests`
dependency installed:

```sh
python3 -m unittest discover -s tests -v
```

The suite uses standard-library `unittest`; no additional test dependency is
required. HTTP sessions, terminal UI launch, and credential prompts are mocked.
Configuration and cookies use temporary directories. HTML fixtures are synthetic
prosilver-style examples, not captures from real accounts or forums.

Coverage protects management commands and TUI dispatch, configuration lookup,
cookie persistence, forum/topic/thread parsing, and network retry boundaries.
These tests do not exercise curses rendering, an actual editor or browser, or a
live phpBB server. They provide regression coverage for the existing client,
not proof of compatibility with every phpBB installation.
