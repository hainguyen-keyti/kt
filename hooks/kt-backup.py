#!/usr/bin/env python3
"""Mirror the machine-local agent layer of the current repo into ~/kt-backups/<repo-name>/.

Run by /kt:save after the commit. Stands in for `rsync -a --delete`, which Git Bash on Windows
does not ship. Mirrors docs/agent/ -> docs-agent/, CLAUDE.md -> CLAUDE.md and .claude/ ->
dot-claude/ (without worktrees/), copying what changed and removing what the source no longer
has, so a second run converges to the same tree. Refuses to run from a lane worktree: a lane's
HANDOFF and dangling symlinks must not overwrite the main checkout's copy. Exit 0 on success
and on the lane refusal; exit 1 with the reason when git or the filesystem refuses.
"""
import os
import shutil
import subprocess
import sys

TARGETS = (("docs/agent", "docs-agent", ("worktrees",)), ("CLAUDE.md", "CLAUDE.md", ()), (".claude", "dot-claude", ("worktrees",)))


def git(*args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.exit("kt-backup: git " + " ".join(args) + " failed: " + proc.stderr.strip())
    return proc.stdout.strip()


def mirror(src, dst, skip):
    copied = 0
    for root, dirs, files in os.walk(src):
        rel_root = os.path.relpath(root, src)
        dirs[:] = [d for d in dirs if os.path.normpath(os.path.join(rel_root, d)) not in skip]
        os.makedirs(os.path.join(dst, rel_root), exist_ok=True)
        for name in files:
            source = os.path.join(root, name)
            if os.path.islink(source) and not os.path.exists(source):
                print("kt-backup: skipped dangling symlink " + os.path.relpath(source))
                continue
            shutil.copy2(source, os.path.join(dst, rel_root, name))
            copied += 1
    for root, dirs, files in os.walk(dst, topdown=False):
        rel_root = os.path.relpath(root, dst)
        for name in files:
            if not os.path.exists(os.path.join(src, rel_root, name)):
                os.remove(os.path.join(root, name))
        for d in dirs:
            rel = os.path.normpath(os.path.join(rel_root, d))
            if rel in skip or not os.path.isdir(os.path.join(src, rel)):
                shutil.rmtree(os.path.join(root, d))
    return copied


def main():
    top = git("rev-parse", "--show-toplevel")
    git_dir = os.path.realpath(os.path.join(top, git("rev-parse", "--git-dir")))
    common = os.path.realpath(os.path.join(top, git("rev-parse", "--git-common-dir")))
    if git_dir != common:
        print("kt-backup: lane worktree, no backup (the main checkout owns ~/kt-backups)")
        return 0
    dest = os.path.join(os.path.expanduser("~"), "kt-backups", os.path.basename(top))
    os.makedirs(dest, exist_ok=True)
    for rel, name, skip in TARGETS:
        src = os.path.join(top, rel)
        target = os.path.join(dest, name)
        if os.path.isdir(src):
            print("kt-backup: " + rel + " -> " + target + " (" + str(mirror(src, target, set(skip))) + " files)")
        elif os.path.isfile(src):
            shutil.copy2(src, target)
            print("kt-backup: " + rel + " -> " + target)
        else:
            if os.path.isfile(target):
                os.remove(target)
            elif os.path.isdir(target):
                shutil.rmtree(target)
            print("kt-backup: " + rel + " absent, nothing to back up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
