#!/usr/bin/env python3
"""Tests for the kt plugin: hook exit codes, fence audit mode, packaging and drift checks.

Run: python3 hooks/test_hooks.py
Hook cases pipe a PreToolUse-style JSON payload into the hook as a subprocess and assert
the exit code (0 = allow, 2 = block). New expectations must be seen RED before the fix
lands (governance rule 4, standing form). Dash characters are built via chr() so the
no-emdash hook can write this file. Totals are derived from the checks actually run.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EMDASH = chr(0x2014)
ENDASH = chr(0x2013)


class Suite:
    def __init__(self):
        self.total = 0
        self.failures = []

    def check(self, label, ok, detail=""):
        self.total += 1
        if not ok:
            self.failures.append(label + (": " + detail if detail else ""))

    def expect_exit(self, hook, label, payload, expected, extra_env=None):
        got = run_hook(hook, payload, extra_env).returncode
        self.check(hook + ": " + label, got == expected, "expected exit " + str(expected) + ", got " + str(got))


class Missing:
    returncode = 127
    stdout = ""
    stderr = ""


def run_hook(hook, payload, extra_env=None, args=None, cwd=None):
    path = os.path.join(HERE, hook)
    if not os.path.isfile(path):
        return Missing()
    env = {k: v for k, v in os.environ.items() if k not in ("KT_ALLOW_EMDASH", "KT_ALLOW_OFFPLAN")}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, path] + (args or []),
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def kt_installed():
    """True when installed_plugins.json records a kt@kt install (the stop gate's audit needs one)."""
    reg = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
    try:
        return bool(json.load(open(reg, encoding="utf-8"))["plugins"].get("kt@kt"))
    except Exception:
        return False


def local_rules_backup_case(s):
    """A fork that keeps its kt rules in CLAUDE.local.md must get them backed up too."""
    repo = os.path.join(tempfile.mkdtemp(prefix="kt-backup-local-"), "fork")
    home = tempfile.mkdtemp(prefix="kt-backup-home-")
    os.makedirs(repo)
    with open(os.path.join(repo, "CLAUDE.local.md"), "w", encoding="utf-8") as f:
        f.write("gates\n")
    git(repo, "init", "-q")
    git(repo, "commit", "-q", "--allow-empty", "-m", "root")
    subprocess.run([sys.executable, os.path.join(HERE, "kt-backup.py")], cwd=repo, capture_output=True, env={**os.environ, "HOME": home, "USERPROFILE": home})
    s.check("kt-backup.py backs up CLAUDE.local.md", os.path.isfile(os.path.join(home, "kt-backups", "fork", "CLAUDE.local.md")))


def utf8_cases(s):
    """Claude Code hands hooks UTF-8 bytes whatever the Windows locale says: an em dash or a Vietnamese
    path must be read as such, so the hooks decode stdin as UTF-8 and write their messages the same way."""
    viet = chr(0x111) + chr(0x1B0) + chr(0x1EDD) + "ng"  # a Vietnamese path segment, built with chr() so this file stays ASCII
    raw = ('{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/' + viet + '/a.md","content":"one ' + EMDASH + ' two"}}').encode("utf-8")
    proc = subprocess.run([sys.executable, os.path.join(HERE, "no-emdash.py")], input=raw, capture_output=True)
    s.check("no-emdash.py blocks a UTF-8 em dash read from raw stdin bytes", proc.returncode == 2, "exit " + str(proc.returncode) + " " + proc.stderr.decode("utf-8", "replace")[:80])
    proc = subprocess.run([sys.executable, os.path.join(HERE, "no-secret-read.py")], input=('{"hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"/tmp/' + viet + '/.env"}}').encode("utf-8"), capture_output=True)
    s.check("no-secret-read.py blocks a secret under a non-ASCII path and answers without crashing", proc.returncode == 2 and proc.stderr.decode("utf-8").startswith("BLOCKED"), "exit " + str(proc.returncode) + " " + proc.stderr.decode("utf-8", "replace")[:80])


def shim(bindir, name, body):
    """A one-line sh script standing in for a tool on a bare PATH (a symlink needs a privilege on Windows)."""
    path = os.path.join(bindir, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, 0o755)


def bare_path(python3_body=None):
    """A PATH holding only what session-rules.sh needs besides python3, plus an optional python3 stand-in."""
    bindir = tempfile.mkdtemp(prefix="kt-nopython-")
    for tool in ("cat", "dirname"):
        shim(bindir, tool, 'exec "' + shutil.which(tool).replace("\\", "/") + '" "$@"')
    if python3_body is not None:
        shim(bindir, "python3", python3_body)
    return bindir


def content(text):
    return {"tool_input": {"content": text}}


def fp(path):
    return {"tool_input": {"file_path": "/tmp/proj/" + path}}


def emdash_cases(s):
    h = "no-emdash.py"
    s.expect_exit(h, "block em dash in content", content("a " + EMDASH + " b"), 2)
    s.expect_exit(h, "block spaced en dash", content("a " + ENDASH + " b"), 2)
    s.expect_exit(h, "allow en dash range", content("pages 1" + ENDASH + "5"), 0)
    s.expect_exit(h, "allow line naming em dash", content("the em dash " + EMDASH + " rule"), 0)
    s.expect_exit(h, "block em dash in new_string", {"tool_input": {"new_string": "x " + EMDASH}}, 2)
    s.expect_exit(h, "block em dash in edits[]", {"tool_input": {"edits": [{"new_string": EMDASH}]}}, 2)
    s.expect_exit(h, "block em dash in notebook new_source", {"tool_input": {"new_source": "x " + EMDASH}}, 2)
    s.expect_exit(h, "block em dash in a Bash commit message", {"tool_input": {"command": 'git commit -m "Fix X ' + EMDASH + ' Y"'}}, 2)
    s.expect_exit(h, "allow clean Bash commit message", {"tool_input": {"command": 'git commit -m "Fix X"'}}, 0)
    s.expect_exit(h, "ignore non-commit Bash commands", {"tool_input": {"command": "echo " + EMDASH + " x"}}, 0)
    s.expect_exit(h, "allow via KT_ALLOW_EMDASH", content("a " + EMDASH + " b"), 0, {"KT_ALLOW_EMDASH": "1"})
    s.expect_exit(h, "allow clean content", content("plain text"), 0)
    s.expect_exit(h, "allow malformed json (fail-open)", "not json", 0)
    s.expect_exit(h, "block en dash at end of line", content("a " + ENDASH), 2)
    s.expect_exit(h, "block en dash beside a tab", content("a\t" + ENDASH + "\tb"), 2)


def emdash_relocation_cases(s):
    h = "no-emdash.py"
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(repo, "src", "pages"), exist_ok=True)
        git(repo, "init", "-q")
        line = "Title " + EMDASH + " already in the repo"
        with open(os.path.join(repo, "src/pages/old.tsx"), "w", encoding="utf-8") as f:
            f.write("<h1>\n  " + line + "\n</h1>\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        moved = {"tool_input": {"file_path": os.path.join(repo, "src/components/new.tsx"), "content": "<p>\n      " + line + "\n</p>\n"}}
        s.expect_exit(h, "allow relocating a line that already exists in the repo (new subdir)", moved, 0)
        fresh = {"tool_input": {"file_path": os.path.join(repo, "src/pages/new.tsx"), "content": line + "\nfresh " + EMDASH + " line\n"}}
        s.expect_exit(h, "block a new em dash line even next to a relocated one", fresh, 2)
        outside = {"tool_input": {"file_path": os.path.join(tmp, "elsewhere.md"), "content": line + "\n"}}
        s.expect_exit(h, "block the same line outside any repo", outside, 2)
        commit = {"tool_input": {"command": 'git commit -m "' + line + '"'}, "cwd": repo}
        s.expect_exit(h, "commit message gets no relocation carve-out", commit, 2)


SECRET_BLOCK = [
    ".env", ".env.local", ".env.production", ".envrc", "local.env", "production.env",
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "secrets.json",
    "server.pem", "api.key", "store.keystore", "bundle.p12", "cert.pfx", "trust.jks",
    "AuthKey_X1.p8", ".netrc", ".npmrc", ".pgpass", "credentials",
    "secrets/api.txt", ".ssh/id_future", ".aws/credentials", ".gnupg/secring.gpg",
    "credentials.json", "service-account-prod.json", "infra.tfstate", "prod.tfvars",
    ".git-credentials", ".kube/config", ".docker/config.json", "key.ppk", "secring.gpg",
    "secrets.yaml", ".ENV", "Id_Rsa", ".htpasswd", ".pypirc",
    "secrets/prod.yaml", "secrets/api.key", "k8s/secrets/db.json", "my-app-firebase-adminsdk-abc.json",
    "serviceAccountKey.json", "credentials.yml", "credentials.yaml", "terraform.tfstate.backup",
]
SECRET_ALLOW = [
    ".env.example", ".env.sample", ".env.template", "id_rsa.example",
    "src/main.py", "README.md", "credentials.ts", "secrets_manager.ts", "docs/keys.md",
    "src/secrets/manager.ts", "secrets/README.md", "secrets/loader.py", ".ssh/config", ".ssh/known_hosts", ".aws/config",
    "id_rsa.pub", ".ssh/id_ed25519.pub", "secrets.py", "src/secrets.ts",
]


def secret_cases(s):
    h = "no-secret-read.py"
    for p in SECRET_BLOCK:
        s.expect_exit(h, "block " + p, fp(p), 2)
    for p in SECRET_ALLOW:
        s.expect_exit(h, "allow " + p, fp(p), 0)
    s.expect_exit(h, "block Grep path .env", {"tool_input": {"path": "/tmp/proj/.env"}}, 2)
    s.expect_exit(h, "block Grep glob .env*", {"tool_input": {"path": "/tmp/proj", "glob": ".env*"}}, 2)
    s.expect_exit(h, "block Grep glob **/id_ed25519*", {"tool_input": {"path": "/tmp/proj", "glob": "**/id_ed25519*"}}, 2)
    s.expect_exit(h, "allow Grep glob *.ts", {"tool_input": {"path": "/tmp/proj", "glob": "*.ts"}}, 0)
    s.expect_exit(h, "block content-mode Grep for a secret-looking pattern over a directory", {"tool_input": {"pattern": "STRIPE_SECRET", "path": "/tmp/proj", "output_mode": "content"}}, 2)
    s.expect_exit(h, "block content-mode Grep for API_KEY without a path", {"tool_input": {"pattern": "API_KEY", "output_mode": "content"}}, 2)
    s.expect_exit(h, "block content-mode Grep for PASSWORD over a directory", {"tool_input": {"pattern": "PASSWORD", "path": "/tmp/proj", "output_mode": "content"}}, 2)
    s.expect_exit(h, "allow content-mode Grep narrowed by a glob", {"tool_input": {"pattern": "STRIPE_SECRET", "path": "/tmp/proj", "output_mode": "content", "glob": "*.ts"}}, 0)
    s.expect_exit(h, "allow files_with_matches Grep for a secret-looking pattern", {"tool_input": {"pattern": "STRIPE_SECRET", "path": "/tmp/proj", "output_mode": "files_with_matches"}}, 0)
    s.expect_exit(h, "allow content-mode Grep for an ordinary pattern", {"tool_input": {"pattern": "useState", "path": "/tmp/proj", "output_mode": "content"}}, 0)
    s.expect_exit(h, "allow content-mode Grep for onKeyDown (key inside a word)", {"tool_input": {"pattern": "onKeyDown", "path": "/tmp/proj", "output_mode": "content"}}, 0)
    s.expect_exit(h, "allow malformed json (fail-open)", "not json", 0)


def plan_text(radius_lines, heading="## Blast radius"):
    return "\n".join(["# Fence test plan", "", heading, "", "```"] + radius_lines + ["```", "", "## Task", ""])


def make_repo(root, radius_lines=("src/*", "hooks/*.py", "# comment line"), heading="## Blast radius", with_marker=True, base="0000000"):
    plan_rel = "docs/agent/plans/p.md"
    os.makedirs(os.path.join(root, "docs/agent/plans"), exist_ok=True)
    with open(os.path.join(root, plan_rel), "w", encoding="utf-8") as f:
        f.write(plan_text(list(radius_lines), heading))
    os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
    if with_marker:
        with open(os.path.join(root, ".claude", "active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": plan_rel, "base": base}))
    return root


