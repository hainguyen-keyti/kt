---
description: Output a handoff report in a fixed block that a person or agent can read and verify
---

Output a report on the work just done using EXACTLY the block below: add no section, drop no
section, rename no section. If $ARGUMENTS names an agent or a session, send the report to it with
SendMessage; otherwise print it for the user.

```
## REPORT
STATE: branch=<name> head=<short sha> tree=<clean|dirty> pushed=<yes|no>
DONE:
- <sha> <one line of work done>
EVIDENCE:
- <command run>: <REAL output or number, the important part copied verbatim>
DECIDED:
- <decision I made myself without asking> because <reason>
BLOCKED:
- <item that needs a human decision> | proposal: <option> because <reason>
WAITING_ON:
- <who or what I am waiting on> | waiting in order to do what | idle, or still doing other work
UNSURE:
- <something odd, not yet concluded, not yet handled>
NEXT:
- <next step per HANDOFF>
```

Rules of this block:

- A section with no content gets exactly the word `none`. NEVER leave a section blank or delete
  it: the reader must be able to tell "nothing to report" from "forgot to report".
- A session that touched no git repo (pure advice): write `STATE: none (no repo touched)` and keep
  the rest of the block unchanged.
- Every DONE line must carry a commit sha; work that only touched the machine-local agent layer
  (HANDOFF, DECISIONS, LESSONS) has no sha, so write `- (local) <file> updated`. Uncommitted code
  goes under UNSURE or NEXT, never under DONE.
- Every EVIDENCE line must be real output from something that ran (test count, exit code,
  measured number). NEVER adjectives such as "works well", "fine", "checked carefully".
- When the repo's full gate is green, EVIDENCE uses exactly the form `<full gate command>:
  <verbatim count line> @ <sha>, clean tree` (measured on a clean tree, `git status --porcelain`
  empty; a run while files are half-edited does not count). The receiver (reviewer, merger)
  checks that HEAD matches the sha and the tree is clean before skipping a rerun; if either one
  differs, or the count line is missing, rerun. This is the only line in REPORT that may be reused
  instead of a rerun, because a machine can check both of its conditions.
- UNSURE is the most valuable section; do not leave it empty to look tidy: every place you had
  to guess, every contradiction between docs and code, everything skipped as out of scope
  belongs here.
- WAITING_ON exists because silence has TWO completely different meanings (busy, and stuck) that
  look identical from outside. If you are waiting on someone, name them and say clearly whether
  you are idle or can still do other work. Waiting on nothing: write `none`. Waiting too long:
  PROACTIVELY send one reminder; do not sit idle until someone comes looking for you.
- The whole block stays under 40 lines. Put long details in a file in the repo and point to it;
  do not stuff them into the report.
- The `## REPORT` line is the handoff signal for the repo's stop gate (the docs/agent standard
  set): only when it sees that line does the machine check that HANDOFF.md is newer than the
  session-start marker and audit the plan. Do not print this block in a turn partway through the
  work.
