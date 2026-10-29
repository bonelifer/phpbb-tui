# TUI attachment downloads

In the attachment list, Enter downloads to the configured downloads directory
and opens the completed file. Lowercase `s` saves there without opening it.
Uppercase `S` asks for a destination file or directory. Leave the answer blank
to cancel. Existing directories are recognized automatically; use a trailing
`/` when choosing a directory that does not yet exist. `~` expands to the home
directory. A relative path is relative to the client's working directory.

The default directory still comes from the existing configuration. Choosing a
save-as destination affects only that download; it does not change settings.
When choosing a directory, the filename supplied by the server is used after
the existing filename sanitization. Choosing a file uses that exact path.

Existing regular files require explicit confirmation on a screen showing the
full destination. Answer `y` (or `j`) to replace; `n` or `q` cancels. Symlinks
and non-file targets are refused. A file appearing during a download also
requires confirmation rather than being overwritten automatically.

The existing streaming and temporary-file handling protects a prior file if
the transfer fails. Confirming replacement may require a second GET request;
the first response establishes the actual server filename. Files are opened
only after a successful Enter download. Saving with `s` or `S` never opens them.

The same controls apply to post and PM attachments. CLI download defaults and
`--force` behavior are unchanged.