def offplan_cases(s):
    h = "no-offplan-edit.py"

    def at(repo, rel, expected, label, extra_env=None, key="file_path"):
        s.expect_exit(h, label, {"tool_input": {key: os.path.join(repo, rel)}}, expected, extra_env)

    with tempfile.TemporaryDirectory() as tmp:
        armed = make_repo(os.path.join(tmp, "armed"))
        at(armed, "src/a.ts", 0, "allow inside radius")
        at(armed, "src/deep/b.ts", 0, "allow deep via star crossing slashes")
        at(armed, "README.md", 2, "block outside radius")
        at(armed, "docs/agent/HANDOFF.md", 0, "allow docs/agent bookkeeping")
        at(armed, "docs/agent/plans/p.md", 2, "block the plan file itself")
        at(armed, "docs/agent/plans/other.md", 2, "block other plan files (no two-step widening)")
        at(armed, ".claude/active-plan", 2, "block the marker via Write (arm uses shell)")
        at(armed, "README.md", 0, "allow escape via KT_ALLOW_OFFPLAN", {"KT_ALLOW_OFFPLAN": "1"})
        at(armed, "README.ipynb", 2, "block notebook outside radius", key="notebook_path")
        at(armed, "src/n.ipynb", 0, "allow notebook inside radius", key="notebook_path")

        web = make_repo(os.path.join(tmp, "web"), ["app/orders/[id]/page.tsx", "./src/*", "lib/**/*.ts"])
        at(web, "app/orders/[id]/page.tsx", 0, "brackets in path are literal")
        at(web, "app/orders/i/page.tsx", 2, "brackets are not a character class")
        at(web, "src/a.ts", 0, "leading ./ in glob is normalized")
        at(web, "lib/a.ts", 0, "** matches zero directories")
        at(web, "lib/x/y.ts", 0, "** matches nested directories")

        wide = make_repo(os.path.join(tmp, "wide"), ["docs/*", "src/*"])
        at(wide, "docs/agent/plans/p.md", 2, "plan guard beats a radius that covers the plans dir")
        at(wide, "docs/agent/plans/other.md", 2, "plan guard covers plan siblings under a wide radius")
        at(wide, "docs/other.md", 0, "wide radius still allows non-plan docs")
        at(wide, "docs/agent/HANDOFF.md", 0, "bookkeeping stays writable under a wide radius")
        selfw = make_repo(os.path.join(tmp, "selfw"), ["docs/agent/plans/p.md", "src/*"])
        at(selfw, "docs/agent/plans/p.md", 2, "plan guard beats a radius listing the plan itself")
        qmark = make_repo(os.path.join(tmp, "qmark"), ["src/?.ts"])
        at(qmark, "src/a.ts", 0, "? matches exactly one character")
        at(qmark, "src/ab.ts", 2, "? does not match two characters")
        for i, pat in enumerate(("**", ".", "/")):
            ca = make_repo(os.path.join(tmp, "bareline" + str(i)), [pat])
            at(ca, "src/a.ts", 2, "bare " + pat + " radius is refused (fail-closed)")
        badjson = make_repo(os.path.join(tmp, "badjson"), with_marker=False)
        with open(os.path.join(badjson, ".claude", "active-plan"), "w", encoding="utf-8") as f:
            f.write("{not json")
        at(badjson, "src/a.ts", 2, "fail-closed on an unparseable marker")

        numbered = make_repo(os.path.join(tmp, "numbered"), heading="## 5. Blast radius")
        at(numbered, "src/a.ts", 0, "numbered heading accepted")
        catch_all = make_repo(os.path.join(tmp, "catchall"), ["*"])
        at(catch_all, "src/a.ts", 2, "catch-all radius is refused (fail-closed)")
        for i, pat in enumerate(("**/*", "*/*", "*.*")):
            ca = make_repo(os.path.join(tmp, "catchall" + str(i)), [pat])
            at(ca, "src/a.ts", 2, "catch-all radius " + pat + " is refused (fail-closed)")
        dirform = make_repo(os.path.join(tmp, "dirform"), ["src/"])
        at(dirform, "src/a.ts", 2, "directory-form radius line is refused (fail-closed)")
        proc = run_hook(h, {"tool_input": {"file_path": os.path.join(dirform, "src/a.ts")}})
        s.check(h + ": directory-form refusal names the fix", "src/*" in proc.stderr, proc.stderr.strip()[:120])
        upper = make_repo(os.path.join(tmp, "upper"), heading="## Blast Radius")
        at(upper, "src/a.ts", 0, "heading match is case-insensitive")
        absplan = make_repo(os.path.join(tmp, "absplan"), with_marker=False)
        with open(os.path.join(absplan, ".claude", "active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": os.path.join(absplan, "docs/agent/plans/p.md"), "base": "0"}))
        at(absplan, "docs/agent/plans/p.md", 2, "absolute plan path in the marker is refused")
        undecodable = make_repo(os.path.join(tmp, "undecodable"))
        with open(os.path.join(undecodable, "docs/agent/plans/p.md"), "wb") as f:
            f.write(b"\xff\xfe# plan\n")
        at(undecodable, "README.md", 2, "fail-closed on an undecodable plan")
        s.expect_exit(h, "fail closed on a string tool_input", {"tool_input": "x"}, 2)

        bare = os.path.join(tmp, "bare")
        os.makedirs(os.path.join(bare, "src"), exist_ok=True)
        at(bare, "src/a.ts", 0, "silent without marker")
        at(bare, "README.md", 0, "silent without marker outside")

        broken = make_repo(os.path.join(tmp, "broken"), with_marker=False)
        with open(os.path.join(broken, ".claude", "active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": "docs/agent/plans/missing.md", "base": "0"}))
        at(broken, "src/a.ts", 2, "fail-closed on dangling marker")
        noradius = os.path.join(tmp, "noradius")
        os.makedirs(os.path.join(noradius, ".claude"), exist_ok=True)
        os.makedirs(os.path.join(noradius, "docs/agent/plans"), exist_ok=True)
        with open(os.path.join(noradius, "docs/agent/plans/p.md"), "w", encoding="utf-8") as f:
            f.write("# Plan\n\nno radius block here\n")
        with open(os.path.join(noradius, ".claude/active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": "docs/agent/plans/p.md", "base": "0"}))
        at(noradius, "src/a.ts", 2, "fail-closed on unparseable radius")

        multi = os.path.join(tmp, "multi")
        repo_a = make_repo(os.path.join(multi, "repo-a"))
        repo_b = os.path.join(multi, "repo-b")
        os.makedirs(os.path.join(repo_b, "src"), exist_ok=True)
        at(repo_b, "anything.md", 0, "sibling repo without marker stays free")
        at(repo_a, "README.md", 2, "marked sibling still fenced")

        parent = make_repo(os.path.join(tmp, "parent"), ["repo-x/src/*"])
        os.makedirs(os.path.join(parent, "repo-x", "src"), exist_ok=True)
        at(parent, "repo-x/src/a.ts", 0, "parent marker governs plain child dir inside radius")
        at(parent, "repo-x/other.md", 2, "parent marker blocks plain child dir outside radius")
        child = make_repo(os.path.join(parent, "repo-y"))
        at(child, "src/a.ts", 0, "nearest marker wins over parent")
        gitchild = os.path.join(parent, "repo-z")
        os.makedirs(os.path.join(gitchild, ".git"), exist_ok=True)
        os.makedirs(os.path.join(gitchild, "src"), exist_ok=True)
        at(gitchild, "other.md", 0, "fence stops at a git repo boundary (.git dir)")

        lane = os.path.join(armed, ".claude", "worktrees", "lane1")
        os.makedirs(os.path.join(lane, "src"), exist_ok=True)
        with open(os.path.join(lane, ".git"), "w", encoding="utf-8") as f:
            f.write("gitdir: /nowhere\n")
        at(lane, "src/a.ts", 0, "worktree lane is not governed by the main marker")
        at(lane, "other.md", 0, "worktree lane outside main radius stays free")


