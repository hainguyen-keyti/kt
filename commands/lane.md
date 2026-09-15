---
description: Open a parallel work lane (worktree + its own branch) with the agent layer in place and shared state that does not drift
---

Open a parallel lane for the current repo: $ARGUMENTS (expected: a lane name, for example
`referral-update`; if empty, ask the user what to name it and what work it is for).

The problem this command solves: a new worktree has NO agent layer (it is machine-local and does
not travel with git), and copying it straight over gives each lane its own `DECISIONS.md` that
drifts apart within a few hours. The right way: whatever is shared gets a SYMLINK back to the main
checkout, whatever belongs to one lane gets copied.

## Step 1: check prerequisites

- You must be in the MAIN checkout (not inside another worktree): `git rev-parse
  --git-common-dir` and `--git-dir` must be identical.
- The lane name must be valid for a git branch: no spaces, ASCII only. If the name the
  user gives is invalid, convert it to kebab-case yourself and TELL the user what it became.
- The repo must already have the standard set (`docs/agent/` and
  `.claude/hooks/session-start.sh` exist); if not, run `/kt:adopt` first, because step 4 verifies
  with that very hook.
- Agent layer tracked or machine-local: `git check-ignore -q docs/agent/PROJECT.md` and
  `git check-ignore -q .claude/hooks/session-start.sh`. If NEITHER is ignored (the repo tracks the
  agent layer), the worktree gets the files through git on its own: skip step 3, do only step 4.
  If one is ignored and the other is not: ask the user, do not guess.

## Step 2: create the worktree

```
git worktree add .claude/worktrees/<lane> -b <lane>
```

The default directory is `.claude/worktrees/`; if the repo already has another convention for
worktrees, follow that convention. The branch grows from the current HEAD; if the user wants a
different base, ask first.

## Step 3: build the agent layer in the lane (only when the agent layer is machine-local)

First run `mkdir -p docs/agent/plans` in the main checkout (a repo that has never run /kt:plan does
not have the directory yet, and the symlink would dangle). Then SYMLINK back to the main checkout,
preferring RELATIVE paths so moving the repo does not break them (macOS has no `ln -sr`, so compute
the relpath yourself; absolute paths are acceptable if the repo will not move). Shared, edited in
one place and seen by every lane:
`CLAUDE.md`, `docs/agent/PROJECT.md`, `DECISIONS.md`, `LESSONS.md`, `ACCESS.md`, and the whole
`docs/agent/plans/` directory (a plan must not vanish when the worktree is removed).

Symlinks are for READING. The harness refuses Write/Edit through a file symlink ("Refusing to write
through symlink"): to write a shared file, get the real path with `readlink -f <file>` and
Write/Edit that path (writing through the `plans/` directory symlink works normally). The ONE WRITER
PER CHECKOUT rule applies only to CODE files: a lane edits code only inside its own worktree; the
shared ledgers (DECISIONS, LESSONS, ACCESS, PROJECT, plans) belong to everyone, are written through
the real path, and are mostly appended to.

COPY (per lane, must differ between lanes):
- `docs/agent/HANDOFF.md`: write it NEW for the lane, with a "WHAT THIS LANE IS" section at the top
  recording: lane name, branch, the base it grew from, what the main checkout is working on, the
  one-writer rule for code, and not touching another checkout's active plan through the `plans/`
  symlink; then every section of the standard HANDOFF (Where we are, Verify commands, Next steps,
  Known traps, Parked questions, Active plan) so go/save/load find the right places.
- Install dependencies for the lane (node_modules and equivalents do not come with git): run the
  repo's install command (CLAUDE.md, section Standard commands) in the lane before verifying.
- Gates in the lane: while working, run only the repo's QUICK GATE (the `Quick gate:` line in
  CLAUDE.md); the FULL GATE (the `Full gate:` line) once at the end of the work, before REPORT,
  recording the sha and the count line in EVIDENCE; the whole-tree gate on the main branch is run
  by the coordinator at merge time (section Merge and clean up the lane). With several agents in ONE
  worktree this is mandatory: each agent runs only the tests for exactly the files it changed, and
  the whole-tree gate (tsc, full test) is run once by the coordinator on a tree nobody is editing, because a
  whole-tree gate reads other agents' half-done state (already hit: `Cannot find name` while
  another agent had inserted a call but not yet the import).
