#!/usr/bin/env python3
"""PreToolUse dispatcher (matcher Bash and PowerShell): one Python process for the two shell guards.

Every Bash call already pays for two interpreter starts (no-offplan-bash, no-emdash); the two guards
added in 1.6.0 share one. The payload is read once and handed to no-destructive first, then
no-gate-weakening. A refusal (exit 2) or an `ask` decision (JSON on stdout) from the first ends the
run; a silent pass goes on to the second. Each guard keeps its own failure policy: a crash inside
no-destructive refuses the call, a crash inside no-gate-weakening lets it through.
"""
import importlib.util
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_guard(module, raw, fail_closed):
    """Run one guard's main() on the shared payload; return (exit code, captured stdout)."""
    stdin, stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(raw), io.StringIO()
    try:
        code = module.main()
    except Exception as exc:
        sys.stderr.write(module.__name__ + ": internal error: " + type(exc).__name__ + "\n")
        code = 2 if fail_closed else 0
    finally:
        out, sys.stdin, sys.stdout = sys.stdout.getvalue(), stdin, stdout
    return code, out


def main():
    sys.dont_write_bytecode = True
    raw = sys.stdin.read()
    for name, fail_closed in (("no-destructive", True), ("no-gate-weakening", False)):
        code, out = run_guard(load(name), raw, fail_closed)
        if code != 0:
            return code
        if out.strip():
            sys.stdout.write(out)
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
