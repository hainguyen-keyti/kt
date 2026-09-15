---
description: "Close the session: save handoff, decisions, lessons; run the gate; commit per repo rules"
---

End the session in exactly this order (a repo without `docs/agent/` skips steps 1-4 and 6: only
gate, commit, push, REPORT):

1. Collect parked questions FIRST: if the "Parked questions" section of HANDOFF still has
   unresolved lines, ask the user in one round following the `/kt:ask` ritual right now (the
   answers can create more work; this way the later steps run only once). Then update
   `docs/agent/HANDOFF.md`: what was just done, branch state, verify commands, next steps, newly
   hit traps, the "Active plan" section if a plan is active. Keep it short: HANDOFF is a handoff
   note, not a diary; delete stale entries (the detailed history is already in git log). Measure
   `wc -c docs/agent/*.md` and cut stale HANDOFF entries: the bootstrap block is reread on every
   turn of the next session (moving "Decided" entries out of the injected block into an archive
   was proposed and rejected).
2. Durable decisions settled in the session: record them in `docs/agent/DECISIONS.md` under
   "Decided" (date + reason). Proposals the user turned down: under "Rejected". New questions
   with no answer yet: under "Open decisions".
3. Lessons paid for in the session (the mistake stepped on, the cause, the right way): record
   them following exactly the `/kt:lesson` ritual (it detects on its own a lesson repeated a
   second time, to promote it into a rule or hook).
4. New access information that came up in the session (a server, a service URL, a new env var, a
   new key location): record it in `docs/agent/ACCESS.md` following exactly the rules at the top
   of that file (only the location and how to get in; if the user pasted a value, do not copy it
   and remind them to rotate).
5. If the session changed code: run the repo's FULL GATE (the `Full gate:` line in the repo's
   CLAUDE.md, for example `pnpm check`) and paste the REAL result, UNLESS the latest EVIDENCE in
   the session already recorded a green full gate at exactly the current HEAD with a clean tree
   (check `git rev-parse --short HEAD` and an empty `git status --porcelain`): then reuse that
   line and do not run it a second time. If the gate is red, report red; no "consider it done"
   closing. The quick gate is only for use while coding; it cannot replace the full gate here.
6. Active plan (`.claude/active-plan` exists): scope audit and acceptance:
   - Run the machine audit inside the repo (the audit climbs up to find the marker), paste the
     output:

     ```
     KT=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['kt@kt'][0]['installPath'])")
     python3 "$KT/hooks/no-offplan-edit.py" --audit
     ```

     Declare every deviating file under UNSURE in the REPORT with a reason; never quietly
     legitimize it. Gitignored areas are outside both the fence and the audit: do not report as
     if they were covered.
   - Once the plan passes acceptance (acceptance green, user confirmed): remove the fence with
     `rm .claude/active-plan`, THEN paste the measurements into the plan's `## Evidence` section
     (the fence locks the plan during execution, so it must come down before the plan can be
     written).
7. Commit the CODE changes in slices, each with a one-sentence English message. The agent layer
   (CLAUDE.md, `docs/agent/`, `.claude/`) is machine-local and untracked: do NOT commit it, no
   `git add -f`. A legacy repo that really still TRACKS the agent layer
   (`git ls-files --error-unmatch docs/agent/PROJECT.md` exits 0) commits those files like
   ordinary files under the grandfather rule, without removing the tracking on its own. Agent
   files that are NOT tracked and also NOT ignored (usually from restoring a backup without
   `.git/info/exclude`): STOP and ask the user to rebuild the exclude; never commit a new agent
   layer. After committing: write the new HEAD sha into the "Where we are" section of HANDOFF.md
   (the standard set's stop gate blocks every stop when the session has a commit newer than
   HANDOFF, so the ledger must be newer than the last commit). Then back up the ENTIRE
   machine-local agent layer (making up for its lack of git history), UNLESS you are in a lane
   worktree (`git rev-parse --git-dir` differs from `--git-common-dir`): a lane does NOT back up,
   because `rsync --delete` from a lane would overwrite the main checkout's copy with the lane's
   HANDOFF and dangling symlinks.

   ```
   mkdir -p ~/kt-backups/<repo-name>
   [ -d docs/agent ] && rsync -a --delete docs/agent/ ~/kt-backups/<repo-name>/docs-agent/
   [ -f CLAUDE.md ] && rsync -a CLAUDE.md ~/kt-backups/<repo-name>/
   [ -d .claude ] && rsync -a --delete --exclude worktrees/ .claude/ ~/kt-backups/<repo-name>/dot-claude/
   ```
8. Push: `git pull --rebase` then `git push` until up to date with origin (the machine-wide
   end-of-session rule; a branch without an upstream, such as a new lane, uses
   `git push -u origin HEAD`), UNLESS the repo explicitly forbids auto-push: then stop at the
   commit and say plainly that it has not been pushed.
9. Final report in EXACTLY the REPORT block of `/kt:report`, 8 fixed sections: STATE, DONE,
   EVIDENCE, DECIDED, BLOCKED, WAITING_ON, UNSURE, NEXT. The full format and rules of the block
   live in that command and are not copied here so they cannot drift (test_hooks.py checks that
   the section names stay in sync). A reminder of the three most-forgotten rules: an empty
   section says `none`, DONE must carry a sha, EVIDENCE is real output. If this session was
   assigned work by another agent, send the block back to that agent with SendMessage.
