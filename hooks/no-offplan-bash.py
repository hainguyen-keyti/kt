#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash): two guards while a plan is active, nothing else.

The plan fence proper lives in no-offplan-edit.py (Write/Edit/NotebookEdit) and in its
--audit mode, which /kt:go runs before every commit and /kt:save runs at the end: shell
writes outside the radius surface there, one step later, against git. This hook does not check
shell writes against the radius (a parser that tried flagged heredoc bodies and arrows while
python, perl, patch and npm slipped through), so it keeps only what the audit cannot undo:
1. the live marker `.claude/active-plan` must not be overwritten or moved through the shell
   (arm and re-arm go rm-then-create; `rm` stays allowed as the sanctioned exit);
2. the directory of the active plan must not be written through the shell (no widening the
   radius from the side).
A command counts as a write for these guards when it names the path and also carries a
writing shape (`>`, `>>`, `tee`, `sed -i`, `cp`, `mv`, `install`, `touch`, `truncate`, `dd`,
`git mv`). No marker up from the cwd: silent. Marker broken: the marker guard still holds.
Broken JSON payload: let through. A crash fails closed only while a marker is active.
Escape: KT_ALLOW_OFFPLAN=1 in the claude process environment (whole session; the banner says so).
"""
import importlib.util
import json
import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kt_fence", os.path.join(HERE, "no-offplan-edit.py"))
fence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fence)

MARKER = fence.MARKER_REL.replace(os.sep, "/")
WRITE_SHAPE_RE = re.compile(r"(?<![<>])>{1,2}(?!&)|\btee\b|\bsed\b[^|;&]*\s-i|\b(?:cp|mv|install|touch|truncate|dd)\b|\bgit\s+mv\b")


def deny(message):
    sys.stderr.write("BLOCKED by plan fence (shell): " + message)
    return 2


def scan(payload):
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    root = fence.find_root(os.path.join(cwd, "_"))
    if root is None or not WRITE_SHAPE_RE.search(command):
        return 0
    if MARKER in command:
        return deny("overwriting or moving the live marker '.claude/active-plan' is not re-arm; re-arm goes rm-then-create, in a separate command, after user approval.\n")
    loaded, matchers = fence.load_fence(root)
    if matchers is None:
        return 0
    plans_dir = fence.plans_dir_of(loaded)
    if plans_dir and (plans_dir + "/") in command:
        return deny("'" + plans_dir + "/' holds the active plan; not writable while armed, whatever the radius says. Shell writes elsewhere are not fenced here but surface in the audit before each commit.\n")
    return 0


def main():
    if os.environ.get("KT_ALLOW_OFFPLAN") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        return scan(payload)
    except Exception as exc:
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        if fence.find_root(os.path.join(cwd or os.getcwd(), "_")) is None:
            return 0
        return fence.deny("shell guard crashed (" + type(exc).__name__ + ": " + str(exc)[:200] + ") while a plan is active; failing closed, rephrase the command or ask the user.\n")


if __name__ == "__main__":
    sys.exit(main())
