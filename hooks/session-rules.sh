#!/bin/sh
# SubagentStart only injects via hookSpecificOutput.additionalContext JSON; plain stdout is
# swallowed for subagents (verified by a live probe). SessionStart keeps plain stdout.
# Anything that switches a kt hook off (KT_ALLOW_* in the claude process env, no python3)
# is announced in the banner, because a silently disabled fence looks like a working one.
# A subagent also gets the stage and the open decisions of the repo it works in (docs/agent
# under the hook cwd), because rules without project context still let it decide what the
# owner has not decided. That block comes from a second hook (argument "docs"): Claude Code
# swaps any single hook output over 10000 chars for a 2000-char preview, so the rules and the
# block each get their own budget, and a block cut to fit names the files to read in full.
root="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$root/rules/work.md" ] || exit 0
mode="${1:-}"
banner="=== kt rules === (injected by the kt plugin at SessionStart and SubagentStart; precedence: repo CLAUDE.md > ~/CLAUDE.md > these rules)"
warn=""
command -v python3 >/dev/null 2>&1 || warn="${warn}WARNING: python3 not found, the kt PreToolUse hooks (plan fence, secret read, em dash) are inert in this session.\n"
[ "$KT_ALLOW_OFFPLAN" = "1" ] && warn="${warn}WARNING: KT_ALLOW_OFFPLAN=1 is set in the claude process environment, the plan fence is OFF for this whole session.\n"
[ "$KT_ALLOW_EMDASH" = "1" ] && warn="${warn}WARNING: KT_ALLOW_EMDASH=1 is set in the claude process environment, the em dash hook is OFF for this whole session.\n"
input="$(cat)"
event="$(printf '%s' "$input" | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("hook_event_name", ""))
except Exception:
    print("")' 2>/dev/null)"
cwd="$(printf '%s' "$input" | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("cwd", "") or "")
except Exception:
    print("")' 2>/dev/null)"
[ -n "$cwd" ] || cwd="${CLAUDE_PROJECT_DIR:-$(pwd)}"
if [ "$mode" = "docs" ]; then
    [ "$event" = "SubagentStart" ] || exit 0
    python3 - "$cwd" <<'PY'
import json, os, sys
BUDGET = 9500
agent_dir = os.path.join(sys.argv[1], "docs", "agent")


def js_len(text):
    return len(text.encode("utf-16-le")) // 2


def section(path, needle):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return ""
    out, on = [], False
    for line in lines:
        if line.startswith("## "):
            if on:
                break
            on = needle in line.lower()
        if on:
            out.append(line)
    return "\n".join(out).strip()


project = os.path.join(agent_dir, "PROJECT.md")
decisions = os.path.join(agent_dir, "DECISIONS.md")
stage = section(project, "current stage")
pending = section(decisions, "open decisions")
warnings = []
if os.path.isfile(decisions) and not pending:
    warnings.append('WARNING: docs/agent/DECISIONS.md has no "Open decisions" section, so this block carries no open decisions; the ledger may still use older section names.')
if os.path.isfile(project) and not stage:
    warnings.append('WARNING: docs/agent/PROJECT.md has no "Current stage and consequences" section, so this block carries no stage; the ledger may still use older section names.')
if not (stage or pending or warnings):
    sys.exit(0)
header = "=== docs/agent (cwd) === (open decisions and stage of the repo this subagent works in: never decide the open items, obey the stage, return with the question instead)"
pointer = "[kt cut this block to stay under the 10000-char limit Claude Code puts on one hook output: read docs/agent/DECISIONS.md (open decisions) and docs/agent/PROJECT.md (stage) in full before deciding anything they cover]"
lines = [header] + warnings + "\n\n".join(s for s in (pending, stage) if s).splitlines()
text = "\n".join(lines)
if js_len(text) > BUDGET:
    kept, size = [], js_len(pointer)
    for line in lines:
        if size + js_len(line) + 1 > BUDGET:
            break
        kept.append(line)
        size += js_len(line) + 1
    text = "\n".join(kept + [pointer])
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": text}}))
PY
    exit 0
fi
if [ "$event" = "SubagentStart" ]; then
    python3 - "$root/rules/work.md" "$banner" "$warn" <<'PY'
import json, sys
body = open(sys.argv[1], encoding="utf-8").read()
warn = sys.argv[3].replace("\\n", "\n")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": sys.argv[2] + "\n" + warn + body}}))
PY
else
    echo "$banner"
    printf "$warn"
    cat "$root/rules/work.md"
fi