def bash_cases(s):
    h = "no-offplan-bash.py"

    def cmd(repo, command, expected, label, extra_env=None):
        got = run_hook(h, {"tool_input": {"command": command}, "cwd": repo}, extra_env).returncode
        s.check(h + ": " + label, got == expected, "expected exit " + str(expected) + ", got " + str(got))

    with tempfile.TemporaryDirectory() as tmp:
        armed = make_repo(os.path.join(tmp, "armed"))
        cmd(armed, "printf '{}' > .claude/active-plan", 2, "block overwriting the live marker via redirect (re-arm goes rm-then-create)")
        cmd(armed, "echo x | tee .claude/active-plan", 2, "block tee onto the live marker")
        cmd(armed, "cp /tmp/x .claude/active-plan", 2, "block cp onto the live marker")
        cmd(armed, "mv .claude/active-plan /tmp/", 2, "block moving the live marker away (disarm goes through rm)")
        cmd(armed, "rm .claude/active-plan && printf '{}' > .claude/active-plan", 2, "block re-arm folded into one command")
        proc = run_hook(h, {"tool_input": {"command": "printf '{}' > .claude/active-plan"}, "cwd": armed})
        s.check(h + ": marker overwrite message says to use a separate command", "separate command" in proc.stderr, proc.stderr.strip()[:120])
        cmd(armed, "rm .claude/active-plan", 0, "allow rm of the marker (sanctioned exit, first half of re-arm)")
        cmd(armed, "cat .claude/active-plan", 0, "allow reading the marker")
        cmd(armed, "echo x >> docs/agent/plans/p.md", 2, "block appending to the active plan via shell")
        cmd(armed, "cp /tmp/x docs/agent/plans/other.md", 2, "block writing a sibling plan via shell")
        cmd(armed, "sed -i '' 's/a/b/' docs/agent/plans/p.md", 2, "block sed -i on the plan")
        cmd(armed, "cp new.ts docs/agent/plans/", 2, "block cp into the plans directory")
        cmd(armed, "git log -- docs/agent/plans/", 0, "allow read-only commands naming the plans dir")
        cmd(armed, "grep radius docs/agent/plans/p.md", 0, "allow grep on the plan")
        cmd(armed, "echo x > README.md", 0, "shell writes outside the radius are left to the audit")
        cmd(armed, "cat > README.md <<'EOF'\nhi\nEOF", 0, "heredoc outside the radius is left to the audit")
        cmd(armed, "git restore README.md", 0, "git restore is not this hook's business anymore")
        cmd(armed, "printf x > docs/agent/HANDOFF.md", 0, "bookkeeping via shell passes")
        cmd(armed, "echo x > src/a.ts", 0, "writes inside the radius pass")
        cmd(armed, "printf '{}' > .claude/active-plan", 0, "allow via KT_ALLOW_OFFPLAN", {"KT_ALLOW_OFFPLAN": "1"})
        blank = make_repo(os.path.join(tmp, "blank"), with_marker=False)
        cmd(blank, "printf '{}' > .claude/active-plan", 0, "allow arming via shell while no marker exists")
        wideb = make_repo(os.path.join(tmp, "wideb"), ["docs/*", "src/*"])
        cmd(wideb, "echo x >> docs/agent/plans/p.md", 2, "plan guard beats a wide radius in the shell guard")
        cmd(wideb, "echo x > docs/other.md", 0, "wide radius still allows non-plan docs via shell")
        broken = make_repo(os.path.join(tmp, "broken"), with_marker=False)
        with open(os.path.join(broken, ".claude", "active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": "docs/agent/plans/missing.md", "base": "0"}))
        cmd(broken, "rm .claude/active-plan", 0, "allow rm marker as the escape from a broken marker")
        cmd(broken, "printf '{}' > .claude/active-plan", 2, "block overwriting even a broken marker (rm first)")
        bare = os.path.join(tmp, "bare")
        os.makedirs(bare, exist_ok=True)
        cmd(bare, "echo x > README.md", 0, "silent without marker")
        s.check(h + ": malformed json (fail-open)", run_hook(h, "not json").returncode == 0)
        s.check(h + ": string tool_input fails closed while armed", run_hook(h, {"tool_input": "x", "cwd": armed}).returncode == 2)
        s.check(h + ": string tool_input stays silent without a marker", run_hook(h, {"tool_input": "x", "cwd": bare}).returncode == 0)


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def audit_cases(s):
    h = "no-offplan-edit.py"
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(os.path.join(tmp, "repo"), with_marker=False)
        git(repo, "init", "-q")
        os.makedirs(os.path.join(repo, "src"), exist_ok=True)
        open(os.path.join(repo, "src/a.ts"), "w").write("a\n")
        open(os.path.join(repo, "README.md"), "w").write("r\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        base = git(repo, "rev-parse", "HEAD").stdout.strip()
        with open(os.path.join(repo, ".claude/active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": "docs/agent/plans/p.md", "base": base}))
        clean = run_hook(h, "", args=["--audit"], cwd=repo)
        s.check(h + ": audit clean tree exits 0", clean.returncode == 0, "got " + str(clean.returncode) + " " + clean.stdout.strip()[:80])
        open(os.path.join(repo, "src/a.ts"), "a").write("more\n")
        git(repo, "commit", "-qam", "inside")
        inside = run_hook(h, "", args=["--audit"], cwd=repo)
        s.check(h + ": audit committed inside-radius change exits 0", inside.returncode == 0, inside.stdout.strip()[:80])
        open(os.path.join(repo, "README.md"), "a").write("sneaky via shell\n")
        git(repo, "commit", "-qam", "outside")
        outside = run_hook(h, "", args=["--audit"], cwd=repo)
        s.check(h + ": audit catches committed outside-radius change", outside.returncode == 2 and "README.md" in outside.stdout, outside.stdout.strip()[:120])
        open(os.path.join(repo, "stray.txt"), "w").write("x\n")
        stray = run_hook(h, "", args=["--audit"], cwd=repo)
        s.check(h + ": audit catches untracked outside-radius file", stray.returncode == 2 and "stray.txt" in stray.stdout, stray.stdout.strip()[:120])
        os.remove(os.path.join(repo, "stray.txt"))
        with open(os.path.join(repo, "docs/agent/HANDOFF.md"), "w") as f:
            f.write("bookkeeping\n")
        book = run_hook(h, "", args=["--audit"], cwd=repo)
        s.check(h + ": audit ignores docs/agent bookkeeping", "HANDOFF.md" not in book.stdout, book.stdout.strip()[:120])
        sub = run_hook(h, "", args=["--audit"], cwd=os.path.join(repo, "src"))
        s.check(h + ": audit from a subdir walks up to the marker", sub.returncode == 2 and "README.md" in sub.stdout, str(sub.returncode) + " " + sub.stdout.strip()[:80])
        shown = run_hook(h, "", args=["--audit"], cwd=repo)
        s.check(h + ": audit prints the base and commit count", ("base " + base[:12]) in shown.stdout, shown.stdout.strip()[:120])
        with open(os.path.join(repo, ".claude/active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": "docs/agent/plans/p.md", "base": "HEAD"}))
        badbase = run_hook(h, "", args=["--audit"], cwd=repo)
        s.check(h + ": audit fails on a non-sha base", badbase.returncode == 2 and "base" in badbase.stdout, str(badbase.returncode) + " " + badbase.stdout.strip()[:80])
        with open(os.path.join(repo, ".claude/active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": "docs/agent/plans/p.md", "base": base}))
        nomarker = run_hook(h, "", args=["--audit"], cwd=os.path.join(tmp))
        s.check(h + ": audit without marker exits 0 and says so", nomarker.returncode == 0, str(nomarker.returncode))
        wide = make_repo(os.path.join(tmp, "wide-audit"), ["docs/*", "src/*"], with_marker=False)
        git(wide, "init", "-q")
        git(wide, "add", "-A")
        git(wide, "commit", "-q", "-m", "base")
        wbase = git(wide, "rev-parse", "HEAD").stdout.strip()
        with open(os.path.join(wide, ".claude/active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": "docs/agent/plans/p.md", "base": wbase}))
        open(os.path.join(wide, "docs/agent/plans/p.md"), "a").write("widen radius sneakily\n")
        wa = run_hook(h, "", args=["--audit"], cwd=wide)
        s.check(h + ": audit flags plan edits even inside a wide radius", wa.returncode == 2 and "plans/p.md" in wa.stdout, str(wa.returncode) + " " + wa.stdout.strip()[:100])
        deep = make_repo(os.path.join(tmp, "deep-audit"), ["src/feature/*.ts"], with_marker=False)
        git(deep, "init", "-q")
        git(deep, "add", "-A")
        git(deep, "commit", "-q", "-m", "base")
        dbase = git(deep, "rev-parse", "HEAD").stdout.strip()
        with open(os.path.join(deep, ".claude/active-plan"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"plan": "docs/agent/plans/p.md", "base": dbase}))
        os.makedirs(os.path.join(deep, "src/feature"), exist_ok=True)
        open(os.path.join(deep, "src/feature/a.ts"), "w").write("a\n")
        newdir = run_hook(h, "", args=["--audit"], cwd=deep)
        s.check(h + ": audit accepts a new untracked directory inside the radius", newdir.returncode == 0, str(newdir.returncode) + " " + newdir.stdout.strip()[:120])
        os.makedirs(os.path.join(deep, "extra"), exist_ok=True)
        open(os.path.join(deep, "extra/x.txt"), "w").write("x\n")
        outdir = run_hook(h, "", args=["--audit"], cwd=deep)
        s.check(h + ": audit names the file inside a new untracked directory outside the radius", outdir.returncode == 2 and "extra/x.txt" in outdir.stdout, str(outdir.returncode) + " " + outdir.stdout.strip()[:120])


FENCE_WIRING = [
    ("commands/plan.md", "## Blast radius"),
    ("commands/plan.md", ".claude/active-plan"),
    ("commands/save.md", ".claude/active-plan"),
    ("commands/save.md", "--audit"),
    ("commands/load.md", ".claude/active-plan"),
    ("commands/go.md", ".claude/active-plan"),
]


def wiring_cases(s):
    for rel, needle in FENCE_WIRING:
        path = os.path.join(ROOT, rel)
        ok = os.path.isfile(path) and needle in open(path, encoding="utf-8").read()
        s.check("fence wiring: " + rel + " has '" + needle + "'", ok)


def frontmatter_cases(s):
    for sub in ("commands", "agents"):
        d = os.path.join(ROOT, sub)
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md"):
                continue
            lines = open(os.path.join(d, name), encoding="utf-8").read().split("\n")
            ok = bool(lines) and lines[0].strip() == "---"
            bad_key = ""
            if ok:
                for line in lines[1:]:
                    if line.strip() == "---":
                        break
                    key, sep, value = line.partition(":")
                    value = value.strip()
                    if sep and ": " in value and not value.startswith(('"', "'")):
                        ok = False
                        bad_key = key.strip()
            s.check("frontmatter: " + sub + "/" + name, ok, "unquoted colon in key " + bad_key if bad_key else "no frontmatter")


EXPECTED_WIRING = {
    "Write|Edit|NotebookEdit": ["no-emdash.py", "no-offplan-edit.py"],
    "Read|Grep": ["no-secret-read.py"],
    "Bash": ["no-offplan-bash.py", "no-emdash.py", "bash-guards.py"],
    "PowerShell": ["bash-guards.py"],
}


