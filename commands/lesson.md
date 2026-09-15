---
description: Quickly log a lesson in the repo LESSONS.md; spot repeats and promote them to a rule or hook
---

Record the following lesson in the repo's ledger: $ARGUMENTS (if empty: ask the user "what lesson,
and what did it cost?"; if the lesson just happened in this session, propose a draft entry yourself
and ask the user to confirm).

## Step 1: Check for a repeat before writing

- Read `docs/agent/LESSONS.md`. If the repo has no `docs/agent/` yet, DO NOT create a lone file
  (an orphan file makes `/kt:load` believe the repo already has the standard set installed):
  suggest `/kt:adopt`, and for now carry the lesson in the end-of-session report. If the repo has
  docs/agent but no LESSONS.md, create it from the skeleton: a title, and the note "each lesson
  1-3 lines; a lesson that repeats a second time is promoted to a rule or hook, then deleted;
  keep under 40 lines".
- If a similar lesson already exists: THIS IS THE SECOND TIME. Do not add another entry. Propose
  a promotion instead: a machine-checkable lesson becomes a hook or lint rule (with a draft
  config); a behavioral lesson becomes one line in the repo's CLAUDE.md (with that draft line and
  the reason). If the user approves, apply it, then DELETE the original lesson from LESSONS.md.

## Step 2: Write (when the lesson is new)

- Exactly 1-3 lines: absolute date, what happened, the cause, the right way. Write it so a later
  session can avoid the mistake, not as a diary of feelings.
- A machine-wide lesson (not specific to this repo): tell the user plainly and propose putting it
  into kt instead of the repo's LESSONS: a behavioral rule goes into `rules/work.md`, a
  machine-checkable lesson becomes a hook. The process for changing kt (bump version,
  `claude plugin update kt@kt`, restart before proving) lives in the "Maintaining kt" section of
  the kt README; do not copy it here.

## Step 3: Tidy up

- File over 40 lines: propose cutting lessons that no longer have value, or that were already
  promoted but never deleted.
- Report back in one line: what was recorded, where, and whether anything was proposed for
  promotion.
