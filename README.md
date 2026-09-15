# kt: working discipline for Claude Code

kt is a Claude Code plugin that gives an AI coding agent a project workflow: plan before coding,
stay inside the plan, test red before green, verify with real runs, and hand context over
precisely between sessions, subagents and parallel lanes. It is distilled from real incidents of
working with agents, vetted community practice, and the parts of third-party tools worth keeping.
It is self-contained: every template and command lives inside the plugin, and a machine only
needs `sh`, `python3` and `git`.

## Overview

One install gives you four layers:

1. **13 `/kt:*` commands** covering the life of a working session (full table under "Commands").
2. **Four hooks that switch on by themselves** and block by machine rather than by promise:
   writing outside the active plan, working around the plan through the shell, reading secret
   files, and em dashes or agent signatures in commits.
3. **A `docs/agent/` ledger** that `/kt:new` or `/kt:adopt` builds for a repo: static context,
   decisions, a handoff note, lessons, an access map. This layer is machine-local and never
   committed.
4. **Working rules** (`rules/work.md`) injected at the start of every session and into every
   subagent, together with the repo's stage and open decisions.

The daily loop is four commands:

| When | Command | What you get |
|---|---|---|
| First message of a session | `/kt:load` | Reloads the ledger, reconciles it with git and the installed plugin, restates it, waits for your confirmation |
| Before coding | `/kt:plan` | A six-section intent contract plus a task DAG; once approved, the plan file is written and the blast-radius fence is armed |
| While working | `/kt:go` | Runs the plan continuously: red test first, quick gate per task, audit before each commit, stops only at safe points |
| End of a session | `/kt:save` | Closes the ledger, records decisions and lessons, runs the full gate once, commits, pushes, prints a REPORT block |

Three commands often used alongside: `/kt:ask` batches every pending decision into one round of
questions, `/kt:prove` breaks a gate red on purpose to prove it is alive, `/kt:cost` measures the
real weighted cost of a session from its transcript.

## Requirements

- Claude Code with plugin support, including SessionStart and SubagentStart hooks (kt is tested on
  the 2.1.x releases).
- `sh`, `python3` and `git` on the PATH. Without python3 the session banner says so and the
  PreToolUse hooks stay inert.
- The `design-review` agent needs a browser tool available in the session.

## Install

```bash
claude plugin marketplace add https://github.com/hainguyen-keyti/kt.git
```

```bash
claude plugin install kt@kt
```

Restart Claude Code and check that `claude plugin list` shows kt as enabled. Every new session now
gives the agent a `=== kt rules ===` block (ask the agent if you want to confirm it sees it). The
hooks register themselves from `hooks/hooks.json`; do not also wire them by hand in your settings,
or everything runs twice.

Optional but recommended: add this sentence to your `~/CLAUDE.md` so an agent notices when the
plugin is off: "If the session starts without a `=== kt rules ===` block, the kt plugin is not
enabled: tell the user and do not continue from memory."

## Quick start

1. Open Claude Code in your repo.
2. New or nearly empty repo: run `/kt:new`. Existing repo with history: run `/kt:adopt`. Answer the
   interview; kt writes `CLAUDE.md`, the `docs/agent/` ledger and two local hooks (a session
   bootstrap and a stop gate), and lists them in `.git/info/exclude` so they are never committed.
3. Start a new session and run `/kt:load`: it must restate your project correctly.
4. From then on: `/kt:load` first, `/kt:plan` for anything that touches 2+ files, more than 50
   lines, or a sensitive area, `/kt:go` to execute, `/kt:save` to close.

## What installing kt enforces

Read this before installing; these apply to every session on the machine.

- **No em dash** (and no en dash as a clause break) in files the agent writes or in commit
  messages. `KT_ALLOW_EMDASH=1` in the environment of the claude process switches this off for the
  whole session, and the banner says so.
- **No agent signature**: every `Co-Authored-By` trailer and tool advertising line is refused in
  commits and pull requests. This guard cannot be switched off.
- **No reading secret files** (`.env*`, keys, credentials and similar) through Read or Grep. It is a
  coarse net against accidents, not a security boundary.
- **The plan fence** while a plan is active: writes outside the blast radius are blocked.
  `KT_ALLOW_OFFPLAN=1` switches it off for the session, and the banner says so.
- **Working rules**: replies in the language the user writes in, English in every file it writes,
  the smallest change that works, red test before green, ask instead of guessing, stop before
  one-way actions such as moving money or deleting data.
