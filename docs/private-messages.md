# Private-message automation

PM commands use the existing Board mailbox parsers, compose forms, recipient
resolution, and deletion confirmation flow. Run `phpbb-tui login example`
first. These commands reuse the stored session, require authentication, and
never prompt, open an editor/browser, or accept guest/credential flags.

## Mailboxes and reading

```sh
phpbb-tui pms example --folder inbox --json
phpbb-tui pms example --folder sent --page 2 --json
phpbb-tui pms example --folder outbox --filter "Report" --json
phpbb-tui pm-read example --message 42 --folder inbox --json
```

Folders are `inbox` (default), `sent`, and `outbox`. `sentbox` is accepted as an
alias for `sent`; output uses the canonical names. Custom folders are not
exposed. `--folder` has short form `-f`; `--message` has `-m`.

For `pms`, `--page` (`-p`) is one-based and uses phpBB's own navigation offsets.
`--filter` (`-F`) filters subjects in the retrieved page, case-insensitively.
It does not run a server search or fetch every page. Reads preserve normal
phpBB effects such as marking a PM read and moving a sender's outbox entry
to sent when the recipient reads it.

## Sending and replying

```sh
phpbb-tui pm example --to alice --subject "Report" --body-file report.md
phpbb-tui pm example --to alice --to bob --subject "Report" --body "**Update**"
phpbb-tui pm-reply example --message 42 --body-file reply.md
phpbb-tui pm-reply example --message 42 --quote --body "My response"
```

New PMs require `--subject` and at least one `--to` (`-t`). Repeat `--to` for
multiple individual users, using one username per option. Duplicate names are
deduplicated without adding duplicate recipients. Every name is resolved
through phpBB before final sending. Any invalid or silently dropped recipient
prevents the final send; the CLI does not intentionally send a partial list.
Group recipients are not supported.

Replies obtain their recipient and default subject from phpBB's reply form;
they do not accept `--to`. An optional `--subject` replaces the reply subject.
`--quote` (`-Q`) is a boolean for PM replies; phpBB supplies the quoted message
and attribution. Conversion uses the same BBCode/Markdown functions as the TUI.

Body input follows the [posting rules](posting.md#body-input): inline `--body`,
UTF-8 `--body-file`, `--body-file -`, or automatic piped stdin. Empty bodies,
missing subjects, malformed IDs, and conflicting sources fail without prompting.

## Dry-run and preview

```sh
phpbb-tui pm example --to alice --subject "Report" --body-file report.md --dry-run --json
phpbb-tui pm-reply example --message 42 --body "Reply" --preview --json
```

`--dry-run` (`-n`) validates input, the session, the PM form, and recipients.
Recipient validation can require non-final POST requests to phpBB. It never
performs final sending or intentionally creates a persistent PM. It returns
the resolved subject, recipients, and converted body, excluding hidden fields
and tokens. It does not prove that the server will accept the final content.

`--preview` (`-v`) resolves recipients, requests phpBB's preview, and returns
rendered plain text without final sending. Preview and dry-run are mutually
exclusive. Both may update ordinary session state. Repeated `--attach FILE`
options add files where the PM form permits them; see the
[attachment reference](attachments.md). The TUI workflow remains available.

## Deletion

```sh
phpbb-tui pm-delete example --message 42 --folder inbox --yes --json
```

`--yes` (`-y`) is required. Omitting it fails before network access. The CLI
uses phpBB's confirmation form and localized confirmation value. It does not
change the TUI's interactive confirmation workflow.

Select the folder shown by the mailbox list. The board determines the normal
deletion behavior for that folder. Inbox deletion removes the selected user's
copy; it does not remove another user's already-held copy. Sent/outbox requests
follow phpBB's own rules. No automatic deletion retry is performed.

## Output contract

All PM commands support `--json` (`-j`) and `--quiet` (`-q`), mutually exclusive.
The [common output envelope](automation.md#output-contract) contains `success`,
`action`, and `board` on success. Command-specific fields are:

| Command | Fields |
| --- | --- |
| pms | `folder`, `title`, `storage`, `pagination`, `messages` |
| pm-read | `message_id`, `subject`, `sender`, `recipients`, `date`, `body`, `folder`, `folder_id`, `attachments` |
| pm / pm-reply | `subject`, `recipients`, `submitted`; confirmed sends add `message_id` and `url` |
| pm-delete | `message_id`, `folder`, `deleted: true` |

Mailbox rows contain `id`, `subject`, `partner`, `date`, `unread`, `folder`, and
`folder_id`. Pagination contains `page`, `pages` (or `null` when unavailable),
and `start`. `storage` preserves the board's displayed usage text, or `null`.
Dates retain source formatting; unknown optional strings are `null`.

For reads, `recipients` preserves the shared parser's joined display string
(or `null`). Do not split it to reconstruct usernames. For writes, `recipients`
is an array of names resolved by the compose form. Reply results also include
`in_reply_to`. Dry-run adds `dry_run: true`, `body_bbcode`, and `submitted: false`;
preview adds `preview: true`, `preview_text`, and `submitted: false`.

Confirmed-send URLs omit session parameters. IDs come from the server's
confirmation; an unrecognized result never produces an invented message ID.
Attachment metadata follows the read-only schema; transfer is documented in the
[attachment reference](attachments.md).

## Failures and write uncertainty

Expected errors use the existing JSON error envelope and nonzero statuses.
Invalid arguments return 2, expired sessions 3, explicit submission rejection
4, and body-file errors 5. Recipient resolution failures return 6; any prepared
valid recipients remain unsent. Missing permissions/resources or unavailable
PM modules return 8, including an HTTP 503 while accessing the PM module.

Resolution/read network failures and known connection failures return 9.
Final sending/deletion can return 10 when the server may have applied the
request but confirmation was lost or unrecognized. Inspect the mailbox before
retrying: an automatic retry could send a duplicate message. The final write
is sent once, and the CLI does not save raw form/session diagnostics.

Run `python3 -m unittest discover -s tests -v` for offline coverage. PM tests
mock requests while exercising the actual CLI, forms, parsers, and converter.
Live checks must use controlled disposable accounts and boards.
