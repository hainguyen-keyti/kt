---
description: "Prove a gate is alive: break it red on purpose, paste the red output, revert, paste the green control-run output"
---

Prove that this gate really bites: $ARGUMENTS (if empty: ask the user which gate; suggest gates
added or changed recently: a new test, a new lint rule, a new hook, a new CI check).

Premise of this command: a gate that bites nothing looks EXACTLY like a gate that works well;
both are green. A gate never seen red counts as a gate that does not exist.

## Safety first

- Run only in a local environment. Do NOT break a gate on production, staging, or anything that
  serves other people. Do not touch real money paths.
- Record the state before starting: `git status --porcelain` must be clean (or the user confirms
  the unfinished changes); the command must end with the tree back in exactly that state.
- With an active plan (`.claude/active-plan`): a mutant outside the blast radius will be blocked
  by the plan fence. Ask the user to choose first (widen the radius, remove the marker, or move
  the prove to after acceptance); do not remove it on your own.
- Marker or hook gates (fence, PreToolUse hook): prove in a temporary repo from `mktemp -d` (mkdir
  `.git` as the boundary); do NOT create `.claude/active-plan` in the real checkout: the marker
  belongs to the whole checkout and arms the fence for every other session open there.
- Probe or verify via a subagent: NEVER run it on a weaker model than the session (lower effort
  instead if cost matters), and require it to quote the exact strings that must appear. For a
  context-injecting hook, cross-check `grep -c hook_additional_context` in the subagent transcript
  (full copy at `~/.claude/projects/<project-slug>/<session-id>/subagents/agent-*.jsonl`, or the
  file `tasks/<agent-id>.output` in the session's temp directory; grep only, never cat the whole
  file) to get evidence that does not depend on the model.

## The 4-step ritual: no conclusion until all 4 are done

1. **Understand the gate**: what ERROR this gate must catch, and by what mechanism. Say it in one
   sentence before breaking anything.
2. **Break it RED**: create the smallest DELIBERATE violation of exactly the kind of error the
   gate must catch (edit code, add a rule-breaking line, corrupt an input...), run the gate, PASTE
   THE RED OUTPUT verbatim.
   **BEFORE CONCLUDING "the gate is blind", PROVE THE VIOLATION WAS REALLY APPLIED**: a diff, or
   the file's line count before and after planting it; paste the numbers. A violation that did not
   apply (sed did not match, the wrong file was edited, the edited code branch never runs) gives
   green output identical to a blind gate, and a wrong conclusion at that point costs more than not
   checking at all. A mutant not proven to be applied proves exactly nothing.
   A gate that still does not go red with the violation really planted = a dead gate: stop here
   and tell the user at once; this is a serious finding, not a failed step.
   **Also check the MEASUREMENT PATH**: a gate can be green because the measurement never reaches
   the thing under check (the button is disabled, so the click does nothing; the script dies on
   `set -e` before reaching the step to observe; the asserted string was already on screen for
   another reason). Only trust the red case once you can answer "what is the one path that reaches
   the thing I am pinning".
3. **GREEN control run**: revert the violation, run again, PASTE THE GREEN OUTPUT verbatim. Only
   red for the right reason plus green for the right reason counts; red from a different error
   (syntax, missing dep) proves nothing yet.
4. **Clean up**: `git status --porcelain` must match the starting state. Leave no violation
   behind, leave no junk files.

## Ledger

- Live gate: add one line to the "Verify commands" section of `docs/agent/HANDOFF.md` (gate X
  proven on date Y) if the repo has the docs/agent set.
- Dead gate: this is a lesson; record it in `docs/agent/LESSONS.md` with the cause after the fix,
  and the fixed gate must run the full 4-step ritual again.
- Final report: the two output blocks (red, green) + a one-sentence conclusion. No real output,
  no conclusion.
