#!/usr/bin/env python3
"""PreToolUse hook: block Write/Edit/NotebookEdit outside the active plan's blast radius.

Threat model: an absent-minded agent drifting off plan, not a malicious one.
Bash writes are not seen live; `--audit` (run by /kt:go and /kt:save from anywhere
inside the repo) is the final net: it compares `git diff --name-only <base>..HEAD`
plus `git status --porcelain --untracked-files=all` against the radius, so shell
writes and committed drift both surface.
Both nets stand on git, so gitignored paths (.env, build output) are invisible to
them; treat that zone as out of scope rather than covered.

Activation marker: `.claude/active-plan` at the repo root, JSON
{"plan": "<repo-relative path>", "base": "<sha at approval>"}. The root is found
by walking UP from the edited file; the walk stops at the first directory that
has the marker, or at a git repo boundary (a `.git` dir or file) without one, so
a nested repo or a worktree lane is never governed by an outer marker. No marker:
stay silent. Marker present but broken (unparseable, plan path not repo-relative,
plan missing or undecodable, radius missing, catch-all, or a directory line):
FAIL CLOSED, because a silently dead fence looks identical to a working one. A
crash inside the hook fails closed for the same reason (only a broken JSON
payload is let through, like the other hooks).

Radius grammar (single source of truth, quoted by commands/plan.md): in the plan
file, under the heading `## Blast radius` (a leading `N.` number is allowed),
the first fenced code block; one glob per line; blank lines and `#` lines are
ignored. Glob semantics: a single `*` crosses `/`; `**/` also matches zero
directories; `?` is one character; brackets are LITERAL (framework paths like
`app/[id]/page.tsx` match themselves); a leading `./` is stripped; a line made
only of `*`, `/`, `.`, `?` (`*`, `**`, `**/*`, `*.*`) makes the whole radius
invalid (a catch-all fence is a dead fence), and so does a line ending in `/`
(a directory is written `dir/*`). The heading match ignores case. Matching runs
on the path relative to the marker directory.

Exemptions: docs/agent/** (bookkeeping lives there) EXCEPT the directory that
holds the active plan: the plan and its siblings are refused OUTRIGHT, before the
radius is consulted, so an agent cannot widen its own radius mid-flight even when
the radius covers the plans directory or lists the plan itself (arming and
re-arming use shell, after user approval); the marker is likewise never writable
through this fence.
Escape hatch: KT_ALLOW_OFFPLAN=1 in the environment of the claude process (it
disables the fence for that whole session and the banner says so); the sanctioned
way out is removing the marker after the user approves.
"""
import json
import os
import re
import subprocess
import sys

MARKER_REL = os.path.join(".claude", "active-plan")
HEADING_RE = re.compile(r"^##\s+(?:\d+\.\s*)?Blast radius$", re.IGNORECASE)
CATCH_ALL_RE = re.compile(r"^[*/.?]*$")


def find_root(path):
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isfile(os.path.join(d, MARKER_REL)):
            return d
        if os.path.exists(os.path.join(d, ".git")):
            return None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def parse_radius(plan_text):
    in_section = False
    in_fence = False
    globs = []
    for line in plan_text.splitlines():
        stripped = line.strip()
        if not in_fence and stripped.startswith("## "):
            in_section = bool(HEADING_RE.match(stripped))
            continue
        if not in_section:
            continue
        if stripped.startswith("```"):
            if in_fence:
                return globs
            in_fence = True
            continue
        if in_fence and stripped and not stripped.startswith("#"):
            globs.append(stripped)
    return None


def glob_to_re(pattern):
    pat = pattern.strip()
    if pat.startswith("./"):
        pat = pat[2:]
    out = []
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif pat[i] == "*":
            out.append(".*")
            i += 1
        elif pat[i] == "?":
            out.append(".")
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_radius(globs):
    """Returns matchers; raises ValueError with the reason when a line makes the radius invalid."""
    cleaned = []
    for g in globs:
        pat = g.strip()
        if pat.startswith("./"):
            pat = pat[2:]
        if CATCH_ALL_RE.match(pat):
            raise ValueError("has a catch-all blast radius line '" + pat + "' (only stars, slashes, dots), which turns the fence off silently; list real paths instead.")
        if pat.endswith("/"):
            raise ValueError("has a directory line '" + pat + "' in its blast radius, which matches nothing; write it as '" + pat + "*'.")
        cleaned.append(glob_to_re(g))
    return cleaned


