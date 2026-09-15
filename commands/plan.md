---
description: Create a plan file with a six-section intent contract + task DAG, self-check for scope creep, get user approval before writing
---

Create a plan for the work the user just described (or ask what the user wants planned if that is
unclear). The plan is the central artifact: code gets written only after it is approved. No code
in this command.

## Step 1: Interview until all six sections are filled (ask when unclear, never guess)

Ask in batches, each with a proposal, until you can fill every one:

1. **Goal**: the user's words verbatim, not paraphrased.
2. **Non-goals**: an explicit list of what is FORBIDDEN, by name (what not to refactor, what not
   to add, which areas not to touch).
3. **Invariants touched and risk tier**: for a stateful or money-handling system, name which
   conservation laws are touched; being unable to name them means the work is not understood yet,
   so keep asking or stop. Read-only work or work that touches no invariant: write `none` with a
   one-sentence reason, never leave it blank. Also add a "Risk tier" subsection for the work; the
   tier decides how many review rounds: tier 1 (money, auth, tokens, shared contracts, gates) is
   reviewed by a strong model through a risk lens with at least 3 separate mutants, and after
   fixes gets a scoped re-review (the fixed part and the old repro); tier 2 (ordinary features,
   UI) gets one review round, plus one design-review pass for UI, and after fixes the coordinator
   runs acceptance with mutants, no re-review; tier 3 (small slices, config, tests, docs) gets no
   separate review, the coordinator runs acceptance, with 1-2 mutants if there is behavior. A fix
   round that only adds test cases for holes the reviewer pointed out with mutants is accepted by
   running those same mutants, each of which must go red, with no extra reviewer pass, even on
   tier 1.
4. **Acceptance evidence**: a runnable command + the expected number that proves "done". Without
   a checkable command it is not a plan yet, it is a wish. When the work needs a real system
   running (dev server, API, worker, browser, file processing), acceptance is ONE script committed
   to the repo and run with one command: it starts its services on its own port, prints a
   PASS/FAIL table with numbers, exits non-zero on failure, and cleans up after itself; the coder
   writes it once, the reviewer and the coordinator only rerun it (a manual acceptance was redone
   three times on one repo). PASSES when: 0 blocking findings; every remaining finding has
   file:line and repro steps and is logged as cleanup debt for the phase milestone; the acceptance
   script has been run.
   Each acceptance line points to a real test case or probe already seen RED on the old code;
   without one, write NOT PASSED, never a verbal claim. The shape of the evidence (file names,
   record counts, a tool's output format) must be MEASURED before it is written, not inferred from
   the tool's internals: an acceptance that guessed "2 records" while the harness merged them into
   1 forced the prove step to be re-explained.
5. **Blast radius**: the allowlist of paths that may be edited, written as a fenced code block
   right under the heading `## Blast radius` (numbering allowed, e.g. `## 5. Blast radius`), one
   glob per line: `*` crosses `/` too, `**/` also matches zero directories, square brackets are
   literal characters (`app/[id]/page.tsx` matches itself), a leading `./` is dropped, a `#` line
   is a comment. The single canonical grammar lives in the docstring of `hooks/no-offplan-edit.py`.
   The radius must name concrete paths: a line made only of `*`, `/`, `.` (`*`, `**`, `**/*`,
   `*.*`) makes the hook REJECT the whole radius (fail-closed), since a whole-repo fence is a fence
   switched off; write a directory as `src/*` (a `src/` line is rejected too, because it matches
   nothing).
6. **Reuse pointers**: existing files in the repo to follow as a pattern (find candidates yourself
   and propose them).

## Step 2: Split into tasks

- SMALL tasks, ordered by dependency. Each task: a 1-2 sentence description, the files it will
  touch (inside the blast radius), its own acceptance command if any.
- Work that touches a deploy or a migration: that task must come with a rollback step prepared
  BEFOREHAND.
- Tests are written before code, in the earliest possible task (red first, green after).

## Step 3: Self-check before presenting (consistency gate)

- Go over each task again: a task that cannot be traced back to the Goal or to some intent section
  is scope creep; cut it or raise it with the user again.
- Every file in the tasks must be inside the blast radius; on a mismatch, fix one of the two sides
  and say so.
- The radius must also cover the TEST path for every source file with checkable behavior, and the
  path of the acceptance SCRIPT (section 4): forget them and the fence blocks the test written
  first in the very first task.
- Each acceptance runs with one command; the plan has the "Risk tier" subsection (section 3).
- Technical specifics the plan commits to (signatures, library behavior, acceptance commands and
  measurements) must already have been tried out, or be citable as `file:line` from the source or
  an installed `.d.ts`; every package the code, tests, and acceptance use must already be declared
  and present in the lockfile, and if not, that becomes the first task. Anything not yet verified
  is written as "needs a probe in the first task", not stated as known fact.

## Step 4: Present for approval, then write

- Present the whole plan for user approval. Whatever the user cuts stays cut; do not argue back by
  writing more.
- If `.claude/active-plan` exists (another plan is running): STOP, do not write a new plan; the
  old plan must first pass acceptance through `/kt:save`, or the user must approve removing the
  marker. One plan at a time.
- After approval: write to `docs/agent/plans/YYYY-MM-DD-<slug>.md` (get the date with
  `date +%Y-%m-%d`). A repo without the standard docs/agent set runs `/kt:adopt` first: the fence,
  progress, and parked questions all live in docs/agent/; a repo that deliberately does not use
  the standard set (its CLAUDE.md says so explicitly) gets the plan presented in the conversation,
  without arming the fence. The header is the six sections, the body is the task DAG, and the file
  ends with an empty `## Evidence` section for pasting measurements at acceptance; do NOT copy the
  execution rules into the plan (they live in `/kt:go` and kt rules §2-4; a copy is one more
  version to drift).
- ARM THE FENCE right after writing the plan, run from the plan's repo ROOT (the marker and the
  path inside it are relative to the directory the command runs in; a session opened in a parent
  folder of several repos must cd into the right repo first):

  ```
  mkdir -p .claude && printf '{"plan":"%s","base":"%s"}\n' "docs/agent/plans/<file>.md" "$(git rev-parse HEAD)" > .claude/active-plan
  ```

  Once armed: add one line "plan <path>, base <sha>, next step = T1" to the "Active plan" section
  of `docs/agent/HANDOFF.md` (HANDOFF is the lookup source if the marker breaks, and go/load read
  from it), then run the audit once (the command in `/kt:go` step 4) to get a clean baseline. From
  then on every Write/Edit/NotebookEdit outside the radius is blocked by the `no-offplan-edit`
  hook, and the plan file itself and the plans folder are locked regardless of radius (through the
  shell as well, together with the marker: those are the only two guards of `no-offplan-bash`); a
  shell write outside the radius is not blocked on the spot but surfaces in the `/kt:go` audit
  before commit, so write files with Write/Edit. Removing the fence is the job of `/kt:save` at
  acceptance. Widen the radius mid-flight ONLY with user approval: read the old `base` from the
  marker, `rm` the marker (a Bash command of its own), edit the plan, then recreate the marker
  with EXACTLY the old `base` in a SEPARATE Bash command (not the new HEAD, so the audit at save
  still sees the tasks already committed; the fence blocks overwriting a live marker and the hook
  runs BEFORE the command, so `rm && printf` folded into one line gets blocked).
- Anything the user settles during the interview that has lasting value: record it in
  `docs/agent/DECISIONS.md`.
- Report back: the plan path, the task count, that the fence is armed, and remind the user that
  any change outside the blast radius during execution must be proposed again, never done on the
  agent's own initiative.
