#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash) and audit: a commit may not quietly weaken a gate.

The gate-integrity idea comes from gstack's catalog (RH-1, RH-3, RH-4): the failure a test was
built to catch does not go away because the test did. Read once per commit command, this hook
scans the diff the commit would record (`git diff --cached`, or `git diff HEAD` with -a/--all)
and refuses, with exit 2 and the hunks named, when it finds:
- a test skipped or focused (`.skip(`, `.only(`, `xit(`, `@pytest.mark.skip`, `#[ignore]`,
  `t.Skip(`, `@Disabled` and friends) or a test definition removed, in a test-looking file;
- a snapshot or golden regenerated while its owning test file is not in the same diff;
- `--no-verify` on the command itself.
The way through is a human decision written into history: a `Gate-edit: <reason>` line in the
commit message lets the commit pass, so the reason reaches the reviewer and /kt:save.
The repo scanned is the one the command names (`git -C <dir>`, a `cd` before the commit), and a
`git add` in the same command, which has not run yet when the hook fires, counts as -a. Limits:
a new untracked test file in that case is not in the diff; a `git commit <path>` with an unstaged pathspec is read from the index only; a timeout
widened inside a test is not detected; product code calling `.skip(` on an iterator in a file
whose name says test will be flagged (the reason line is the answer).
`--audit <base>` scans `git diff <base> HEAD` and prints the same findings (exit 2 when any), for
/kt:go before a commit and /kt:save at acceptance.
Unreadable payload, no git, or not a commit: silent, exit 0 (a broken scan must not stop every
commit; the audit catches drift later).
"""
import json
import os
import re
import subprocess
import sys

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    # Claude Code hands hooks UTF-8 whatever the Windows locale says: read and answer in UTF-8.
    _stream.reconfigure(encoding="utf-8", errors="replace")

PATH_TOKEN = r"""("[^"]*"|'[^']*'|[^\s;&|]+)"""
COMMIT_RE = re.compile(r"""\bgit((?:\s+-[cC]\s+(?:"[^"]*"|'[^']*'|\S+)|\s+--?[\w-]+(?:=\S+)?)*)\s+commit\b""")
DIR_OPT_RE = re.compile(r"\s-C\s+" + PATH_TOKEN)
CD_RE = re.compile(r"(?:^|[;&|(]\s*)(?:cd|pushd|Set-Location|sl)\s+(?:-Path\s+)?" + PATH_TOKEN)
ADD_RE = re.compile(r"\bgit\b[^|;&]*\s(?:add|stage)\b")
MESSAGE_RE = re.compile(r"""(?:^|\s)(?:-([a-zA-Z]*)m|--message)(?:=|\s+)(?:"[^"]*"|'[^']*'|\S+)""")
FILE_OPT_RE = re.compile(r"(?:\s-F\s*|\s--file[=\s]\s*)" + PATH_TOKEN)
ALL_FLAG_RE = re.compile(r"(^|\s)(--all|-[a-zA-Z]*a[a-zA-Z]*)(\s|$)")
TESTLIKE_RE = re.compile(r"(^|/)(tests?|specs?|__tests__|e2e)/|\.(test|spec|e2e)\.|_test\.(go|py|rb|ts|js)$|(^|/)test_[^/]*\.py$|(^|/)[^/]*Tests?\.(java|kt|cs|swift)$", re.I)
SKIP_RE = re.compile(r"\.(skip|only|todo)\s*\(|\b(xit|xdescribe|xtest|fit|fdescribe)\s*\(|@pytest\.mark\.(skip|skipif|xfail)|#\[ignore\]|\bt\.Skip(Now)?\(|@(Disabled|Ignore)\b|\bXCTSkip|@tag :skip|\bskip:\s*true")
TEST_DEF_RE = re.compile(r"^\s*(test|it|describe|context)\s*\(|^\s*(async\s+)?def test_|^\s*func Test[A-Z_]|^\s*@Test\b|^\s*(it|test|scenario)\s+['\"]")
SNAPSHOT_RE = re.compile(r"(^|/)__snapshots__/|\.snap$|\.golden$|(^|/)testdata/", re.I)
REASON_RE = re.compile(r"gate-edit:", re.I)


def run_git(args, cwd):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout


def native_path(token, base):
    path = os.path.expanduser(token.strip("\"'"))
    if os.name == "nt":  # a native Python cannot open the Git Bash spelling /c/Users/...
        path = re.sub(r"^/([a-zA-Z])(?=/|$)", r"\1:", path)
    return os.path.join(base, path)