def load_fence(root):
    """Returns (plan_rel, matchers) or (error_message, None)."""
    marker_abs = os.path.join(root, MARKER_REL)
    remedy = "Sanctioned exit: rm " + marker_abs + " (only after the user approved).\n"
    try:
        with open(marker_abs, encoding="utf-8") as f:
            plan_rel = json.load(f)["plan"].replace(os.sep, "/")
    except Exception:
        return (".claude/active-plan is unreadable. " + remedy, None)
    if os.path.isabs(plan_rel):
        return ("marker plan path must be repo-relative, got '" + plan_rel + "'. " + remedy, None)
    try:
        with open(os.path.join(root, plan_rel), encoding="utf-8") as f:
            radius = parse_radius(f.read())
    except Exception:
        return ("marker points to a missing or undecodable plan (" + plan_rel + "). " + remedy, None)
    if not radius:
        return ("plan " + plan_rel + " has no parseable '## Blast radius' block. " + remedy, None)
    try:
        matchers = compile_radius(radius)
    except ValueError as exc:
        return ("plan " + plan_rel + " " + str(exc) + " " + remedy, None)
    return (plan_rel, matchers)


def plans_dir_of(plan_rel):
    return plan_rel.rsplit("/", 1)[0] if "/" in plan_rel else ""


def is_bookkeeping(rel, plan_rel):
    if not rel.startswith("docs/agent/"):
        return False
    pd = plans_dir_of(plan_rel)
    if pd and (rel == plan_rel or rel.startswith(pd + "/")):
        return False
    return True


def is_plan_guarded(rel, plan_rel):
    pd = plans_dir_of(plan_rel)
    return rel == plan_rel or (bool(pd) and rel.startswith(pd + "/"))


def deny(message):
    sys.stderr.write("BLOCKED by plan fence: " + message)
    return 2


def hook_main():
    try:
        return _hook_main()
    except Exception as exc:
        return deny("hook crashed (" + type(exc).__name__ + ": " + str(exc)[:200] + "); failing closed rather than silently off.\n")


def _hook_main():
    if os.environ.get("KT_ALLOW_OFFPLAN") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(file_path, str) or not file_path:
        return 0
    root = find_root(file_path)
    if root is None:
        return 0
    rel = os.path.relpath(os.path.abspath(file_path), root).replace(os.sep, "/")
    loaded, matchers = load_fence(root)
    if matchers is None:
        return deny(loaded)
    plan_rel = loaded
    if is_bookkeeping(rel, plan_rel):
        return 0
    if is_plan_guarded(rel, plan_rel):
        return deny("'" + rel + "' is the active plan or sits in its directory (" + plan_rel + "): not writable while armed, whatever the radius says; re-arm (rm marker, edit, re-create) after user approval.\n")
    for matcher in matchers:
        if matcher.match(rel):
            return 0
    marker_abs = os.path.join(root, MARKER_REL)
    sys.stderr.write(
        "BLOCKED by plan fence: '" + rel + "' is outside the blast radius of the active plan (" + plan_rel + ").\n"
        "- Needed for the Goal: propose it to the user; after approval re-arm (remove marker, widen the plan's radius, re-create marker via shell).\n"
        "- Not blocking the current task: append one line to the 'Parked questions' section of docs/agent/HANDOFF.md and continue within the radius.\n"
        "- Sanctioned exit: rm " + marker_abs + " (only after the user approved).\n"
    )
    return 2


def git_lines(root, *args):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git " + " ".join(args) + " failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def audit_main():
    root = find_root(os.path.join(os.getcwd(), "_"))
    if root is None:
        print("plan fence: no active plan from " + os.getcwd() + " upward, nothing to audit")
        return 0
    loaded, matchers = load_fence(root)
    if matchers is None:
        print("plan fence audit FAILED: " + loaded.strip())
        return 2
    plan_rel = loaded
    try:
        with open(os.path.join(root, MARKER_REL), encoding="utf-8") as f:
            base = json.load(f)["base"]
        if not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{7,40}", base):
            print("plan fence audit FAILED: base in .claude/active-plan is not a commit sha (" + str(base)[:40] + "); restore the original base before trusting any audit")
            return 2
        commits = git_lines(root, "rev-list", "--count", base + "..HEAD")
        print("plan fence audit: base " + base + ", " + (commits[0] if commits else "0") + " commit(s) from base to HEAD")
        changed = set(git_lines(root, "diff", "--name-only", base + "..HEAD"))
        for line in git_lines(root, "status", "--porcelain", "--untracked-files=all"):
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            changed.add(path.strip().strip('"'))
    except Exception as exc:
        print("plan fence audit FAILED: cannot diff against base (" + str(exc) + ")")
        return 2
    offenders = []
    for rel in sorted(changed):
        rel = rel.rstrip("/")
        if not rel or rel == ".claude/active-plan":
            continue
        if is_bookkeeping(rel, plan_rel):
            continue
        if is_plan_guarded(rel, plan_rel):
            offenders.append(rel)
            continue
        if any(m.match(rel) for m in matchers):
            continue
        offenders.append(rel)
    if offenders:
        print("plan fence audit: files changed OUTSIDE the blast radius of " + plan_rel + " (report each in UNSURE with a reason):")
        for rel in offenders:
            print("  " + rel)
        return 2
    print("plan fence audit: all changes since base are inside the blast radius of " + plan_rel)
    return 0


if __name__ == "__main__":
    sys.exit(audit_main() if "--audit" in sys.argv[1:] else hook_main())
