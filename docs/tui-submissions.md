# TUI submission outcomes

The compose preview and existing send key remain unchanged for posts, replies,
edits, and private messages.

After sending, a confirmed success returns to browsing normally. An explicit
server rejection or returned compose form keeps the existing offer to edit
again. A connection timeout known to occur before connecting also permits
that flow because no content was submitted.

A lost response, server failure, cookie-save failure after the request, or
unrecognized confirmation can mean the content was already saved. In that
case, the TUI displays a warning and returns to browsing after `q`. It does
not offer to edit and send again from that failure screen. Check the topic,
edited post, or PM outbox before starting another submission. A failed
redirect after submission is also uncertain: the original POST may have
succeeded even if the destination page could not be read.

Each final request is attempted once. Preview failures remain preview errors;
they do not trigger the final-submission warning. This behavior does not
change the CLI, attachment upload flow, or PM deletion controls.

The warning does not establish whether the server saved anything. It prevents
an ambiguous response from being presented as a definite rejection. The
warning path does not save raw response HTML or display network exceptions
that might contain private request details.