- Lane ceiling per machine, declared by the repo in CLAUDE.md (for example 3 heavy lanes with a
  browser or dev server, 6 in total, sized to its RAM): before opening a lane, check `uptime`
  (1-minute load) against `sysctl -n hw.ncpu` (macOS) or `nproc`; if load exceeds the core count,
  do not open another. CPU-heavy tests or tests that spawn child processes need their own timeouts,
  because a loaded machine makes a test with a 5-second timeout flaky and it gets rerun.
- `.claude/settings.json` and `.claude/hooks/`: copy (not symlink, so a lane that breaks a hook
  does not drag every other lane down with it).
- Do NOT copy `.claude/active-plan`: the fence belongs to the plan; each lane arms its own plan
  with `/kt:plan`.
- `.claude/launch.json` if present: copy it, then CHANGE THE PORT: offset = 10 times the number of
  existing lanes including the one just created in step 2 (`git worktree list | wc -l` minus 1);
  for the first lane 5173 becomes 5183, the second lane gets 5193. If the repo has ever REMOVED a
  lane, the count drops and can hand out a port already in use: check `lsof -i :<port>` before
  settling on it. Record the new port in the lane's HANDOFF. Port collisions are the most common
  failure when running in parallel.

## Step 4: verify; report done only when all five cases pass

1. `git -C <lane> status --porcelain` must be EMPTY (the agent layer must not show up).
2. `git -C <lane> branch --show-current` matches the lane name.
3. Real hook run in the lane: `CLAUDE_PROJECT_DIR=<lane-abs> sh <lane>/.claude/hooks/session-start.sh`
   must print the bootstrap and READ the content through the symlinks (grep finds a string from
   PROJECT.md and the "WHAT THIS LANE IS" string from HANDOFF). The tracked case skips step 3, so
   there is no "WHAT THIS LANE IS" section: there this case only requires grep to find a string
   from PROJECT.md.
4. Control case: the same script with `CLAUDE_PROJECT_DIR=/tmp` must exit 0 silently.
5. Really run ONE of the repo's test commands in the lane (a verify command from HANDOFF): it must
   run to a result, not "command not found" (a worktree missing dependencies is the first failure
   you hit when actually running in parallel).

## Step 5: hand off

Print for the user exactly one command to open a session in the lane:
`cd <lane-path> && claude`. Remind the user that a new lane needs `/kt:load` as its first message,
that `/kt:save` in the lane pushes with `git push -u origin <lane>` (the branch has no upstream
yet) and does not back up to ~/kt-backups (the backup belongs to the main checkout).

## Merge and clean up the lane when the work is done

Merge into the main branch (the coordinator, from the main checkout): rebase the lane onto the main
branch; if the main branch has moved on since the lane ran its full gate, run the FULL GATE exactly
once on the rebased branch, and if it has not, reuse the lane's full gate EVIDENCE at the same sha
(check the sha and a clean tree); fast-forward; push; do not run it a second time on the main
branch at the same sha. Several lanes at once: you may merge the whole batch, then run the full gate
ONCE on the final main branch and bisect by lane if it is red, because each lane's full gate has
already blocked most of the risk.

Once merged and no longer needed: `git worktree remove <lane>` then `git branch -d <lane>`. Losing
the lane's own HANDOFF with it is CORRECT (it is temporary state); everything worth keeping already
lives in the shared DECISIONS, LESSONS, plans, and in the git history of the merged branch.
