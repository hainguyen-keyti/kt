#!/usr/bin/env python3
"""PreToolUse hook: block Write/Edit content containing em dash or clause-break en dash.

Reads the tool call JSON on stdin. Exit 2 blocks the write and feeds stderr back to the
model so it rewrites without the banned characters. An en dash is a clause break when it
stands alone between whitespace or at a line edge; ranges like 1-5 with an en dash pass.
Also wired on Bash, where it scans only commands containing 'commit', so commit messages
cannot smuggle the dash into git history. Lines that mention the words 'em dash' or 'en
dash' are exempt (rule files legitimately quote the characters). Relocation carve-out:
an offending line that already exists in the tracked working tree of the target file's
repo may be written again (moving existing text is not writing new text); Bash commit
messages get no carve-out. KT_ALLOW_EMDASH=1 must sit in the environment of the claude
process (it disables this hook for that whole session; restart to apply); an agent cannot
set it for its own tool call. The dash characters are built with chr() so this file
itself passes the hook.
"""
import json
import os
import re
import subprocess
import sys

EM_DASH = chr(0x2014)
EN_DASH_BREAK_RE = re.compile("(^|\\s)" + chr(0x2013) + "(\\s|$)")
# The agent does not sign the owner's work. The strict reading is deliberate:
# EVERY co-author trailer is refused, human ones included, so no shape is left to hide behind.
COAUTHOR_RE = re.compile(r"co-authored-by\s*:", re.IGNORECASE)
ADVERT_RE = re.compile(r"generated with .{0,24}claude", re.IGNORECASE)
# Only commit and pull-request commands are read: an `echo` mentioning a trailer is not authorship.
COMMIT_LIKE_RE = re.compile(r"\bcommit\b|\bpr\s+create\b|\bpull\s+request\b", re.IGNORECASE)


def already_tracked(file_path, line):
    d = os.path.dirname(os.path.abspath(file_path))
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    try:
        top = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if top.returncode != 0:
            return False
        found = subprocess.run(["git", "-C", top.stdout.strip(), "grep", "-qF", "-e", line], capture_output=True)
        return found.returncode == 0
    except Exception:
        return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    texts = []
    for key in ("content", "new_string", "new_source"):
        value = tool_input.get(key)
        if isinstance(value, str):
            texts.append(value)
    for edit in tool_input.get("edits") or []:
        value = (edit or {}).get("new_string")
        if isinstance(value, str):
            texts.append(value)
    command = tool_input.get("command")
    signed = []
    if isinstance(command, str) and COMMIT_LIKE_RE.search(command):
        texts.append(command)
        for line in command.splitlines():
            if COAUTHOR_RE.search(line) or ADVERT_RE.search(line):
                signed.append(line.strip()[:120])
    if signed:
        sys.stderr.write(
            "BLOCKED: this commit or pull request signs the work with a co-author trailer or a "
            "tool advertising line. The author is the person who asked for the change, not the "
            "agent that typed it. Remove the line and write the message again. Offending lines:\n"
        )
        for line in signed[:5]:
            sys.stderr.write("  " + line + "\n")
        return 2
    # The dash rule has an escape hatch; the signature rule does NOT, and the order above is
    # what enforces that: KT_ALLOW_EMDASH is only read after the signature check has passed.
    if os.environ.get("KT_ALLOW_EMDASH") == "1":
        return 0
    bad = []
    for text in texts:
        for line in text.splitlines():
            lowered = line.lower()
            if "em dash" in lowered or "en dash" in lowered:
                continue
            if EM_DASH in line or EN_DASH_BREAK_RE.search(line):
                stripped = line.strip()
                if isinstance(file_path, str) and file_path and already_tracked(file_path, stripped):
                    continue
                bad.append(stripped[:120])
    if bad:
        sys.stderr.write(
            "BLOCKED: em dash (or clause-break en dash) found in the content being written. "
            "House rule: replace with comma, colon, semicolon, parentheses, or split the "
            "sentence. Moving a line that already exists in the repo is allowed as is. Offending lines:\n"
        )
        for line in bad[:5]:
            sys.stderr.write("  " + line + "\n")
        sys.stderr.write("(KT_ALLOW_EMDASH=1 in the claude process environment disables this hook for the whole session)\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
