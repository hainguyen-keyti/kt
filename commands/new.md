---
description: "Set up the agent standard for a NEW project: interview first, generate every file from the embedded templates, verify. Self-contained, needs no outside file"
---

Set up the agent standard for the CURRENT repo (a new or nearly empty project). This command is
SELF-CONTAINED: every file template is right below, nothing is read from anywhere else. Principle:
interview first, generate files from real answers, never fill a gap the user has not answered with
a guess.

## Step 1: INTERVIEW (no file created yet)

Ask the user in clusters, each question with a suggested default for a quick pick, covering:

1. What the project is and who it is for, in 1-2 sentences.
2. Stage: pre-launch (no real users yet) or live? Settle the consequences from it: pre-launch means
   data is test data that can be reset, no backward compatibility, no migration ceremony; live
   means the exact opposite on every point.
3. Stack and standard commands: install, test, lint, run locally, and TWO gate commands: the "quick
   gate" runs only the part related to the changed files (lint and format on changed files,
   typecheck of the touched unit, related tests via the repo's own tool such as `vitest related`,
   `jest --findRelatedTests`, `pytest <path>`, `go test ./pkg/...`) and the "full gate" is the
   repo's complete gate. A repo without a related-tests tool uses the same command for both, and
   still declares both lines. An empty repo: ask what it plans to use.
4. Three permission levels: allowed without asking / ask first / forbidden.
5. Out of scope: what is deliberately NOT done at this stage.
6. Repo-specific rules if any, each with a one-sentence reason.
7. Access: which servers, which outside services (staging, dashboards, databases), where secrets
   live (env file path, keychain or password-manager item name). Ask ONLY for location and how to
   get in, NEVER for a secret value; if the user pastes a value anyway, say that a key pasted into
   a chat counts as burned and must be rotated.

## Step 2: BUILD (fill the templates below with the real answers)

If the folder is not a git repo yet, run `git init` first. Create exactly these files. Every section
named below is a level-2 heading (`## <name>`): the hooks and the commands look sections up by these
exact names.

### File `CLAUDE.md` (repo root, keep it under 100 lines)

Template content:
- Project name plus 1-2 sentences on what it is (from question 1).
- Mandatory paragraph: "State and context live in `docs/agent/`. AT THE START OF EVERY SESSION:
  read `docs/agent/PROJECT.md` and `docs/agent/HANDOFF.md` before doing anything, restate them for
  the user to confirm, then start (or the user types /kt:load). AT THE END OF THE SESSION: update
  `docs/agent/HANDOFF.md` (or the user types /kt:save)."
- Section "Standard commands": the commands from question 3, one per line, including the two fixed
  lines `Quick gate: <command>` and `Full gate: <command>` (go, save and lane of kt refer to exactly
  these two names).
- Section "Allowed / Ask first / Forbidden": the three lists from question 4, named explicitly.
- Section "Working rules": one fixed sentence "The shared working rules (scope, tests, verification,
  parked questions, git) are injected by the kt plugin at the start of every session in the
  `=== kt rules ===` block; this file only keeps the rules SPECIFIC to this repo, and a repo rule
  wins on conflict", then the repo-specific rules from question 6 (each with a one-sentence reason).
  Do not copy the shared rules here: two copies drift.
- When detailed rules (style, folder layout, error handling, test conventions) push CLAUDE.md past
  about 100 lines: move them to `docs/CONVENTIONS.md` and point to it, CLAUDE.md keeps only short
  hard rules. A rule a machine can check becomes a lint rule or a hook instead of another sentence.

### File `docs/agent/PROJECT.md`

Template: title "PROJECT.md: static context (the agent reads it at the start of every session)";
section "What this is" (question 1); section "Current stage and consequences" (question 2, each
consequence on its own line, obeyed absolutely by the agent, plus the line "a stage change means
rewriting this whole section"); section "Architecture on one screen" (fill once there is code, an
empty repo writes "none yet"); section "Out of scope" (question 5); section "Environments" (a table
of local / staging / production: which exist, how they deploy, which are user-gated).

### File `docs/agent/DECISIONS.md`

Four sections, with a behavior note at the top of the file:
"Section 1, decided: never reopen, never ask again. Section 2, rejected: never propose again.
Section 3, deferred with a due date: decided to postpone; once due and unpaid, the agent must raise
it on its own. Section 4, open decisions: never decide on your own; when you run into one, ask the
user with a recommendation; labels [BLOCKS MERGE] / [NON-BLOCKING] give urgency, and an area label
(security, money) means a second-opinion must be invited before the user settles it."
- Section "1. Decided": table Date | Decision | Reason. Record right away what the user settled in
  the interview (stage, stack, permissions).
