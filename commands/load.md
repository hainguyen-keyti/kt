---
description: Reload the full project context, restate it, and wait for the user to confirm before going on
---

Reload the project context in exactly this order, skipping no step:

1. Read (if present): `docs/agent/PROJECT.md`, `docs/agent/HANDOFF.md`, `docs/agent/DECISIONS.md`,
   `docs/agent/LESSONS.md`, `docs/agent/ACCESS.md` (and `ACCESS.local.md` if present); for any
   file the "=== docs/agent bootstrap ===" block at the top of the context injected IN FULL, use
   that copy and do not Read it again (it was injected as the session opened, so it cannot be
   stale yet); if the block is only a `persisted-output` preview (Claude Code cuts hook output
   over 10,000 characters down to 2000), treat it as carrying no file at all: Read the saved file
   the stub names, or Read each file; then the repo's `CLAUDE.md` and the rule files it points
   to; then `git log --oneline -15` and `git status`. Then the step named
   "Reconcile the ledger with the machine", never skipped: the sha and date on the HANDOFF
   "Last updated" line against `git log -1 --format='%h %ci'`; the HANDOFF mtime (`stat`) against
   that commit's date; the `kt-skeleton <version>` stamp in the bootstrap block against the
   version of the installed kt (`installed_plugins.json`; no stamp means an old
   skeleton; on a mismatch rerun the Hooks step of `/kt:adopt`); any ledger entry that has a real
   source in the repo (defects, run meta, lockfile) against that source. Call out any mismatch at
   the very top of the presentation.
2. If the repo has NO `docs/agent/`: read CLAUDE.md, README, the most recent handoff or plan file
   in `docs/`, and git log; tell the user the repo does not have the standard docs/agent set
   installed and suggest running `/kt:adopt` (the install command that learns first and builds
   after), but still summarize the context as well as possible from whatever is there.
3. Present it back to the user, briefly, in exactly this frame:
   - What the project is; the current STAGE and the consequences in force.
   - State: which branch, what is done, what is unfinished.
   - Decisions WAITING on the user, numbered (from the "Open decisions" section of DECISIONS.md),
     and entries under "Deferred with a due date" that are OVERDUE as of today
     (`date +%Y-%m-%d`), named explicitly.
   - Lessons to avoid, only those relevant to the upcoming work (from LESSONS.md).
   - Access relevant to the upcoming work (from ACCESS.md): servers, services, where secrets live.
     If HANDOFF states which access the next step needs, run the quick check for exactly that
     access (only read-only commands from the "Quick checks" section of ACCESS.md, such as
     ssh 'echo ok' or curl /health); everything else waits until the user confirms; do not guess
     the upcoming work in order to scan.
   - Plan: if the marker `.claude/active-plan` (created by /kt:plan) exists, read the plan file it
     points to, present the task currently in progress (per the progress in the HANDOFF
     "Active plan" section), ECHO VERBATIM the `## Blast radius` block (an overly wide radius must
     hit the user's eye right here), and the open lines of "Parked questions". If there is NO
     marker, say out loud exactly one line "NO ACTIVE PLAN: no fence; work touching 2+ files,
     over 50 lines, or a sensitive area must go through /kt:plan first" (a session once ran 53
     minutes without a fence and nobody noticed).
   - The next task per HANDOFF.md.
4. End with exactly one question: "Have I understood the above correctly, and where do we start?"

FORBIDDEN to do anything else (edit files, run state-changing commands) until the user confirms
the context is correct. Do not fill gaps with assumptions: anything still ambiguous after reading
goes into the presentation as a question.