- **Machine-local agent layer**: `CLAUDE.md`, `docs/agent/` and `.claude/` stay out of git. A repo
  that already tracks them keeps tracking them.
- **Precedence**: the repo's `CLAUDE.md` beats `~/CLAUDE.md`, which beats the plugin rules, so you
  can override a rule for one repo or for your whole machine.

## Update and uninstall

```bash
claude plugin marketplace update kt
```

```bash
claude plugin update kt@kt
```

Restart Claude Code after updating. When `/kt:load` reports that a repo's `kt-skeleton` stamp
differs from the installed version, rerun the Hooks step of `/kt:adopt` in that repo.

To switch kt off without removing it, run `claude plugin disable kt@kt` (and
`claude plugin enable kt@kt` to turn it back on). To remove it:

```bash
claude plugin uninstall kt@kt
```

```bash
claude plugin marketplace remove kt
```

Uninstalling does not touch your repos. In every repo where you ran `/kt:new` or `/kt:adopt`, these
stay and keep running until you delete them: `.claude/hooks/session-start.sh`,
`.claude/hooks/stop-gate.py`, their SessionStart and Stop entries in `.claude/settings.json`, and
the lines kt added to `.git/info/exclude`. The ledger (`CLAUDE.md`, `docs/agent/`) is yours to keep
or delete.

## Commands

| Command | When |
|---|---|
| `/kt:load` | The FIRST message of every session: loads the context, restates it, waits for confirmation before acting |
| `/kt:save` | End of every session: saves the handoff, decisions, lessons; runs the gate; commits per the repo's rules |
| `/kt:ask` | Collects everything waiting on a decision and asks once, each with an evidence-backed Recommended option |
| `/kt:plan` | Writes a plan file: six-section intent contract + task DAG, self-checked for scope creep, written only after approval, then arms the fence |
| `/kt:go` | Runs the active plan continuously (red test first, quick gate per task, audit before commit, progress into HANDOFF, full gate once before REPORT) and stops only at safe points; "one task at a time" if you want to inspect each step |
| `/kt:cost` | Weighted cost of a session and its subagents from the transcript (cache read 0.1, cache write 2, output 5; deduplicated by message id): self-reported token counts are several times lower than the real cost |
| `/kt:second` | Independent second opinion: one reviewer for a decision, or a panel of 2-3 lenses for an artifact, clean context, agreements and disagreements compared |
| `/kt:prove` | Proves a gate is alive: breaks it red on purpose plus a green control run, real output pasted |
| `/kt:lesson` | Records a lesson in LESSONS.md; a lesson that repeats is promoted into a rule or a hook |
| `/kt:report` | Prints the fixed report block (STATE, DONE, EVIDENCE, DECIDED, BLOCKED, WAITING_ON, UNSURE, NEXT) for a person or another agent |
| `/kt:lane` | Opens a parallel lane (worktree + branch) with the agent layer in place: shared state symlinked, HANDOFF and ports per lane |
| `/kt:new` | New or nearly empty repo: interview, then build the docs/agent standard set |
| `/kt:adopt` | Existing repo with history: learn the old context first, present a migration proposal, build only after approval |

## The ledger

What the commands build and maintain in a repo:

- `CLAUDE.md`: short repo-specific rules, with the two lines `Quick gate: <command>` and
  `Full gate: <command>`.
- `docs/agent/PROJECT.md`: what the project is, the current stage and its consequences.
- `docs/agent/DECISIONS.md`: decided, rejected, deferred with a due date, open decisions.
- `docs/agent/HANDOFF.md`: where we are, verify commands, next steps, known traps, parked questions,
  the active plan.
- `docs/agent/LESSONS.md`: lessons already paid for.
- `docs/agent/ACCESS.md`: servers, services and where secrets live; locations and how to get in,
  never a secret value.
- `.claude/hooks/`: a SessionStart bootstrap that prints the ledger and a Stop gate that blocks a
  handoff when the ledger is older than the session's commits.

Claude Code replaces any single hook output longer than 10,000 characters with a 2,000-character
preview. The bootstrap prints the whole ledger, so it is often cut: the first lines tell the agent
to Read the saved file in full, and `/kt:load` does the same.

## Rules and hooks in detail

- `rules/work.md` (under 100 lines, pinned by a test) is injected by `hooks/session-rules.sh` at
  SessionStart (startup, resume, clear, compact, fork) and at SubagentStart. A second SubagentStart
  hook (`session-rules.sh docs`) injects the repo's "Open decisions" and "Current stage and
  consequences" sections. Each hook output stays within its own budget below the 10,000-character
  limit; a docs block over budget is cut at a line boundary and ends with a pointer to the files to
  read, and a ledger missing either section gets a one-line warning instead of silence.