def packaging_cases(s):
    hooks_json = os.path.join(ROOT, "hooks", "hooks.json")
    try:
        spec = json.load(open(hooks_json, encoding="utf-8"))["hooks"]
    except Exception as exc:
        s.check("hooks.json readable", False, type(exc).__name__)
        return
    s.check("hooks.json readable", True)
    def words(h):
        # The banner runs in shell form (sh is not on the Windows PATH), python3 hooks in exec form.
        return h["args"] if "args" in h else [w.strip('"') for w in h["command"].split()[1:]]

    pre = {m["matcher"]: [h["args"][0].rsplit("/", 1)[-1] for h in m["hooks"]] for m in spec.get("PreToolUse", [])}
    for matcher, hooks in EXPECTED_WIRING.items():
        s.check("hooks.json PreToolUse " + matcher + " wires " + ", ".join(hooks), pre.get(matcher) == hooks, "found " + str(pre.get(matcher)))
    start = spec.get("SessionStart", [])
    s.check("hooks.json SessionStart present", bool(start))
    if start:
        matcher = start[0]["matcher"]
        s.check("hooks.json SessionStart matcher covers startup, clear, compact, fork", all(k in matcher for k in ("startup", "clear", "compact", "fork")), matcher)
        s.check("hooks.json SessionStart matcher leaves out resume (the resumed conversation already holds the rules)", "resume" not in matcher, matcher)
    sub = spec.get("SubagentStart", [])
    s.check("hooks.json SubagentStart injects the rules", bool(sub) and any("session-rules.sh" in words(h)[0] for m in sub for h in m["hooks"]))
    sub_args = [[a.replace("${CLAUDE_PLUGIN_ROOT}/hooks/", "") for a in words(h)] for m in sub for h in m["hooks"]]
    s.check("hooks.json SubagentStart wires two hooks, rules and docs (the harness caps each hook output at 10000 chars)", sub_args == [["session-rules.sh"], ["session-rules.sh", "docs"]], "found " + str(sub_args))
    for group in spec.values():
        for m in group:
            for h in m["hooks"]:
                target = words(h)[0].replace("${CLAUDE_PLUGIN_ROOT}", ROOT)
                s.check("hooks.json target exists: " + os.path.relpath(target, ROOT), os.path.isfile(target))
    claude = shutil.which("claude")
    if claude:
        # Validate what ships: tracked files only, so a machine-local CLAUDE.md at the root is not judged.
        with tempfile.TemporaryDirectory() as shipped:
            for rel in subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.splitlines():
                src = os.path.join(ROOT, rel)
                if os.path.isfile(src):
                    os.makedirs(os.path.dirname(os.path.join(shipped, rel)), exist_ok=True)
                    shutil.copy2(src, os.path.join(shipped, rel))
            proc = subprocess.run([claude, "plugin", "validate", shipped, "--strict"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        s.check("plugin validate --strict on the tracked files", proc.returncode == 0, (proc.stdout + proc.stderr).strip().splitlines()[-1] if (proc.stdout + proc.stderr).strip() else "no output")
    else:
        s.check("plugin validate --strict on the tracked files", False, "claude CLI not found on PATH")


def rules_cases(s):
    rules = os.path.join(ROOT, "rules", "work.md")
    s.check("rules/work.md exists", os.path.isfile(rules))
    if not os.path.isfile(rules):
        return
    text = open(rules, encoding="utf-8").read()
    s.check("rules/work.md passes no-emdash", run_hook("no-emdash.py", content(text)).returncode == 0)
    s.check("rules/work.md at most 70 lines", text.count("\n") <= 70, str(text.count("\n")))
    s.check("rules/core.md does not exist (the rules live in rules/work.md only)", not os.path.exists(os.path.join(ROOT, "rules", "core.md")))
    script = os.path.join(HERE, "session-rules.sh")
    s.check("session-rules.sh exists", os.path.isfile(script))
    if os.path.isfile(script):
        proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input="")
        s.check("session-rules.sh emits the guard string and the rules", proc.returncode == 0 and "=== kt rules ===" in proc.stdout and "## 2. Scope" in proc.stdout, proc.stdout[:80])
        proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}))
        s.check("session-rules.sh SessionStart stays plain stdout", proc.returncode == 0 and proc.stdout.startswith("=== kt rules ===") and "## 2. Scope" in proc.stdout, proc.stdout[:80])
        proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart", "agent_type": "claude"}))
        ok = False
        detail = proc.stdout[:80]
        try:
            out = json.loads(proc.stdout)
            ctx = out["hookSpecificOutput"]["additionalContext"]
            ok = out["hookSpecificOutput"]["hookEventName"] == "SubagentStart" and ctx.startswith("=== kt rules ===") and "## 2. Scope" in ctx
        except Exception as exc:
            detail = str(exc) + " | " + detail
        s.check("session-rules.sh SubagentStart emits additionalContext JSON (stdout is swallowed for subagents)", proc.returncode == 0 and ok, detail)
        clean = {k: v for k, v in os.environ.items() if k not in ("KT_ALLOW_EMDASH", "KT_ALLOW_OFFPLAN", "KT_ALLOW_DESTRUCTIVE")}
        start = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})
        proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=start, env=clean)
        s.check("session-rules.sh prints no WARNING when nothing is switched off", proc.returncode == 0 and "WARNING" not in proc.stdout, proc.stdout[:120])
        proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=start, env={**clean, "KT_ALLOW_OFFPLAN": "1"})
        s.check("session-rules.sh warns when KT_ALLOW_OFFPLAN=1 is set", "WARNING: KT_ALLOW_OFFPLAN=1" in proc.stdout and "## 2. Scope" in proc.stdout, proc.stdout[:120])
        proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=start, env={**clean, "KT_ALLOW_DESTRUCTIVE": "1"})
        s.check("session-rules.sh warns when KT_ALLOW_DESTRUCTIVE=1 is set", "WARNING: KT_ALLOW_DESTRUCTIVE=1" in proc.stdout, proc.stdout[:120])
        proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart"}), env={**clean, "KT_ALLOW_EMDASH": "1"})
        try:
            ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            ctx = proc.stdout
        s.check("session-rules.sh SubagentStart carries the KT_ALLOW_EMDASH warning inside additionalContext", "WARNING: KT_ALLOW_EMDASH=1" in ctx and "## 2. Scope" in ctx, ctx[:120])
        proj = tempfile.mkdtemp(prefix="kt-agentdocs-")
        os.makedirs(os.path.join(proj, "docs", "agent"))
        with open(os.path.join(proj, "docs/agent/PROJECT.md"), "w", encoding="utf-8") as f:
            f.write("# P\n\n## What this is\nthing\n\n## Current stage and consequences\nSTAGE-MARK-RESET\n\n## Architecture on one screen\nARCH-MARK-HIDDEN\n")
        with open(os.path.join(proj, "docs/agent/DECISIONS.md"), "w", encoding="utf-8") as f:
            f.write("# D\n\n## 1. Decided\nDECIDED-MARK-HIDDEN\n\n## 4. Open decisions\n1. [BLOCKS MERGE] PENDING-MARK-TAX\n")
        proc = subprocess.run(["sh", script, "docs"], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart", "cwd": proj}), env=clean)
        try:
            ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            ctx = proc.stdout
        s.check("session-rules.sh docs hook injects the stage section of PROJECT.md from cwd", "STAGE-MARK-RESET" in ctx and "=== docs/agent" in ctx, ctx[-160:])
        s.check("session-rules.sh docs hook injects the open decisions of DECISIONS.md from cwd", "PENDING-MARK-TAX" in ctx, ctx[-160:])
        s.check("session-rules.sh docs hook leaves the other sections out", "ARCH-MARK-HIDDEN" not in ctx and "DECIDED-MARK-HIDDEN" not in ctx, ctx[-160:])
        s.check("session-rules.sh docs hook adds no warning when both sections are found", "WARNING" not in ctx, ctx[:160])
        s.check("session-rules.sh docs hook carries only the docs/agent block, not the rules", ctx.startswith("=== docs/agent") and "=== kt rules ===" not in ctx, ctx[:120])
        proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart", "cwd": proj}), env=clean)
        try:
            ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            ctx = proc.stdout
        s.check("session-rules.sh SubagentStart rules hook leaves the docs/agent block to the docs hook", "## 2. Scope" in ctx and "=== docs/agent" not in ctx and "STAGE-MARK-RESET" not in ctx, ctx[-160:])
        proc = subprocess.run(["sh", script, "docs"], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart", "cwd": tempfile.mkdtemp(prefix="kt-nodocs-")}), env=clean)
        s.check("session-rules.sh docs hook prints nothing when cwd has no docs/agent", proc.returncode == 0 and proc.stdout.strip() == "", proc.stdout[-120:])
        stale = tempfile.mkdtemp(prefix="kt-staledocs-")
        os.makedirs(os.path.join(stale, "docs", "agent"))
        with open(os.path.join(stale, "docs/agent/PROJECT.md"), "w", encoding="utf-8") as f:
            f.write("# P\n\n## An older stage heading\nSTAGE-OLD\n")
        with open(os.path.join(stale, "docs/agent/DECISIONS.md"), "w", encoding="utf-8") as f:
            f.write("# D\n\n## 4. An older open heading\nPENDING-OLD\n")

        def stale_ctx():
            proc = subprocess.run(["sh", script, "docs"], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart", "cwd": stale}), env=clean)
            try:
                return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
            except Exception:
                return proc.stdout

        ctx = stale_ctx()
        s.check("session-rules.sh docs hook warns when ledger files exist but both sections are missing (older headings)", "WARNING" in ctx and "docs/agent/PROJECT.md has no" in ctx and "docs/agent/DECISIONS.md has no" in ctx and "Current stage" in ctx and "Open decisions" in ctx, ctx[:200])
        with open(os.path.join(stale, "docs/agent/PROJECT.md"), "w", encoding="utf-8") as f:
            f.write("# P\n\n## Current stage and consequences\nSTAGE-NEW\n")
        ctx = stale_ctx()
        s.check("session-rules.sh docs hook injects the stage it found and warns only about the missing open decisions", "STAGE-NEW" in ctx and "docs/agent/DECISIONS.md has no" in ctx and "docs/agent/PROJECT.md has no" not in ctx, ctx[:200])
        # Role-based injection: a reading subagent (reviewer, explorer, planner) gets sections 1, 4 and 5 only;
        # a coder, an unknown type or no type at all gets the whole file.
        def sub_ctx(agent_type):
            payload = {"hook_event_name": "SubagentStart"}
            if agent_type is not None:
                payload["agent_type"] = agent_type
            proc = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps(payload), env=clean)
            try:
                return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
            except Exception:
                return ""

        full = sub_ctx(None)
        reader = sub_ctx("reviewer")
        s.check("session-rules.sh gives a reviewer subagent sections 1, 4 and 5 and keeps the SUBAGENT header", all(k in reader for k in ("## 1.", "## 4.", "## 5.", "SUBAGENT", "=== kt rules ===")) and "## 2. Scope" not in reader and "## 3." not in reader and "## 6." not in reader, reader[:160])
        s.check("session-rules.sh reader injection is at most 60% of the full rules", 0 < len(reader) <= 0.6 * len(full), str(len(reader)) + " vs " + str(len(full)))
        for role in ("kt-coder", "Explore", "kt:design-review"):
            ctx = sub_ctx(role)
            expect_full = role == "kt-coder"
            s.check("session-rules.sh injection for agent_type " + role + (" is the full file" if expect_full else " is the reader cut"), ("## 2. Scope" in ctx) == expect_full and "## 4." in ctx, ctx[:120])
        s.check("session-rules.sh with no agent_type injects the full file", "## 2. Scope" in full and "## 6." in full, full[:120])
        sh = shutil.which("sh")
        proc = subprocess.run([sh, script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=start, env={**clean, "PATH": bare_path()})
        s.check("session-rules.sh warns when python3 is missing and still prints the rules", "WARNING: python3 not found" in proc.stdout and "## 2. Scope" in proc.stdout, proc.stdout[:120])
        # The Microsoft Store alias is a python3 that exists on PATH and cannot run: it must warn like an absent one.
        proc = subprocess.run([sh, script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=start, env={**clean, "PATH": bare_path('printf "Python was not found" >&2\nexit 9009')})
        s.check("session-rules.sh warns when python3 is a stub that cannot run (Windows Store alias)", "WARNING: python3 not found" in proc.stdout and "## 2. Scope" in proc.stdout, proc.stdout[:120])


def repo_hygiene_cases(s):
    proc = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for rel in proc.stdout.split():
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        s.check("no-emdash sweep: " + rel, run_hook("no-emdash.py", content(text)).returncode == 0)
    allowed = {chr(0xA7), chr(0x2013), chr(0x2014)}  # section sign, and the two dashes the rules must name
    for rel in subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.split():
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        hits = [str(n) for n, line in enumerate(open(path, encoding="utf-8", errors="replace").read().splitlines(), 1) if any(ord(ch) > 127 and ch not in allowed for ch in line)]
        s.check("ascii-only sweep: " + rel, not hits, str(len(hits)) + " lines with non-ASCII characters, first at line " + ", ".join(hits[:5]))
    reg = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
    recs = []
    if os.path.isfile(reg):
        try:
            recs = json.load(open(reg, encoding="utf-8"))["plugins"].get("kt@kt") or []
        except Exception:
            recs = []
    if not recs:
        s.check("installed cache matches the dev tree (kt not installed here)", True)
        return
    install = recs[0].get("installPath", "")
    tracked = subprocess.run(["git", "ls-files", "hooks", "rules", "commands", "agents", ".claude-plugin"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.split()
    stale = []
    for rel in tracked:
        dev, inst = os.path.join(ROOT, rel), os.path.join(install, rel)
        if not os.path.isfile(inst) or open(dev, "rb").read() != open(inst, "rb").read():
            stale.append(rel)
    s.check("installed cache matches the dev tree (bump then claude plugin update)", not stale, "stale: " + ", ".join(stale[:5]))


def extract_block(md_text, heading):
    lines = md_text.splitlines()
    i = next(i for i, l in enumerate(lines) if l.strip() == heading)
    j = next(k for k in range(i, len(lines)) if lines[k].startswith("```")) + 1
    end = next(k for k in range(j, len(lines)) if lines[k].startswith("```"))
    return "\n".join(lines[j:end]) + "\n"


def stop_gate_cases(s):
    text = open(os.path.join(ROOT, "commands", "new.md"), encoding="utf-8").read()
    try:
        code = extract_block(text, "### File `.claude/hooks/stop-gate.py`")
    except StopIteration:
        s.check("new.md embeds .claude/hooks/stop-gate.py", False, "heading or fenced block missing")
        return
    s.check("new.md embeds .claude/hooks/stop-gate.py", True)
    with tempfile.TemporaryDirectory() as tmp:
        gate = os.path.join(tmp, "stop-gate.py")
        open(gate, "w", encoding="utf-8").write(code)
        repo = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(repo, "docs", "agent"))
        os.makedirs(os.path.join(repo, ".claude"))
        handoff = os.path.join(repo, "docs/agent/HANDOFF.md")
        open(handoff, "w").write("old\n")
        open(os.path.join(repo, ".claude/session-start"), "w").write("")
        os.utime(handoff, (1, 1))

        def transcript(last_text):
            p = os.path.join(tmp, "t.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")
                f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": last_text}]}}) + "\n")
            return p

        def run(payload):
            return subprocess.run([sys.executable, gate], input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "CLAUDE_PROJECT_DIR": repo})

        proc = run({"transcript_path": transcript("done\n## REPORT\nSTATE: x")})
        s.check("stop-gate blocks a handoff when HANDOFF.md is older than the session stamp", proc.returncode == 2 and "HANDOFF" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:80])
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate lets a mid-task turn pass", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        proc = run({"transcript_path": transcript("## REPORT"), "stop_hook_active": True})
        s.check("stop-gate passes a repeated stop (stop_hook_active)", proc.returncode == 0, str(proc.returncode))
        os.utime(handoff, None)
        proc = run({"transcript_path": transcript("## REPORT")})
        s.check("stop-gate passes a handoff once HANDOFF.md is fresh", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        git(repo, "init", "-q")
        with open(os.path.join(repo, ".git", "info", "exclude"), "a", encoding="utf-8") as f:
            f.write("docs/agent/\n.claude/\n")
        open(os.path.join(repo, "a.txt"), "w").write("a\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        base = git(repo, "rev-parse", "HEAD").stdout.strip()
        os.utime(handoff, None)  # the base commit is setup, not an in-session commit: keep HANDOFF newer than it
        os.makedirs(os.path.join(repo, "docs/agent/plans"))
        open(os.path.join(repo, "docs/agent/plans/p.md"), "w", encoding="utf-8").write(plan_text(["src/*"]))
        open(os.path.join(repo, ".claude/active-plan"), "w", encoding="utf-8").write(json.dumps({"plan": "docs/agent/plans/p.md", "base": base}))
        open(os.path.join(repo, "stray.txt"), "w").write("x\n")
        # The audit runs the fence of the INSTALLED kt (the gate reads installed_plugins.json), so these two
        # cases need kt installed; a dev machine without it skips them, like repo_hygiene_cases does.
        if kt_installed():
            proc = run({"transcript_path": transcript("## REPORT")})
            s.check("stop-gate blocks a handoff when the plan audit finds drift", proc.returncode == 2 and "stray.txt" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
            os.remove(os.path.join(repo, "stray.txt"))
            proc = run({"transcript_path": transcript("## REPORT")})
            s.check("stop-gate passes a handoff when the plan audit is clean", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        else:
            os.remove(os.path.join(repo, "stray.txt"))
            s.check("stop-gate plan audit cases (kt not installed here, skipped)", True)
        # Git condition: a commit made in this session that is newer than
        # HANDOFF.md blocks ANY stop, REPORT or not; a silent session can no longer leave the ledger behind.
        os.remove(os.path.join(repo, ".claude/active-plan"))
        stamp = os.path.join(repo, ".claude/session-start")
        open(os.path.join(repo, "b.txt"), "w").write("b\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "in-session commit")
        ct = int(git(repo, "log", "-1", "--format=%ct").stdout.strip())
        os.utime(stamp, (ct - 100, ct - 100))
        os.utime(handoff, (ct - 50, ct - 50))
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate blocks any stop after an in-session commit newer than HANDOFF.md (no REPORT needed)", proc.returncode == 2 and "commit" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
        os.utime(handoff, (ct + 5, ct + 5))
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate passes once HANDOFF.md is touched after the commit", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        os.utime(handoff, (ct - 50, ct - 50))
        os.utime(stamp, (ct + 10, ct + 10))
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate ignores a commit made before this session started", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        os.utime(stamp, (ct - 100, ct - 100))
        git(repo, "add", "-f", "docs/agent/HANDOFF.md")
        git(repo, "commit", "-q", "-m", "handoff tracked (grandfather)")
        ct2 = int(git(repo, "log", "-1", "--format=%ct").stdout.strip())
        os.utime(handoff, (ct2 - 50, ct2 - 50))
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate treats a tracked HANDOFF.md committed in HEAD as fresh (grandfather repos)", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        # Ledger ceilings: the bootstrap rereads HANDOFF every session, so a session that committed (or hands off)
        # may not leave HANDOFF over 120 lines / 12000 bytes, or LESSONS over 40 lines.
        lessons = os.path.join(repo, "docs/agent/LESSONS.md")

        def write_lines(path, n, width=10):
            with open(path, "w", encoding="utf-8") as f:
                f.write("".join("l" * width + "\n" for _ in range(n)))

        write_lines(handoff, 121)
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate blocks after an in-session commit when HANDOFF.md exceeds 120 lines, naming the ceiling", proc.returncode == 2 and "120" in proc.stderr and "HANDOFF" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
        write_lines(handoff, 80)
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate passes with HANDOFF.md at 80 lines", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        write_lines(handoff, 100, width=130)
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate blocks when HANDOFF.md exceeds 12000 bytes even under 120 lines", proc.returncode == 2 and "12000" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
        write_lines(handoff, 80)
        write_lines(lessons, 41)
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate blocks when LESSONS.md exceeds 40 lines", proc.returncode == 2 and "LESSONS" in proc.stderr and "40" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
        write_lines(lessons, 40)
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate passes with LESSONS.md at 40 lines", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        write_lines(handoff, 121)
        os.utime(stamp, (ct2 + 10, ct2 + 10))
        proc = run({"transcript_path": transcript("mid-task question?")})
        s.check("stop-gate ignores an oversized HANDOFF.md on a mid-task stop when the session made no commit", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:80])
        os.utime(handoff, (ct2 + 20, ct2 + 20))
        proc = run({"transcript_path": transcript("## REPORT")})
        s.check("stop-gate blocks a handoff with an oversized HANDOFF.md even without a commit", proc.returncode == 2 and "120" in proc.stderr and "older" not in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])


def subagent_long_section_cases(s):
    """The open-decisions section is injected WHOLE: a silent 60-line cap hid the last items of a long
    ledger from every subagent, so they could not obey 'never decide the open items'."""
    script = os.path.join(HERE, "session-rules.sh")
    if not os.path.isfile(script):
        return
    clean = {k: v for k, v in os.environ.items() if k not in ("KT_ALLOW_EMDASH", "KT_ALLOW_OFFPLAN")}
    proj = tempfile.mkdtemp(prefix="kt-longdocs-")
    os.makedirs(os.path.join(proj, "docs", "agent"))
    body = "\n".join(str(i) + ". [NON-BLOCKING] item " + str(i) for i in range(1, 69))
    with open(os.path.join(proj, "docs/agent/DECISIONS.md"), "w", encoding="utf-8") as f:
        f.write("# D\n\n## 4. Open decisions\n" + body + "\n70. [NON-BLOCKING] LAST-MARK-70\n\n## 5. Other\nAFTER-MARK\n")
    proc = subprocess.run(["sh", script, "docs"], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart", "cwd": proj}), env=clean)
    try:
        ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    except Exception:
        ctx = proc.stdout
    s.check("session-rules.sh docs hook injects a 70-line open-decisions section whole (no silent cap)", "LAST-MARK-70" in ctx, ctx[-160:])
    s.check("session-rules.sh docs hook still stops at the next heading", "AFTER-MARK" not in ctx, ctx[-160:])


HOOK_BUDGET = 9500  # Claude Code 2.1.268 swaps any hook output over 10000 chars (OSr=1e4) for a 2000-char preview


def js_len(text):
    return len(text.encode("utf-16-le")) // 2


def hook_budget_cases(s):
    """Claude Code replaces a hook output longer than 10000 chars with a <persisted-output> stub and a
    2000-char preview, one hook at a time (a subagent fed 12895 chars saw only the banner, section 1 and
    half of section 2). Every kt hook stays under HOOK_BUDGET, counted the way the
    harness counts (JavaScript length), and a docs block cut to fit names the files to read."""
    script = os.path.join(HERE, "session-rules.sh")
    if not os.path.isfile(script):
        return
    clean = {k: v for k, v in os.environ.items() if k not in ("KT_ALLOW_EMDASH", "KT_ALLOW_OFFPLAN")}
    proj = tempfile.mkdtemp(prefix="kt-bigdocs-")
    os.makedirs(os.path.join(proj, "docs", "agent"))
    stage = "\n".join("stage line " + str(i) + " " + "s" * 60 for i in range(1, 41))
    items = "\n".join(str(i) + ". [NON-BLOCKING] open item " + str(i) + " " + "d" * 60 for i in range(1, 181))
    with open(os.path.join(proj, "docs/agent/PROJECT.md"), "w", encoding="utf-8") as f:
        f.write("# P\n\n## Current stage and consequences\n" + stage + "\n\n## Architecture on one screen\nARCH\n")
    with open(os.path.join(proj, "docs/agent/DECISIONS.md"), "w", encoding="utf-8") as f:
        f.write("# D\n\n## 4. Open decisions\n" + items + "\nBIG-TAIL-MARK\n")

    def ctx_of(args):
        proc = subprocess.run(["sh", script] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart", "cwd": proj}), env=clean)
        try:
            return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return proc.stdout

    rules = ctx_of([])
    s.check("session-rules.sh rules hook stays under the hook budget when docs/agent is huge", js_len(rules) <= HOOK_BUDGET and "## 2. Scope" in rules, str(js_len(rules)) + " chars")
    docs = ctx_of(["docs"])
    s.check("session-rules.sh docs hook stays under the hook budget when docs/agent is huge", js_len(docs) <= HOOK_BUDGET, str(js_len(docs)) + " chars")
    lines = docs.rstrip().splitlines()
    last = lines[-1] if lines else ""
    s.check("session-rules.sh docs hook ends a cut block with a pointer to the files to read", "docs/agent/PROJECT.md" in last and "docs/agent/DECISIONS.md" in last and "BIG-TAIL-MARK" not in docs, last[:200])
    body = lines[1:-1]
    s.check("session-rules.sh docs hook cuts at a line boundary", bool(body) and all(l == "" or l.startswith("#") or l.endswith("s" * 60) or l.endswith("d" * 60) for l in body), (body[-1] if body else "")[-80:])
    start = subprocess.run(["sh", script], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SessionStart", "source": "startup", "cwd": proj}), env=clean)
    s.check("session-rules.sh SessionStart output stays under the hook budget", js_len(start.stdout.strip()) <= HOOK_BUDGET, str(js_len(start.stdout.strip())) + " chars")


def docs_block_review_cases(s):
    """Holes a tier-1 review found in the docs hook: the harness counts JavaScript length, where
    an emoji is two; a long stage section must not push out the open decisions; a stray non-UTF-8 byte in a
    ledger must not drop the block without a word."""
    script = os.path.join(HERE, "session-rules.sh")
    if not os.path.isfile(script):
        return
    clean = {k: v for k, v in os.environ.items() if k not in ("KT_ALLOW_EMDASH", "KT_ALLOW_OFFPLAN")}

    def docs_of(project, decisions):
        proj = tempfile.mkdtemp(prefix="kt-review-")
        os.makedirs(os.path.join(proj, "docs", "agent"))
        if project is not None:
            with open(os.path.join(proj, "docs/agent/PROJECT.md"), "wb") as f:
                f.write(project)
        with open(os.path.join(proj, "docs/agent/DECISIONS.md"), "wb") as f:
            f.write(decisions)
        proc = subprocess.run(["sh", script, "docs"], capture_output=True, text=True, encoding="utf-8", errors="replace", input=json.dumps({"hook_event_name": "SubagentStart", "cwd": proj}), env=clean)
        try:
            return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return proc.stdout

    emoji = chr(0x1F534) + chr(0x1F7E1) + chr(0x1F7E2) + chr(0x1F535)
    items = "\n".join(str(i) + ". " + emoji + " [NON-BLOCKING] item " + "x" * 28 for i in range(1, 200))
    docs = docs_of(None, ("# D\n\n## 4. Open decisions\n" + items + "\n").encode("utf-8"))
    s.check("session-rules.sh docs hook counts length the way the harness does (an emoji is two JavaScript chars)", js_len(docs) <= HOOK_BUDGET, str(js_len(docs)) + " js chars, " + str(len(docs)) + " python chars")
    stage = "## Current stage and consequences\n" + "word " * 1880 + "\n"
    docs = docs_of(("# P\n\n" + stage).encode("utf-8"), "# D\n\n## 4. Open decisions\n1. [BLOCKS MERGE] ONE-OPEN-ITEM\n".encode("utf-8"))
    s.check("session-rules.sh docs hook keeps the open decisions when the stage section alone fills the budget", "ONE-OPEN-ITEM" in docs, docs[:160])
    docs = docs_of(None, b"# D\n\n## 4. Open decisions\n1. caf\xe9 BYTE-MARK\n")
    s.check("session-rules.sh docs hook survives a non-UTF-8 byte in the ledger instead of dropping the block", "BYTE-MARK" in docs and "=== docs/agent" in docs, repr(docs[:120]))


SKELETON_HEADS = [
    "### File `.claude/hooks/session-start.sh` (chmod +x after creating it)",
    "### File `.claude/hooks/stop-gate.py`",
    "### File `.claude/settings.json` (if it already exists, MERGE, never overwrite existing keys)",
]
# Stamp = the kt version in which these blocks last changed; when a block changes, update both together.
SKELETON_PIN = ("1.5.0", "b8b0ced7815695c2a88833bb80064104d8dd44d8a8e15282dc725ba945d4e0d0")


def skeleton_digest(md_text):
    parts = ["\n".join(l for l in extract_block(md_text, h).splitlines() if "kt-skeleton" not in l) for h in SKELETON_HEADS]
    return hashlib.sha256("\n\n".join(parts).encode("utf-8")).hexdigest()


def version_tuple(v):
    return tuple(int(x) for x in v.split("."))


def skeleton_stamp_cases(s):
    """The stamp names the kt version in which the skeleton last changed, so /kt:load asks for an upgrade
    only when the skeleton really moved; the stamp and the skeleton content are pinned together."""
    text = open(os.path.join(ROOT, "commands", "new.md"), encoding="utf-8").read()
    ver = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8"))["version"]
    try:
        code = extract_block(text, SKELETON_HEADS[0])
        digest = skeleton_digest(text)
    except StopIteration:
        s.check("new.md embeds the three skeleton blocks", False, "heading or fenced block missing")
        return
    found = re.search(r"kt-skeleton ([0-9][0-9.]*)", code)
    stamp = found.group(1) if found else ""
    s.check("skeleton stamp and skeleton content are pinned together (change both, deliberately)", (stamp, digest) == SKELETON_PIN, "stamp " + stamp + ", digest " + digest)
    s.check("skeleton stamp is not newer than the plugin version", bool(stamp) and version_tuple(stamp) <= version_tuple(ver), stamp + " vs " + ver)
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "session-start.sh")
        open(script, "w", encoding="utf-8").write(code)
        proj = os.path.join(tmp, "proj")
        agent = os.path.join(proj, "docs", "agent")
        os.makedirs(agent)
        ledger = {
            "PROJECT.md": "# P\n\n## What this is\nWHAT-MARK\n\n## Current stage and consequences\nSTAGE-MARK\n",
            "DECISIONS.md": "# D\n\n## 1. Decided\nDECIDED-MARK\n\n## 4. Open decisions\nOPEN-MARK\n",
            "HANDOFF.md": "# H\n\n## Where we are\nWHERE-MARK\n\n## Next steps\nNEXT-MARK\n\n## Known traps\nTRAP-MARK\n",
            "LESSONS.md": "# L\nLESSON-MARK\n",
            "ACCESS.md": "# A\nACCESS-MARK\n",
        }
        for name, body in ledger.items():
            open(os.path.join(agent, name), "w", encoding="utf-8").write(body)
        stamp_file = os.path.join(proj, ".claude", "session-start")
        confirm = "Do not start coding until the user confirms"

        def start(payload):
            if os.path.exists(stamp_file):
                os.remove(stamp_file)
            proc = subprocess.run(["sh", script], input=payload, capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "CLAUDE_PROJECT_DIR": proj})
            return proc, os.path.exists(stamp_file)

        for label, payload in (("startup", '{"source":"startup"}'), ("clear", '{"source":"clear"}'), ("no stdin", ""), ("an unknown source", '{"source":"other"}')):
            proc, touched = start(payload)
            out = proc.stdout
            s.check("skeleton session-start.sh on " + label + " prints the stamp, stage, open decisions and next steps, and asks to wait for the user", proc.returncode == 0 and touched and ("kt-skeleton " + stamp) in out and all(m in out for m in ("STAGE-MARK", "OPEN-MARK", "NEXT-MARK")) and confirm in out, out[:300])
            s.check("skeleton session-start.sh on " + label + " leaves out the rest of the ledger and the read-in-full instruction", not any(m in out for m in ("WHAT-MARK", "DECIDED-MARK", "WHERE-MARK", "TRAP-MARK", "LESSON-MARK", "ACCESS-MARK")) and "Read the saved file" not in out, out[:300])
        for src in ("compact", "fork"):
            proc, touched = start('{"source":"' + src + '"}')
            out = proc.stdout
            s.check("skeleton session-start.sh on " + src + " prints the same block without the wait for the user", proc.returncode == 0 and touched and all(m in out for m in ("STAGE-MARK", "OPEN-MARK", "NEXT-MARK")) and confirm not in out, out[:300])
        proc, touched = start('{"source":"resume"}')
        s.check("skeleton session-start.sh on resume prints only the stamp line and still touches the session stamp", proc.returncode == 0 and touched and ("kt-skeleton " + stamp) in proc.stdout and len(proc.stdout) < 300 and "STAGE-MARK" not in proc.stdout, proc.stdout[:300])
        open(os.path.join(agent, "PROJECT.md"), "w", encoding="utf-8").write("# P\n\n## Current stage and consequences\nSTAGE-MARK\n" + ("word " * 60 + "\n") * 80)
        proc, touched = start('{"source":"startup"}')
        s.check("skeleton session-start.sh stays under the 10000-char hook limit and names the files to read when it cuts", proc.returncode == 0 and len(proc.stdout) < 10000 and "docs/agent/PROJECT.md" in proc.stdout and "kt-skeleton" in proc.stdout, str(len(proc.stdout)) + " " + proc.stdout[-200:])


def skeleton_compare_cases(s):
    """The adopt upgrade compares a repo's skeleton with kt's byte for byte before copying anything, so a
    local change is shown and asked about instead of silently overwritten; the stamp line is ignored."""
    try:
        code = extract_block(open(os.path.join(ROOT, "commands", "adopt.md"), encoding="utf-8").read(), "## Skeleton compare script")
    except StopIteration:
        s.check("adopt.md embeds the skeleton compare script under '## Skeleton compare script'", False, "heading or fenced block missing")
        return
    s.check("adopt.md embeds the skeleton compare script under '## Skeleton compare script'", True)
    new_md = os.path.join(ROOT, "commands", "new.md")
    md = open(new_md, encoding="utf-8").read()
    ss, sg, st = ".claude/hooks/session-start.sh", ".claude/hooks/stop-gate.py", ".claude/settings.json"
    full = {ss: extract_block(md, SKELETON_HEADS[0]), sg: extract_block(md, SKELETON_HEADS[1]), st: extract_block(md, SKELETON_HEADS[2])}
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "skeleton_compare.py")
        open(script, "w", encoding="utf-8").write(code)

        def run(name, files):
            root = os.path.join(tmp, name)
            for rel, body in files.items():
                os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
                open(os.path.join(root, rel), "w", encoding="utf-8").write(body)
            before = {rel: open(os.path.join(root, rel), "rb").read() for rel in files}
            proc = subprocess.run([sys.executable, script, new_md, root], capture_output=True, text=True, encoding="utf-8", errors="replace")
            after = {rel: open(os.path.join(root, rel), "rb").read() for rel in files}
            return proc, before == after and sorted(os.listdir(os.path.join(root, ".claude"))) == sorted({r.split("/")[1] for r in files})

        proc, untouched = run("same", full)
        s.check("skeleton compare: an unchanged skeleton is SAME (exit 0)", proc.returncode == 0 and "RESULT: SAME" in proc.stdout, (proc.stdout + proc.stderr)[-300:])
        s.check("skeleton compare: reading a repo writes nothing into it", untouched)
        old = dict(full)
        old[ss] = "\n".join('echo "kt-skeleton 1.0.0 (older wording)"' if "kt-skeleton" in l else l for l in full[ss].split("\n"))
        proc, _ = run("stamp", old)
        s.check("skeleton compare: a different stamp line alone is still SAME", proc.returncode == 0 and "RESULT: SAME" in proc.stdout, proc.stdout[-300:])
        edited = dict(full)
        edited[sg] = full[sg] + "# LOCAL-EDIT-MARK\n"
        proc, untouched = run("edited", edited)
        s.check("skeleton compare: a local edit to stop-gate.py is DIFFERS (exit 1) and the diff shows the edited line", proc.returncode == 1 and "stop-gate.py: DIFFERS" in proc.stdout and "+# LOCAL-EDIT-MARK" in proc.stdout, proc.stdout[-400:])
        s.check("skeleton compare: a repo with a local edit is left untouched", untouched)
        missing = dict(full)
        del missing[sg]
        proc, _ = run("missing", missing)
        s.check("skeleton compare: a missing stop-gate.py is MISSING (exit 1)", proc.returncode == 1 and "stop-gate.py: MISSING" in proc.stdout, proc.stdout[-300:])
        local = dict(full)
        local[".claude/settings.local.json"] = full[st]
        local[st] = '{"permissions": {}}\n'
        proc, _ = run("local", local)
        s.check("skeleton compare: kt hook entries kept in settings.local.json count, and the output names that file", proc.returncode == 0 and "settings.local.json" in proc.stdout, proc.stdout[-300:])
        narrow = dict(full)
        narrowed = json.loads(full[st])
        narrowed["hooks"]["SessionStart"][0]["matcher"] = "startup|resume|clear"
        narrow[st] = json.dumps(narrowed, indent=2)
        proc, _ = run("narrow", narrow)
        s.check("skeleton compare: a SessionStart group running the kt command with a narrower matcher is DIFFERS (exit 1), not MISSING", proc.returncode == 1 and "hooks.SessionStart: DIFFERS" in proc.stdout and "MISSING" not in proc.stdout, proc.stdout[-400:])
        prompt = dict(full)
        prompt[st] = json.dumps({"hooks": {"SessionStart": json.loads(full[st])["hooks"]["SessionStart"], "Stop": [{"hooks": [{"type": "prompt", "prompt": "You are a stop-gate evaluator"}]}]}})
        proc, _ = run("prompt", prompt)
        s.check("skeleton compare: a Stop prompt hook in place of the kt command hook is MISSING (exit 1)", proc.returncode == 1 and "Stop: MISSING" in proc.stdout, proc.stdout[-300:])


def cost_cases(s):
    """/kt:cost measures weighted cost from transcripts: one API response is written as several JSONL
    lines sharing message.id (343 of 576 ids in a real session), so counting lines overstates 2.3x."""
    path = os.path.join(ROOT, "commands", "cost.md")
    if not os.path.isfile(path):
        s.check("commands/cost.md exists", False, "file missing")
        return
    s.check("commands/cost.md exists", True)
    try:
        code = extract_block(open(path, encoding="utf-8").read(), "## Script")
    except StopIteration:
        s.check("cost.md embeds the cost script under '## Script'", False, "heading or fenced block missing")
        return
    s.check("cost.md embeds the cost script under '## Script'", True)

    def usage(i, cw, cr, o):
        return {"input_tokens": i, "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr, "output_tokens": o}

    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "kt_cost.py")
        open(script, "w", encoding="utf-8").write(code)
        cwd = os.path.join(tmp, "repo")
        os.makedirs(cwd)
        proj = os.path.join(tmp, "projects", "-some-slug")
        os.makedirs(os.path.join(proj, "sid", "subagents"))
        real = os.path.realpath(cwd)
        with open(os.path.join(proj, "sid.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "cwd": real, "sessionId": "sid", "message": {"role": "user", "content": "hi"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "cwd": real, "sessionId": "sid", "message": {"id": "m1", "usage": usage(10, 1000, 20000, 100), "content": [{"type": "text", "text": "a"}]}}) + "\n")
            f.write(json.dumps({"type": "assistant", "cwd": real, "sessionId": "sid", "message": {"id": "m1", "usage": usage(10, 1000, 20000, 100), "content": [{"type": "tool_use", "name": "Bash"}]}}) + "\n")
            f.write(json.dumps({"type": "assistant", "cwd": real, "sessionId": "sid", "message": {"id": "m2", "usage": usage(0, 500, 21000, 50), "content": []}}) + "\n")
        with open(os.path.join(proj, "sid", "subagents", "agent-x.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "cwd": real, "sessionId": "sid", "message": {"id": "s1", "usage": usage(0, 2000, 0, 10), "content": []}}) + "\n")
        other = os.path.join(tmp, "projects", "-other-slug")
        os.makedirs(other)
        with open(os.path.join(other, "zzz.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "cwd": os.path.join(tmp, "elsewhere"), "sessionId": "zzz", "message": {"role": "user", "content": "hi"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "cwd": os.path.join(tmp, "elsewhere"), "sessionId": "zzz", "message": {"id": "z1", "usage": usage(0, 0, 0, 999999), "content": []}}) + "\n")
        env = {**os.environ, "KT_COST_PROJECTS": os.path.join(tmp, "projects")}
        proc = subprocess.run([sys.executable, script], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        out = proc.stdout
        s.check("cost script runs and picks the session whose cwd matches (not the newest anywhere)", proc.returncode == 0 and "sid" in out and "zzz" not in out, (proc.stderr or out)[:160])
        # m1 once: 10 + 1000*2 + 20000*0.1 + 100*5 = 4510; m2: 500*2 + 21000*0.1 + 50*5 = 3350; total 7860 over 2 turns
        s.check("cost script dedups by message id (7,860 weighted over 2 turns, not 12,370 over 3)", "7,860" in out and "turns: 2" in out and "12,370" not in out, out[:200])
        s.check("cost script breaks the total into cache read, cache write, output, input", all(k in out for k in ("cache read", "cache write", "output", "input")), out[:200])
        # subagent: 2000*2 + 10*5 = 4050
        s.check("cost script sums subagent transcripts under <session>/subagents", "4,050" in out and "agent-x" in out, out[:200])
        proc = subprocess.run([sys.executable, script, os.path.join(other, "zzz.jsonl")], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        s.check("cost script accepts an explicit transcript path", proc.returncode == 0 and "zzz" in proc.stdout, (proc.stderr or proc.stdout)[:160])


GATE_WORDS = ["quick gate", "full gate"]
GATE_FILES = ["commands/new.md", "commands/adopt.md", "commands/go.md", "commands/save.md", "commands/lane.md"]
TEXT_WIRING = [
    ("commands/load.md", "Reconcile the ledger with the machine"),
    ("commands/load.md", "kt-skeleton"),
    ("commands/load.md", "persisted-output"),
    ("commands/load.md", "Active plan"),
    ("commands/load.md", "is not older than"),
    ("commands/adopt.md", "settings.local.json"),
    ("commands/go.md", "Active plan"),
    ("commands/save.md", "Parked questions"),
    ("commands/report.md", "clean tree"),
    ("commands/plan.md", "Risk tier"),
    ("commands/plan.md", "already seen RED on the old code"),
    ("commands/new.md", "Current stage and consequences"),
    ("commands/new.md", "Open decisions"),
    ("commands/new.md", "Parked questions"),
    ("commands/new.md", "Active plan"),
    ("commands/new.md", "[BLOCKS MERGE]"),
    ("commands/new.md", "[NON-BLOCKING]"),
    ("commands/new.md", "Quick gate:"),
    ("commands/new.md", "Full gate:"),
    ("commands/new.md", "Last updated"),
    ("hooks/no-offplan-edit.py", "Parked questions"),
    ("README.md", "/kt:cost"),
    ("README.md", "## Overview"),
    ("rules/work.md", "in the language the user writes in"),
    ("rules/work.md", "one recorded red run"),
    ("rules/work.md", "after 2 failed fix attempts on the same check"),
    ("rules/work.md", "never re-execute a run to see its output again"),
    ("commands/save.md", "Short path"),
    ("commands/save.md", "`/clear`"),
    ("commands/load.md", "HANDOFF is fresh"),
    ("README.md", "in the language the user writes in"),
]


def gate_wording_cases(s):
    for rel in GATE_FILES:
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read().lower()
        missing = [w for w in GATE_WORDS if w not in text]
        s.check("gate levels named in " + rel, not missing, "missing " + ", ".join(missing))
    for rel, needle in TEXT_WIRING:
        path = os.path.join(ROOT, rel)
        ok = os.path.isfile(path) and needle in open(path, encoding="utf-8").read()
        s.check("text wiring: " + rel + " has '" + needle + "'", ok)
    rules_sh = open(os.path.join(HERE, "session-rules.sh"), encoding="utf-8").read()
    skeleton = open(os.path.join(ROOT, "commands", "new.md"), encoding="utf-8").read()
    needles = re.findall(r'=\s*section\(.*"([^"]+)"\)\s*$', rules_sh, re.M)
    s.check("session-rules.sh looks up exactly two ledger sections", len(needles) == 2, str(needles))
    for needle in needles:
        named = re.search(r'section "(?:\d+\. )?' + re.escape(needle), skeleton, re.I)
        s.check("ledger section '" + needle + "' that the docs hook looks up is a quoted section name in the new.md skeleton", bool(named))


REPORT_SECTIONS = ["STATE", "DONE", "EVIDENCE", "DECIDED", "BLOCKED", "WAITING_ON", "UNSURE", "NEXT"]
REPORT_FILES = ["commands/report.md", "commands/save.md", "commands/adopt.md"]


def backup_cases(s):
    """kt-backup.py mirrors the machine-local agent layer into ~/kt-backups without rsync: idempotent,
    deletes what the source no longer has, skips .claude/worktrees, and refuses to run from a lane worktree."""
    helper = os.path.join(HERE, "kt-backup.py")
    s.check("hooks/kt-backup.py exists", os.path.isfile(helper))
    if not os.path.isfile(helper):
        return
    home = tempfile.mkdtemp(prefix="kt-backup-home-")
    repo = os.path.join(tempfile.mkdtemp(prefix="kt-backup-repo-"), "proj")
    os.makedirs(os.path.join(repo, "docs", "agent", "plans"))
    os.makedirs(os.path.join(repo, ".claude", "hooks"))
    os.makedirs(os.path.join(repo, ".claude", "worktrees", "lane-1"))
    for rel, body in (("docs/agent/HANDOFF.md", "h1"), ("docs/agent/plans/p.md", "p"), ("CLAUDE.md", "c"), (".claude/hooks/x.sh", "x"), (".claude/worktrees/lane-1/big", "w")):
        with open(os.path.join(repo, rel), "w", encoding="utf-8") as f:
            f.write(body)
    git(repo, "init", "-q")
    git(repo, "commit", "-q", "--allow-empty", "-m", "root")

    def run():
        return subprocess.run([sys.executable, helper], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "HOME": home, "USERPROFILE": home})

    def tree(root):
        out = []
        for d, _, files in os.walk(root):
            for name in files:
                out.append(os.path.relpath(os.path.join(d, name), root).replace("\\", "/"))
        return sorted(out)

    dest = os.path.join(home, "kt-backups", "proj")
    proc = run()
    s.check("kt-backup.py exits 0 and names the destination", proc.returncode == 0 and "kt-backups" in proc.stdout, (proc.stdout + proc.stderr)[:160])
    first = tree(dest)
    s.check("kt-backup.py copies docs/agent, CLAUDE.md and .claude, not worktrees", first == ["CLAUDE.md", "docs-agent/HANDOFF.md", "docs-agent/plans/p.md", "dot-claude/hooks/x.sh"], str(first))
    proc = run()
    s.check("kt-backup.py is idempotent (second run, same tree, exit 0)", proc.returncode == 0 and tree(dest) == first, str(tree(dest)))
    os.remove(os.path.join(repo, "docs", "agent", "plans", "p.md"))
    with open(os.path.join(repo, "docs", "agent", "HANDOFF.md"), "w", encoding="utf-8") as f:
        f.write("h2")
    run()
    s.check("kt-backup.py removes files the source no longer has and refreshes changed ones", tree(dest) == ["CLAUDE.md", "docs-agent/HANDOFF.md", "dot-claude/hooks/x.sh"] and open(os.path.join(dest, "docs-agent", "HANDOFF.md"), encoding="utf-8").read() == "h2", str(tree(dest)))
    lane = os.path.join(repo, ".claude", "worktrees", "lane-2")
    git(repo, "worktree", "add", "-q", lane, "-b", "lane-2")
    proc = subprocess.run([sys.executable, helper], cwd=lane, capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "HOME": home, "USERPROFILE": home})
    s.check("kt-backup.py refuses to run from a lane worktree and says so", proc.returncode == 0 and "lane" in proc.stdout.lower() and tree(dest) == ["CLAUDE.md", "docs-agent/HANDOFF.md", "dot-claude/hooks/x.sh"], (proc.stdout + proc.stderr)[:160])


def gate_weakening_cases(s):
    """no-gate-weakening.py: a commit that skips, focuses or removes a test, regenerates a snapshot without its
    owning test, or runs with --no-verify, is refused unless the message carries a `Gate-edit: <reason>` line;
    `--audit <base>` lists the same hunks over a committed range."""
    hook = os.path.join(HERE, "no-gate-weakening.py")
    s.check("hooks/no-gate-weakening.py exists", os.path.isfile(hook))
    if not os.path.isfile(hook):
        return
    repo = tempfile.mkdtemp(prefix="kt-gate-")
    os.makedirs(os.path.join(repo, "src", "__snapshots__"))
    files = {
        "src/a.test.js": 'test("adds", () => { expect(1 + 1).toBe(2); });\nit("keeps", () => { expect(true).toBe(true); });\n',
        "src/__snapshots__/a.test.js.snap": "exports[`adds 1`] = `2`;\n",
        "src/test_b.py": "def test_b():\n    assert 1\n",
        "src/util.js": "export const x = 1;\n",
    }
    for rel, body in files.items():
        with open(os.path.join(repo, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()

    def write(rel, body):
        with open(os.path.join(repo, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    def commit_hook(command):
        return run_hook("no-gate-weakening.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": repo, "tool_input": {"command": command}})

    def reset():
        git(repo, "reset", "-q")
        git(repo, "checkout", "-q", "--", ".")

    write("src/a.test.js", files["src/a.test.js"].replace('test("adds"', 'test.skip("adds"'))
    git(repo, "add", "-A")
    proc = commit_hook('git commit -m "tidy"')
    s.check("no-gate-weakening blocks a commit that adds .skip, naming the file and the way through", proc.returncode == 2 and "a.test.js" in proc.stderr and "Gate-edit:" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:160])
    proc = commit_hook('git commit -m "tidy" -m "Gate-edit: flaky under load, tracked in DECISIONS"')
    s.check("no-gate-weakening lets the same commit through with a Gate-edit trailer", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:120])
    proc = commit_hook("ls -la")
    s.check("no-gate-weakening ignores a command that is not a commit", proc.returncode == 0, str(proc.returncode))
    reset()
    write("src/a.test.js", 'test("adds", () => { expect(1 + 1).toBe(2); });\n')
    git(repo, "add", "-A")
    proc = commit_hook('git commit -m "drop a test"')
    s.check("no-gate-weakening blocks a commit that removes a test function", proc.returncode == 2 and "a.test.js" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:160])
    reset()
    write("src/test_b.py", "import pytest\n@pytest.mark.skip\ndef test_b():\n    assert 1\n")
    git(repo, "add", "-A")
    proc = commit_hook('git commit -m "skip"')
    s.check("no-gate-weakening blocks an added @pytest.mark.skip", proc.returncode == 2 and "test_b.py" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:160])
    reset()
    write("src/__snapshots__/a.test.js.snap", "exports[`adds 1`] = `3`;\n")
    git(repo, "add", "-A")
    proc = commit_hook('git commit -m "update snapshot"')
    s.check("no-gate-weakening blocks a snapshot change whose owning test did not change", proc.returncode == 2 and "a.test.js.snap" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:160])
    write("src/a.test.js", files["src/a.test.js"] + "\n")
    git(repo, "add", "-A")
    proc = commit_hook('git commit -m "update snapshot with its test"')
    s.check("no-gate-weakening lets a snapshot change through when its owning test changed too", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:120])
    reset()
    write("src/util.js", "export const x = 2;\n")
    git(repo, "add", "-A")
    proc = commit_hook('git commit -m "bump x"')
    s.check("no-gate-weakening lets an ordinary commit through", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:120])
    proc = commit_hook('git commit --no-verify -m "bump x"')
    s.check("no-gate-weakening blocks --no-verify on a commit", proc.returncode == 2 and "no-verify" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
    write("src/a.test.js", files["src/a.test.js"].replace('it("keeps"', 'it.only("keeps"'))
    git(repo, "add", "-A")
    proc = commit_hook('git commit -a -m "focus"')
    s.check("no-gate-weakening blocks .only committed with -a (reads the HEAD diff)", proc.returncode == 2 and "a.test.js" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:160])
    git(repo, "commit", "-q", "-m", "focus landed")
    audit = subprocess.run([sys.executable, hook, "--audit", base], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    s.check("no-gate-weakening --audit <base> lists the committed .only over the range", audit.returncode == 2 and "a.test.js" in audit.stdout, str(audit.returncode) + " " + (audit.stdout + audit.stderr)[:160])
    clean = subprocess.run([sys.executable, hook, "--audit", "HEAD"], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    s.check("no-gate-weakening --audit on an empty range is clean", clean.returncode == 0, str(clean.returncode) + " " + (clean.stdout + clean.stderr)[:120])
    # The commit the agent really types: another directory, staging in the same command, PowerShell, a message file.
    skipped = 'test.' + 'skip("adds", () => { expect(1 + 1).toBe(2); });\n'

    def from_elsewhere(command, tool="Bash"):
        return run_hook("no-gate-weakening.py", {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": tempfile.gettempdir(), "tool_input": {"command": command}})

    posix = repo.replace("\\", "/")
    write("src/a.test.js", skipped)
    git(repo, "add", "-A")
    proc = from_elsewhere('git -C "' + posix + '" commit -m "tidy"')
    s.check("no-gate-weakening follows git -C to the repo being committed", proc.returncode == 2 and "a.test.js" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
    if os.name == "nt":
        msys = "/" + posix[0].lower() + posix[2:]
        proc = from_elsewhere('git -C "' + msys + '" commit -m "tidy"')
        s.check("no-gate-weakening reads a Git Bash path (/c/...) on Windows", proc.returncode == 2 and "a.test.js" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
    proc = from_elsewhere('cd "' + posix + '" && git commit -m "tidy"')
    s.check("no-gate-weakening follows a cd before the commit", proc.returncode == 2 and "a.test.js" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
    proc = from_elsewhere('git -C "' + posix + '" commit -m "tidy"', "PowerShell")
    s.check("no-gate-weakening scans a commit from the PowerShell tool", proc.returncode == 2 and "a.test.js" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
    proc = from_elsewhere('git -C "' + posix + '" log --grep commit')
    s.check("no-gate-weakening ignores a git command that only mentions commit", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:120])
    msg = os.path.join(repo, "..", os.path.basename(repo) + "-msg.txt")
    with open(msg, "w", encoding="utf-8") as f:
        f.write("tidy\n\nGate-edit: flaky under load\n")
    proc = from_elsewhere('git -C "' + posix + '" commit -F "' + os.path.abspath(msg).replace("\\", "/") + '"')
    s.check("no-gate-weakening reads the Gate-edit reason from a message file", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:120])
    git(repo, "reset", "-q")
    proc = from_elsewhere('git -C "' + posix + '" add -A && git -C "' + posix + '" commit -m "tidy"')
    s.check("no-gate-weakening sees what a git add in the same command is about to stage", proc.returncode == 2 and "a.test.js" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
    proc = from_elsewhere('git -C "' + posix + '" commit -am "tidy"')
    s.check("no-gate-weakening reads -am as -a (the unstaged diff)", proc.returncode == 2 and "a.test.js" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:120])
    proc = from_elsewhere('git -C "' + posix + '" commit -m "drop -a and --no-verify from the docs"')
    s.check("no-gate-weakening does not read flags out of the message text", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:120])
    proc = from_elsewhere('cd "' + posix + '" && git add -A && git commit -am "tidy" -m "Gate-edit: flaky under load"')
    s.check("no-gate-weakening accepts the reason on a same-command add", proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:120])
    reset()
    proc = run_hook("no-gate-weakening.py", "not json")
    s.check("no-gate-weakening lets a broken payload through like the other hooks", proc.returncode == 0, str(proc.returncode))


def destructive_cases(s):
    """no-destructive.py: the hard set (force-push, a hard reset, a forced clean, skipping commit hooks, disk
    operations) is refused with exit 2; the recursive deletes aimed at an absolute, home or parent path, and
    table drops, get a JSON `ask`; everything else, including deletes inside the repo and $TMPDIR, passes."""
    hook = os.path.join(HERE, "no-destructive.py")
    s.check("hooks/no-destructive.py exists", os.path.isfile(hook))
    if not os.path.isfile(hook):
        return

    def bash(command, tool="Bash"):
        return run_hook("no-destructive.py", {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}})

    def decision(proc):
        try:
            return json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            return ""

    hard = [
        ("git push --force origin main", "force"),
        ("git push -f origin main", "force"),
        ("git push origin +main", "force"),
        ("git reset --hard HEAD~1", "hard reset"),
        ("git clean -fd", "clean"),
        ("git commit --no-verify -m x", "verify"),
        ("format d:", "format"),
        ("Format-Volume -DriveLetter D", "disk"),
    ]
    for cmd, word in hard:
        proc = bash(cmd, "PowerShell" if cmd[0].isupper() else "Bash")
        s.check("no-destructive refuses: " + cmd, proc.returncode == 2 and word.lower() in proc.stderr.lower(), str(proc.returncode) + " " + proc.stderr[:100])
    asks = [
        ("rm -rf /var/data", "Bash"),
        ("rm -r ~/projects/x", "Bash"),
        ("rm -rf ../sibling", "Bash"),
        ("rm -rf C:/Users/x/tmp", "Bash"),
        ("Remove-Item -Recurse -Force C:\\Users\\x\\tmp", "PowerShell"),
        ("rd /s /q build", "Bash"),
        ("psql -c 'DROP TABLE users'", "Bash"),
        ("kubectl delete deployment api", "Bash"),
    ]
    for cmd, tool in asks:
        proc = bash(cmd, tool)
        s.check("no-destructive asks: " + cmd, proc.returncode == 0 and decision(proc) == "ask", str(proc.returncode) + " " + (proc.stdout + proc.stderr)[:100])
    passes = [
        "ls -la",
        "git push origin master",
        "rm -rf .claude/worktrees/lane-1",
        'rm -rf "$TMPDIR/kt-probe"',
        "rm -rf node_modules/.cache",
        "git worktree remove --force .claude/worktrees/lane-1",
        'git commit -m "note: the old force-push and hard reset advice is gone"',
        "grep -rn 'reset --hard' docs/",
    ]
    for cmd in passes:
        proc = bash(cmd)
        s.check("no-destructive passes: " + cmd, proc.returncode == 0 and decision(proc) == "", str(proc.returncode) + " " + (proc.stdout + proc.stderr)[:100])
    proc = run_hook("no-destructive.py", "not json")
    s.check("no-destructive lets a broken payload through like the other hooks", proc.returncode == 0, str(proc.returncode))
    proc = run_hook("no-destructive.py", {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "x"}})
    s.check("no-destructive ignores tools other than Bash and PowerShell", proc.returncode == 0 and decision(proc) == "", str(proc.returncode))


def exec_form_cases(s):
    """Exec form spawns `command` from PATH with no shell. Windows PATH has no sh (only Git Bash's shell form
    finds it), so a banner wired `sh` + args fails with 'Executable not found' and no session gets the rules."""
    spec = json.load(open(os.path.join(HERE, "hooks.json"), encoding="utf-8"))["hooks"]
    entries = [h for groups in spec.values() for g in groups for h in g["hooks"]]
    s.check("hooks.json never spawns sh in exec form", not [h for h in entries if h.get("command") == "sh" and "args" in h], "")
    banner = [h for h in entries if "session-rules.sh" in h.get("command", "") + " ".join(h.get("args", []))]
    s.check("hooks.json quotes the plugin root in the shell-form banner commands", len(banner) == 3 and all('"${CLAUDE_PLUGIN_ROOT}/hooks/session-rules.sh"' in h["command"] for h in banner), str(banner)[:200])
    sh = shutil.which("bash") or shutil.which("sh")
    for h in banner:
        line = h["command"].replace("${CLAUDE_PLUGIN_ROOT}", ROOT.replace("\\", "/"))
        proc = subprocess.run([sh, "-c", line], input=json.dumps({"hook_event_name": "SubagentStart", "agent_type": "kt-coder", "cwd": ROOT}), capture_output=True, text=True, encoding="utf-8", errors="replace")
        s.check("shell-form banner command runs: " + line[-30:], proc.returncode == 0, str(proc.returncode) + " " + proc.stderr[:120])


def dispatcher_cases(s):
    """bash-guards.py runs no-destructive then no-gate-weakening in one process and is wired on Bash and PowerShell."""
    hooks = json.load(open(os.path.join(HERE, "hooks.json"), encoding="utf-8"))["hooks"]["PreToolUse"]
    wired = {g["matcher"]: [h["args"][0].rsplit("/", 1)[-1] for h in g["hooks"]] for g in hooks}
    s.check("hooks.json wires bash-guards.py on Bash", "bash-guards.py" in wired.get("Bash", []), str(wired.get("Bash")))
    s.check("hooks.json wires bash-guards.py on PowerShell", wired.get("PowerShell") == ["bash-guards.py"], str(wired.get("PowerShell")))
    s.check("hooks.json wires the two new guards only through the dispatcher", all("no-destructive.py" not in v and "no-gate-weakening.py" not in v for v in wired.values()), str(wired))

    def run(payload):
        return run_hook("bash-guards.py", payload)

    proc = run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}})
    s.check("bash-guards refuses a forced push with the no-destructive message", proc.returncode == 2 and "no-destructive" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:100])
    proc = run({"hook_event_name": "PreToolUse", "tool_name": "PowerShell", "tool_input": {"command": "Remove-Item -Recurse C:\\x"}})
    s.check("bash-guards forwards an ask decision from PowerShell", proc.returncode == 0 and '"ask"' in proc.stdout, str(proc.returncode) + " " + proc.stdout[:100])
    repo = tempfile.mkdtemp(prefix="kt-guards-")
    os.makedirs(os.path.join(repo, "tests"))
    with open(os.path.join(repo, "tests", "a.test.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write('test("a", () => {});\n')
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    with open(os.path.join(repo, "tests", "a.test.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write('test.skip("a", () => {});\n')
    git(repo, "add", "-A")
    proc = run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": repo, "tool_input": {"command": 'git commit -m "x"'}})
    s.check("bash-guards reaches no-gate-weakening when no-destructive is silent", proc.returncode == 2 and "Gate-edit:" in proc.stderr, str(proc.returncode) + " " + proc.stderr[:100])
    proc = run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": repo, "tool_input": {"command": "ls"}})
    s.check("bash-guards is silent on a plain command", proc.returncode == 0 and proc.stdout.strip() == "" and proc.stderr.strip() == "", str(proc.returncode) + " " + (proc.stdout + proc.stderr)[:80])
    proc = run_hook("bash-guards.py", "not json")
    s.check("bash-guards lets a broken payload through", proc.returncode == 0, str(proc.returncode))


def report_drift_cases(s):
    for rel in REPORT_FILES:
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        missing = [sec for sec in REPORT_SECTIONS if sec not in text]
        s.check("REPORT sections in " + rel, not missing, "missing " + ", ".join(missing))


def trailer_cases(s):
    """The agent must never sign its own work: no co-author trailer, no tool advertising.

    The STRICT reading is deliberate: every `Co-Authored-By` is refused, human
    ones included, so there is no shape left to hide behind. The advertising line is refused in
    the same breath because the harness adds it to pull request bodies by default."""
    h = "no-emdash.py"
    claude_trailer = 'git commit -m "Fix X" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"'
    human_trailer = 'git commit -m "Fix X" -m "Co-Authored-By: Someone Real <someone@example.com>"'
    s.expect_exit(h, "block Co-Authored-By naming the agent", {"tool_input": {"command": claude_trailer}}, 2)
    s.expect_exit(h, "block Co-Authored-By even for a human (owner chose the strict reading)", {"tool_input": {"command": human_trailer}}, 2)
    s.expect_exit(h, "block the advertising line in a pull request body", {"tool_input": {"command": 'gh pr create --title T --body "Fixes it.\n\nGenerated with Claude Code"'}}, 2)
    s.expect_exit(h, "block the advertising line in a commit message too", {"tool_input": {"command": 'git commit -m "Generated with Claude Code"'}}, 2)
    s.expect_exit(h, "allow a commit message that carries neither", {"tool_input": {"command": 'git commit -m "Fix the parser"'}}, 0)
    s.expect_exit(h, "allow the word commit without a trailer", {"tool_input": {"command": 'git commit -m "add the commit hook guard"'}}, 0)
    s.expect_exit(h, "ignore a trailer outside a commit or pull request command", {"tool_input": {"command": 'echo "Co-Authored-By: whoever"'}}, 0)
    s.expect_exit(h, "allow Signed-off-by, which is a different trailer", {"tool_input": {"command": 'git commit -s -m "Fix X"'}}, 0)
    s.expect_exit(h, "KT_ALLOW_EMDASH does NOT switch the signature guard off", {"tool_input": {"command": claude_trailer}}, 2, {"KT_ALLOW_EMDASH": "1"})


def main():
    s = Suite()
    for fn in (emdash_cases, emdash_relocation_cases, trailer_cases, secret_cases, offplan_cases, bash_cases, audit_cases, wiring_cases, frontmatter_cases, packaging_cases, rules_cases, subagent_long_section_cases, hook_budget_cases, docs_block_review_cases, stop_gate_cases, skeleton_stamp_cases, skeleton_compare_cases, cost_cases, gate_wording_cases, repo_hygiene_cases, report_drift_cases, backup_cases, utf8_cases, gate_weakening_cases, destructive_cases, dispatcher_cases, exec_form_cases, local_rules_backup_case):
        fn(s)
    for line in s.failures:
        print("FAIL " + line)
    print(str(s.total - len(s.failures)) + "/" + str(s.total) + " cases passed")
    return 1 if s.failures else 0


if __name__ == "__main__":
    sys.exit(main())
