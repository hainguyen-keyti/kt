#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash and PowerShell): one-way shell commands stop at a human.

Promoted into kt from a machine-local guard.ps1 that paid for each rule. Two tiers:
- HARD (exit 2, the call is refused and the agent is told to hand the command to the user):
  a force-push, `git reset --hard`, `git clean -f`, a commit or push that skips the repo's own
  hooks (`--no-verify`), formatting a drive, PowerShell disk and partition cmdlets.
- ASK (JSON `permissionDecision: ask`, the user sees the normal prompt): a recursive delete whose
  target is an absolute path, a home path or a parent (`..`), `rd /s`, `del /s`, a table or
  database drop or truncate, `kubectl delete`.
Deletes that stay inside the repo or under a `$TMPDIR` variable pass, so worktree and scratch
cleanup is not interrupted.
The match is on the command text, like every shell guard: text quoted after `-m`/`--message`
(a commit message that mentions a hard reset) is stripped before matching, but a heredoc or an
`echo` that spells a forbidden command still trips the hard tier; rephrase or let the user run it.
Unreadable payload: exit 0, like the other hooks. An internal error exits 2: a destructive guard
that dies must be noticed, not stepped around. `KT_ALLOW_DESTRUCTIVE=1` in the claude process
environment disables the hook for the whole session, and the session banner says so.
"""
import json
import os
import re
import sys

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    # Claude Code hands hooks UTF-8 whatever the Windows locale says: read and answer in UTF-8.
    _stream.reconfigure(encoding="utf-8", errors="replace")

MESSAGE_RE = re.compile(r"""(?:^|\s)(?:-m|--message)(?:=|\s+)(?:"[^"]*"|'[^']*')""")
HARD = [
    (re.compile(r"\bgit\b[^|;&]*\bpush\b[^|;&]*(?:--force(?:-with-lease)?\b|\s-[a-zA-Z]*f[a-zA-Z]*\b|\s\+\S+)"), "git force-push"),
    (re.compile(r"\bgit\b[^|;&]*\breset\b[^|;&]*--hard\b"), "git hard reset (uncommitted work is lost)"),
    (re.compile(r"\bgit\b[^|;&]*\bclean\b[^|;&]*\s-[a-zA-Z]*f"), "git clean -f (untracked files are deleted)"),
    (re.compile(r"(?:^|\s)--no-verify\b"), "a commit or push that skips the repo's own hooks (the verify flag)"),
    (re.compile(r"\bformat(?:\.com)?\s+[a-zA-Z]:", re.I), "formatting a drive"),
    (re.compile(r"\b(?:Format-Volume|Clear-Disk|Remove-Partition|Initialize-Disk)\b", re.I), "a disk or partition operation"),
]
DANGEROUS_TARGET = r"(?:/|~|[A-Za-z]:|\\\\|\$HOME\b|\$env:|\S*\.\.)"
ASK = [
    (re.compile(r"\brm\b[^|;&]*\s-(?:-recursive\b|[a-zA-Z]*r)[^|;&]*\s['\"]?" + DANGEROUS_TARGET), "rm -r aimed at an absolute, home or parent path"),
    (re.compile(r"\b(?:Remove-Item|ri|rmdir|rd|del|erase)\b[^|;&]*\s-(?:Recurse|r)\b[^|;&]*(?:\s|['\"])" + DANGEROUS_TARGET, re.I), "Remove-Item -Recurse aimed at an absolute, home or parent path"),
    (re.compile(r"\b(?:rd|rmdir)\s+/s\b", re.I), "rd /s (recursive delete)"),
    (re.compile(r"\bdel\b[^|;&]*\s/s\b", re.I), "del /s (recursive delete)"),
    (re.compile(r"\b(?:DROP|TRUNCATE)\s+(?:TABLE|DATABASE|SCHEMA)\b", re.I), "a table, schema or database drop or truncate"),
    (re.compile(r"\bkubectl\s+delete\b"), "kubectl delete"),
]


def ask(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "no-destructive: " + reason + ". Confirm the target before allowing."}}))
    return 0


def main():
    if os.environ.get("KT_ALLOW_DESTRUCTIVE") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return 0
    text = MESSAGE_RE.sub(" ", command)
    for pattern, reason in HARD:
        if pattern.search(text):
            sys.stderr.write("BLOCKED by no-destructive: " + reason + ". Explain to the user why it is needed and let them run it themselves if they agree; a one-way command is not the agent's to take.\n")
            return 2
    for pattern, reason in ASK:
        if pattern.search(text):
            return ask(reason)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write("no-destructive: internal error, refusing the call so the guard is noticed: " + type(exc).__name__ + ": " + str(exc)[:120] + "\n")
        sys.exit(2)
