# TUI pagination

The existing `n` and `p` keys use offsets from the board's numeric pagination
links for forum lists, keyword and predefined searches, threads, and PM folders.
The TUI no longer assumes 50 topics, 15 posts, or at least 25 PMs per page.

Links must belong to the same board, path, and resource. Nested topic links
inside a forum list do not control the forum's pagination. PM folder names
are matched to phpBB's numeric folder IDs.

If the board reports more pages but does not expose an unambiguous matching
numeric link, the TUI displays a navigation message instead of guessing an
offset. Custom styles without recognizable pagination may require browser
navigation. A known last-page link is also used when returning after a reply;
without one, the current page is refreshed.

This change preserves filtering, compose controls, and CLI behavior. It does
not add page-size settings or change server pagination preferences.