- Section "2. Rejected": table Date | Proposal | Why. Leave empty if none.
- Section "3. Deferred with a due date": table Item | Where | Paid where, due when. Leave empty if
  none.
- Section "4. Open decisions": a numbered list of the questions the user could not answer in the
  interview.

### File `docs/agent/HANDOFF.md`

Template: title "HANDOFF.md: live state (updated at the end of every session)"; the line
"Last updated: <date> (initial setup)"; section "Where we are" (just set up, no code added yet);
section "Verify commands" (test commands from question 3); section "Next steps" (the first thing
the user plans to do); section "Known traps" (empty); section "Parked questions" (non-blocking
ambiguities written down to ask in one batch later, empty); section "Active plan" (append one line
when EACH task is DONE, in the form `- [x] T<n> <name> | <command>: <result>`; never pre-populate
the task list, leave it empty). Note at the top of the file: "This file is a handoff note, not a
diary; delete stale items, history already lives in git log; write feature or task ids IN FULL
(M3-F9, not F9: short ids collide across milestones and grep returns the wrong one)."

### File `docs/agent/LESSONS.md`

Template: title "LESSONS.md: project lessons (read before similar work)"; note: "Each lesson is 1-3
lines: what happened, the cause, the right way, with an absolute date. A lesson that repeats a
second time is promoted to a rule in CLAUDE.md or to a hook, then deleted from here. Keep this file
under 40 lines." The list starts empty.

### File `docs/agent/ACCESS.md`

Template: title "ACCESS.md: the project's access map (NEVER holds a secret value)"; rule at the top
of the file: "This file only holds paths, names and how to get in. Secret values (keys, passwords,
tokens) live in a gitignored env file or a key file: write the LOCATION, never the value. If the
repo may become public, move sensitive hosts to a gitignored ACCESS.local.md."; four sections, filled
from question 7:
- "Servers and infrastructure": table What | Command to get in | Where the key lives.
- "Services and URLs": table What | URL | How to sign in (the password-manager item name, never the
  value).
- "Where secrets live": table Name | Location (path or keychain item) | Used for | Least privilege.
- "Quick checks": one harmless verify command per access, such as ssh 'echo ok' or curl /health, so
  a later session checks the access is alive instead of asking the user again.

### File `.claude/hooks/session-start.sh` (chmod +x after creating it)

```
#!/bin/sh
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
[ -d docs/agent ] || exit 0
mkdir -p .claude && touch .claude/session-start
echo "=== docs/agent bootstrap (injected by the SessionStart hook) ==="
echo "kt-skeleton 1.0.2 (version of the kt plugin that wrote these hooks; /kt:load compares it with the installed plugin)"
echo "If this block reached you as a <persisted-output> preview, Read the saved file named in it in full before restating anything: the preview is not the files."
echo "Before doing anything else: restate to the user, in one short paragraph, the project stage and its consequences, the current state, the open decisions, and the next step, based on the files below. Respect the stage consequences absolutely. Items under '4. Open decisions' in DECISIONS.md must not be re-decided or re-proposed. Do not start coding until the user confirms."
for f in docs/agent/PROJECT.md docs/agent/HANDOFF.md docs/agent/DECISIONS.md docs/agent/LESSONS.md docs/agent/ACCESS.md; do
  if [ -f "$f" ]; then
    echo ""
    echo "--- $f ---"
    cat "$f"
  fi
done
exit 0
```

### File `.claude/hooks/stop-gate.py`

A machine stop gate with two checks and no trust in self-report. One, on EVERY stop: if a commit was
made in this session (newer than the `.claude/session-start` stamp that session-start.sh touches at
every session start) and `docs/agent/HANDOFF.md` is older than that commit, block, so a session that
ends quietly cannot leave the ledger behind; HANDOFF counts as fresh at max(mtime, time of the last
commit touching it) so a repo that tracks its ledger is not blocked by mistake. Two, when the
agent's last message carries the `## REPORT` block (the handoff signal): HANDOFF must also be newer
than the session stamp and, with an active plan, the kt audit must pass. A repo without docs/agent,
or the second stop after a block (`stop_hook_active`), passes. The session stamp is touched again on
every app resume, so a commit made before the last resume is no longer caught by check one.

