---
description: "Measure the weighted cost of a session and its subagents from the transcript: cache read 0.1, cache write 2, output 5; never trust self-reported numbers"
---

Measure the real cost of the current session (or the session/transcript the user names in
$ARGUMENTS) from the transcript on disk, because the token counts an agent reports about itself
(`subagent_tokens`, the end-of-session total) are 5-8 times lower than the weighted cost (measured
on a repo using kt), and because the most expensive component, rereading the context on every
turn, shows up nowhere (59% of one measured 1219-turn session).

Use it at phase milestones, when the user asks about quota, or when choosing between two approaches
(a one-command script versus 20 manual turns). The command only READS transcripts and prints
numbers; it never prints chat content.

## How to run

1. Write the script below to a temp file (`mktemp`) and run
   `python3 <file> [session-id | path to .jsonl]` from the repo directory. With no argument it
   picks the NEWEST transcript under `~/.claude/projects/*/` whose `cwd` field equals the current
   directory (do not guess the folder slug from the repo path: the project folder name cannot be
   reliably derived back from the path, while the `cwd` field is exact). The `KT_COST_PROJECTS`
   variable changes the projects root directory (used by tests).
2. Read the result: the weighted total, its three components (cache read, cache write, output),
   the average context per turn, and the top subagents. Paste it into EVIDENCE if you are reporting.
3. Weights follow Anthropic pricing relative to plain input = 1: cache read 0.1; cache write 2
   (1-hour TTL, the transcript records `ephemeral_1h_input_tokens`); output 5. If prices change,
   edit `W` in the script.

Reading the numbers: the average context per turn times 0.1 is the cost of rereading per turn; if
that is many times the output cost per turn, the lever is FEWER TURNS and LESS CONTEXT (a script
that prints a table instead of many manual commands, a gate script that prints only the red part,
`/kt:save` then `/clear` at each milestone), not writing shorter.

## Script

```
#!/usr/bin/env python3
"""Weighted cost of one Claude Code session and its subagents, read from the JSONL transcripts.
One API response is written as several lines sharing message.id, so usage is taken once per id."""
import glob
import json
import os
import sys

W = {"cache_read_input_tokens": 0.1, "cache_creation_input_tokens": 2.0, "output_tokens": 5.0, "input_tokens": 1.0}
LABEL = {"cache_read_input_tokens": "cache read", "cache_creation_input_tokens": "cache write", "output_tokens": "output", "input_tokens": "input"}
PROJECTS = os.environ.get("KT_COST_PROJECTS") or os.path.expanduser("~/.claude/projects")


def usage_by_id(path):
    last = {}
    with open(path, errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            m = d.get("message") or {}
            if d.get("type") == "assistant" and isinstance(m.get("usage"), dict):
                last[m.get("id")] = m["usage"]
    return last


def totals(path):
    per = usage_by_id(path)
    parts = {k: sum(u.get(k, 0) or 0 for u in per.values()) for k in W}
    return sum(parts[k] * w for k, w in W.items()), len(per), parts


def first_cwd(path):
    with open(path, errors="replace") as f:
        for i, line in enumerate(f):
            if i > 20:
                break
            try:
                cwd = json.loads(line).get("cwd")
            except ValueError:
                continue
            if cwd:
                return os.path.realpath(cwd)
    return ""


def pick(arg):
    if arg and os.path.isfile(arg):
        return arg
    candidates = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    if arg:
        candidates = [p for p in candidates if os.path.basename(p)[:-6] == arg]
    else:
        here = os.path.realpath(os.getcwd())
        candidates = [p for p in candidates if first_cwd(p) == here]
    if not candidates:
        sys.exit("no transcript found (cwd match or session id); pass a .jsonl path")
    return max(candidates, key=os.path.getmtime)


def fmt(n):
    return "{:,.0f}".format(n)


def main():
    session = pick(sys.argv[1] if len(sys.argv) > 1 else "")
    weighted, turns, parts = totals(session)
    context = parts["cache_read_input_tokens"] + parts["cache_creation_input_tokens"] + parts["input_tokens"]
    print("session " + os.path.basename(session)[:-6] + " (" + session + ")")
    print("  turns: " + str(turns) + "   weighted: " + fmt(weighted) + "   avg context/turn: " + fmt(context / max(turns, 1)))
    print("  " + " | ".join(LABEL[k] + " " + fmt(parts[k] * W[k]) + " (" + "{:.1f}".format(100 * parts[k] * W[k] / weighted if weighted else 0) + "%)" for k in W))
    subs = []
    for p in glob.glob(os.path.join(session[:-6], "subagents", "*.jsonl")):
        e, n, _ = totals(p)
        subs.append((e, n, os.path.basename(p)))
    subs.sort(reverse=True)
    print("subagents: " + str(len(subs)) + ", weighted " + fmt(sum(s[0] for s in subs)))
    for e, n, name in subs[:10]:
        print("  " + fmt(e).rjust(12) + "  " + str(n).rjust(4) + " turns  " + name)


if __name__ == "__main__":
    main()
```
