# Inbox desk: run log (owner's request, 15 Nov 2026)

The owner found on 15 Nov 2026 that the inbox desk had fired on schedule for two days without reading a single
email, and nothing showed where it stopped. So every run now leaves a record in the repository. This file adds
to the desk's scheduled instructions; it does not replace them.

## A. First thing, before anything else (right after you have the checkout)

Append one line to `data/inbox-log.jsonl` and push it straight away, on its own:

    cd <checkout> && echo "{\"at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"stage\":\"started\"}" >> data/inbox-log.jsonl \
      && git add data/inbox-log.jsonl && git -c user.name="The Seax inbox desk" -c user.email="noreply@anthropic.com" commit -q -m "Inbox desk started" \
      && git push -q origin HEAD:main

If the push is refused because someone else pushed first, run `git pull -q --rebase origin main` and push again.

## B. After the Gmail search (step 3 of your instructions)

Append a second line with `"stage":"inbox"`, `"unhandled": <number of unlabelled threads found>` and, if a Gmail
tool failed, `"error": "<the tool and its message, one line>"`. If the Gmail tools cannot be loaded or every call
fails, write that line, push it, and end the run with "ALERT: Gmail not reachable, inbox not read".

## C. Last thing

Append a final line with `"stage":"done"`, `"labelled"`, `"stories"` (list of story ids published), `"events"`
(number of What's On listings added), `"flagged"` (one short phrase each) and `"left"` (threads left for the next
run). Commit it with the same author name and push. If publish.py already pushed, this is a second small push; that is fine.

Keep the file to the last 200 lines (drop the oldest). Never put email addresses of members of the public or the
text of an email in the log.

## D. Backlog rule

When more than 15 threads are unlabelled, handle the newest 15 that are still current this run and leave the rest;
label as handled, without publishing, anything older than 72 hours that is not a dated future event.
