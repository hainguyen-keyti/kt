#!/usr/bin/env python3
"""PreToolUse hook: block Read/Grep on secret files.

A coarse tripwire against ACCIDENTAL exposure, NOT a security boundary: Bash reads
are not covered; the real boundary is gitignore, least-privilege keys, and indirect
use. Agents may USE secrets ($VAR, wrapper scripts, paths) but never read the
values. Matching is case-insensitive on the basename; a directory component named
secrets/.ssh/.aws/.gnupg/.kube/.docker blocks too, except code files under a
`secrets` module (.ts .js .py .go .rs .java .md) and the non-secret ssh/aws files
(config, known_hosts). Content-mode Grep over a whole directory (no glob or type)
for a secret-looking pattern (secret, token, passw, api_key, *_key) is blocked as
well, because it prints the values into the transcript: narrow with a glob or use
files_with_matches. Exempt: .example/.sample/.template files, public keys (*.pub),
and code files named secrets.* (a module, not a vault). Exit 2 blocks and explains;
locations live in docs/agent/ACCESS.md.
"""
import fnmatch
import json
import os
import re
import sys

SECRET_BASENAME_GLOBS = [
    "*.pem", "*.key", "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*",
    ".env*", "*.env", ".netrc", ".npmrc", ".pgpass", ".htpasswd", ".pypirc",
    "credentials", "credentials.json", "credentials.yml", "credentials.yaml",
    "*service-account*.json", "serviceaccount*.json", "*firebase-adminsdk*.json", ".git-credentials",
    "*.tfstate", "*.tfstate.backup", "*.tfvars", "secrets.*", "secring.*",
    "*.keystore", "*.p12", "*.pfx", "*.jks", "*.p8", "*.ppk",
]
SECRET_DIR_NAMES = {"secrets", ".ssh", ".aws", ".gnupg", ".kube", ".docker"}
SAFE_SUFFIXES = (".example", ".sample", ".template")
CODE_SUFFIXES = (".ts", ".js", ".py", ".go", ".rs", ".java", ".md")
SAFE_IN_DIR = {".ssh": {"config", "known_hosts"}, ".aws": {"config"}}
SECRET_PATTERN_RE = re.compile(r"secret|token|passw|(?:api|private|access|auth)[_-]?key|_key\b", re.IGNORECASE)


def is_secret_path(path: str) -> bool:
    if not path:
        return False
    normalized = path.replace("\\", "/").lower()
    parts = normalized.rstrip("/").split("/")
    base = parts[-1]
    if base.endswith(SAFE_SUFFIXES) or base.endswith(".pub"):
        return False
    if base.startswith("secrets.") and base.endswith(CODE_SUFFIXES):
        return False
    for glob in SECRET_BASENAME_GLOBS:
        if fnmatch.fnmatch(base, glob):
            return True
    hit = SECRET_DIR_NAMES.intersection(parts)
    if not hit:
        return False
    if base in SECRET_DIR_NAMES:
        return True
    if hit == {"secrets"} and base.endswith(CODE_SUFFIXES):
        return False
    if any(base in SAFE_IN_DIR.get(d, ()) for d in hit):
        return False
    return True


def is_secret_grep(tool_input) -> bool:
    if tool_input.get("output_mode") != "content" or tool_input.get("glob") or tool_input.get("type"):
        return False
    path = tool_input.get("path")
    if isinstance(path, str) and os.path.isfile(path):
        return False
    return bool(SECRET_PATTERN_RE.search(str(tool_input.get("pattern") or "")))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = payload.get("tool_input") or {}
    for key in ("file_path", "path", "glob"):
        value = tool_input.get(key)
        if isinstance(value, str) and is_secret_path(value):
            sys.stderr.write(
                "BLOCKED: reading secret files is forbidden. Use the value indirectly "
                "($VAR, repo wrapper script, file path in a command). Locations are mapped "
                "in docs/agent/ACCESS.md; if you truly need the value, ask the user.\n"
            )
            return 2
    if is_secret_grep(tool_input):
        sys.stderr.write(
            "BLOCKED: content-mode Grep for a secret-looking pattern over a whole directory "
            "would print secret values into the transcript. Use output_mode files_with_matches, "
            "or narrow the files with a glob or type.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