def commit_dir(before, global_opts, cwd):
    """The repo the commit lands in: the payload cwd, moved by a cd earlier in the command, then by git -C."""
    for token in CD_RE.findall(before):
        cwd = native_path(token, cwd)
    for token in DIR_OPT_RE.findall(global_opts):
        cwd = native_path(token, cwd)
    return cwd


def reason_in_file(flags, cwd):
    found = FILE_OPT_RE.search(flags)
    if not found:
        return False
    try:
        return bool(REASON_RE.search(open(native_path(found.group(1), cwd), encoding="utf-8", errors="replace").read()))
    except OSError:
        return False


def scan(diff_text):
    findings = []
    changed = set()
    path, old_no, new_no = None, 0, 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            path = path[2:] if path.startswith("b/") else path
            if path != "/dev/null":
                changed.add(path)
            continue
        if line.startswith("--- ") or line.startswith("diff --git") or line.startswith("index "):
            continue
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            old_no, new_no = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            continue
        if path is None:
            continue
        testlike = bool(TESTLIKE_RE.search(path))
        if line.startswith("+") and not line.startswith("+++"):
            body = line[1:]
            if testlike and SKIP_RE.search(body):
                findings.append(path + ":" + str(new_no) + " test skipped or focused: " + body.strip()[:80])
            new_no += 1
        elif line.startswith("-") and not line.startswith("---"):
            body = line[1:]
            if testlike and TEST_DEF_RE.search(body):
                findings.append(path + ":" + str(old_no) + " test removed: " + body.strip()[:80])
            old_no += 1
        else:
            old_no += 1
            new_no += 1
    for snap in sorted(p for p in changed if SNAPSHOT_RE.search(p)):
        owner = None
        if "__snapshots__/" in snap and snap.endswith(".snap"):
            parent = snap.split("__snapshots__/")[0]
            owner = parent + os.path.basename(snap)[: -len(".snap")]
        if owner is None:
            findings.append(snap + " golden or test data changed: confirm the test that owns it changed for a reason")
        elif owner not in changed:
            findings.append(snap + " snapshot regenerated while its test " + owner + " is unchanged")
    return findings


def report(findings, stream):
    stream.write("BLOCKED: this commit weakens a gate (a test or snapshot stops catching what it was built for):\n")
    for f in findings:
        stream.write("  " + f + "\n")
    stream.write("Keep the gate, or make the change a named decision: add a line `Gate-edit: <why>` to the commit message so the reason rides into history for the reviewer and /kt:save.\n")


def audit(base, cwd):
    code, diff = run_git(["diff", "-U0", "--no-color", base, "HEAD"], cwd)
    if code != 0:
        sys.stdout.write("no-gate-weakening: git diff " + base + " HEAD failed\n")
        return 0
    findings = scan(diff)
    if findings:
        report(findings, sys.stdout)
        return 2
    sys.stdout.write("no-gate-weakening: no gate weakened in " + base + "..HEAD\n")
    return 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--audit":
        return audit(sys.argv[2], os.getcwd())
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    match = COMMIT_RE.search(command)
    if not match:
        return 0
    before = command[:match.start()]
    # Message text out, so it is not read as flags; the letters of a bundled -am stay.
    bare = MESSAGE_RE.sub(lambda m: " -" + m.group(1) + " " if m.group(1) else " ", command[match.end():])
    flags = re.split(r"[;&|]", bare)[0]
    cwd = commit_dir(before, match.group(1), payload.get("cwd") or os.getcwd())
    findings = []
    if re.search(r"(^|\s)--no-verify\b", flags):
        findings.append("--no-verify on the command: the repo's own commit hooks would be skipped")
    # PreToolUse runs before the whole command: a `git add` in it has not staged anything yet.
    staged_only = not (ALL_FLAG_RE.search(flags) or ADD_RE.search(before))
    code, diff = run_git(["diff", "-U0", "--no-color"] + (["--cached"] if staged_only else ["HEAD"]), cwd)
    if code == 0:
        findings.extend(scan(diff))
    if not findings or REASON_RE.search(command) or reason_in_file(flags, cwd):
        return 0
    report(findings, sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a broken scan must not stop every commit; the audit catches drift later
        sys.stderr.write("no-gate-weakening: internal error, letting the call through: " + type(exc).__name__ + "\n")
        sys.exit(0)