```
#!/usr/bin/env python3
"""Stop gate, two machine checks, no self-report trusted.
1. Any stop: a commit made in this session (newer than .claude/session-start) that is newer than
   docs/agent/HANDOFF.md blocks, so a silent session cannot leave the ledger behind. HANDOFF counts
   as fresh at max(mtime, time of the last commit touching it), which keeps tracked ledgers honest.
2. A handoff (last assistant message carries the REPORT block): HANDOFF.md must also be newer than
   the session stamp and, with an active plan, the kt fence audit must pass.
Everything else passes through."""
import json
import os
import subprocess
import sys


def git_time(*args):
    try:
        proc = subprocess.run(["git", "log", "-1", "--format=%ct", *args], capture_output=True, text=True)
        return int(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else 0
    except Exception:
        return 0


def stale_after_commit(stamp, handoff):
    if not os.path.isfile(stamp) or not os.path.isfile(handoff):
        return False
    head = git_time()
    if not head or head <= os.path.getmtime(stamp):
        return False
    return max(os.path.getmtime(handoff), git_time("--", handoff)) < head


def last_assistant_text(path):
    last = ""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                content = (obj.get("message") or {}).get("content") or []
                text = "".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
                if text.strip():
                    last = text
    except OSError:
        return ""
    return last


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    os.chdir(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
    if not os.path.isdir("docs/agent"):
        return 0
    problems = []
    stamp = os.path.join(".claude", "session-start")
    handoff = os.path.join("docs", "agent", "HANDOFF.md")
    if stale_after_commit(stamp, handoff):
        problems.append("docs/agent/HANDOFF.md is older than a commit made in this session: update it (current state with the HEAD sha, next step, plan progress) before stopping.")
    if "## REPORT" in last_assistant_text(payload.get("transcript_path") or ""):
        if os.path.isfile(stamp) and os.path.isfile(handoff) and os.path.getmtime(handoff) < os.path.getmtime(stamp):
            problems.append("docs/agent/HANDOFF.md is older than this session's start: update it (what was done, durable decisions mirrored into DECISIONS.md, current state, next step, known traps, plan progress) before handing off.")
        if os.path.isfile(os.path.join(".claude", "active-plan")):
            try:
                reg = json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json"), encoding="utf-8"))
                kt = reg["plugins"]["kt@kt"][0]["installPath"]
                audit = subprocess.run([sys.executable, os.path.join(kt, "hooks", "no-offplan-edit.py"), "--audit"], capture_output=True, text=True)
                if audit.returncode != 0:
                    problems.append("plan fence audit failed, fix or report each file in UNSURE before handing off:\n" + audit.stdout.strip())
            except Exception as exc:
                problems.append("plan fence audit could not run (" + type(exc).__name__ + "); run it by hand and report the output.")
    if problems:
        sys.stderr.write("STOP GATE (docs/agent): " + "\n".join(problems) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### File `.claude/settings.json` (if it already exists, MERGE, never overwrite existing keys)

```
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact|fork",
        "hooks": [
          {
            "type": "command",
            "command": "sh \"$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/stop-gate.py\""
          }
        ]
      }
    ]
  }
}
```

Mandatory technical note: SessionStart must be a command hook as above, NEVER a prompt hook
(SessionStart does not support it and the session reports an error on open). The stop gate is a
command hook because a prompt hook only reads the closing message, so "HANDOFF is updated" would be
a self-report; the machine checks mtime and the audit instead.

## Step 3: VERIFY before reporting done

1. `chmod +x .claude/hooks/session-start.sh`, then really run both cases: inside the repo
   `CLAUDE_PROJECT_DIR=$(pwd) sh .claude/hooks/session-start.sh` must print the bootstrap and the
   content of the docs/agent files and create the `.claude/session-start` stamp; with
   `CLAUDE_PROJECT_DIR=/tmp` it must stay silent and exit 0. Stop gate: `echo '{}' | CLAUDE_PROJECT_DIR=$(pwd)
   python3 .claude/hooks/stop-gate.py` must exit 0 (no REPORT and no commit in the session means it
   does not bite). The `kt-skeleton <version>` line in session-start.sh keeps the version of the kt
   plugin installed at setup time: it is the stamp that lets /kt:load tell a repo runs an old
   skeleton.
2. Parse `.claude/settings.json` (for example `python3 -c "import json; json.load(open('.claude/settings.json'))"`).
3. THE AGENT LAYER IS MACHINE-LOCAL AND NEVER COMMITTED: write these four lines into
   `.git/info/exclude` (NOT `.gitignore`, so nothing is pushed anywhere or visible in the repo):
   `CLAUDE.md`, `AGENTS.md`, `.claude/`, `docs/agent/`. Verify with `git check-ignore -v` on each
   path (it must point to info/exclude or a machine-level rule) AND `git status --porcelain` must
   not list any file of the standard; use `check-ignore` because `git status` and `git add` stay
   silent when a file is swallowed.
4. Do NOT commit or push any file of the standard. Never use `git add -f`. Other repo files (if any
   were changed) are committed separately as usual, and only once approved.
5. Report: the list of files created, the decisions recorded in DECISIONS.md, and invite the user to
   open a new session and type `/kt:load` as acceptance: it must correctly restate the project just described.