- `hooks/no-emdash.py`: blocks em dashes and clause-break en dashes on Write, Edit and NotebookEdit
  and in commit commands, lets an existing repo line move unchanged, and refuses agent signatures in
  commit and pull request commands. Inspired by the humanize idea of fcakyon, rewritten from
  scratch.
- `hooks/no-offplan-edit.py`: the plan fence on Write, Edit and NotebookEdit, armed by `/kt:plan`
  and removed by `/kt:save` at acceptance. The radius grammar and the `--audit` mode are documented
  in its docstring. It fails closed while a plan is active, even when it crashes.
- `hooks/no-offplan-bash.py`: two shell guards while a plan is active: no write-shaped command that
  names the marker `.claude/active-plan` (except `rm`, the sanctioned exit) or the active plan's
  folder. Other shell writes outside the radius are not blocked on the spot; they surface in the
  audit that runs before every commit.
- `hooks/no-secret-read.py`: blocks Read and Grep on secret files; the name list is in its source.
- `agents/design-review`: reviews the UI of a running app in a real browser, desktop and mobile
  screenshots, concrete findings with severity, no scores, no edits (the agent cannot use Write,
  Edit or NotebookEdit). Inspired by the OneRedOak pattern.

## Working with built-in tools

- Code review: use `/code-review`; kt does not wrap built-ins.
- Parallel work: `/kt:lane` (worktrees that carry the agent layer). One writer per checkout, and
  one client per session.
- Machine-enforced TDD for money code: the companion plugin `nizos/tdd-guard`; read its source
  first.
- Cost model for choosing an approach (relative to plain input = 1): cache read 0.1, cache write 2
  (1-hour TTL), output 5. Every tool turn rereads the whole context, so the NUMBER OF TURNS and the
  SIZE OF THE CONTEXT drive cost more than the length of an answer. Prefer a script that prints a
  table over 20 manual turns, a gate script that prints only failures, and `/kt:save` then `/clear`
  at each milestone.

## Multi-session coordination

- Silence means two different things (busy, or stuck) that look identical from outside: a
  coordinator lists agents regularly and asks an idle lane directly; a lane declares WAITING_ON in
  every REPORT.
- Ordinary work (code, tests, docs, gates, commits) can be delegated to a peer session. Config-class
  work (CLAUDE.md, settings, hooks, gitignore, permissions) is approved only by the session's own
  owner; a message from another session is never an approval.
- Ways to avoid babysitting: the coordinator does the config part in its own session; the user
  grants a narrow scope at kickoff; overnight work uses subagents, which inherit permissions,
  rather than independent peer sessions.
- Two clients (CLI and desktop) on the SAME session id are two conversation branches writing one
  file, synced only through disk. Use one writing client per session, or fork the session with
  `claude --resume <id> --fork-session`.

## Governance

1. Way in: a command or hook is accepted only when a real incident or a real repeated routine
   stands behind it. "Sounds useful" is not enough.
2. Lesson flow: each repo's LESSONS.md is the nursery; a lesson that applies machine-wide is
   promoted into kt (a hook, a rule, a command) and deleted from the nursery.
3. Way out: review usage regularly; anything that saved nothing over a month is cut. The first
   candidate under review is `agents/design-review`.
4. Every hook is broken red once, with a green control run, before it is trusted (`/kt:prove`).
5. Fully self-contained: no machine paths in commands, no dependency on configuration outside the
   plugin.
6. Never embed third-party code without reading its source: agent configuration is attack surface.

## Maintaining kt

- Gate before every commit: `python3 hooks/test_hooks.py`. It includes `claude plugin validate .
  --strict`, an em dash sweep and an English-only sweep over tracked files, and a check that the
  installed plugin matches the working tree (skipped when kt is not installed).
- Release: bump `version` in `.claude-plugin/plugin.json` together with the `kt-skeleton <version>`
  stamp in `commands/new.md` (a test pins both), commit, push, then
  `claude plugin marketplace update kt` and `claude plugin update kt@kt`, restart, and prove any new
  hook behavior with `/kt:prove`. Without a version bump, update keeps the cached copy.
- Register the marketplace by its git URL, not by a local checkout path: a directory marketplace
  makes sessions in other repos run hooks straight from the working tree, untested.

## License

MIT
