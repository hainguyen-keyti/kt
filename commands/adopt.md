---
description: "Install the docs/agent standard set in an existing repo: learn old context first, propose, build once approved"
---

Install the agent standard set in the CURRENT repo, which already has its own history and config.
The standard file skeleton (CLAUDE.md, docs/agent/*, hooks, settings) is EMBEDDED in the sibling
command `new.md` of this SAME kt plugin: get EXACTLY the installed version (the cache also keeps
old versions; do NOT use `find`, it returns every stale copy) with the command below, then read
`<installPath>/commands/new.md`; if no path comes out, ask the user for the path of the kt repo.
No other template is needed. Supreme principle: LEARN FIRST, BUILD SECOND, BREAK NOTHING.

```
python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['kt@kt'][0]['installPath'])"
```

Delete nothing and overwrite nothing until the user has approved the proposal in step 2.

## Step 1: LEARN (read only, touch no file yet)

- Read: the existing `CLAUDE.md` and every file it points to; `AGENTS.md`; `.claude/`
  (settings.json, rules/, commands/, hooks/); `docs/` (handoff, plan, spec, convention,
  postmortem); README; `git log --oneline -30` and the notable commit messages; stray state
  files (PROGRESS, TODO, NOTES, `.superpowers/`...).
- Pan that pile for these kinds of ore:
  1. LIVE RULES: things without which the agent will get it wrong.
  2. SETTLED DECISIONS with their reasons: found in docs, handoffs, commit messages.
  3. LESSONS ALREADY PAID FOR: sentences like "hit this X times", postmortems, fix-it-again commits.
  4. CURRENT STATE: where things stand, unfinished work, technical debt.
  5. SCATTERED ACCESS INFO: ssh commands in old docs, staging and dashboard URLs, env var names,
     where keys are kept. Gather it into ACCESS.md but NEVER copy a secret value; if a secret
     value sits in plain text in any file (old files included), report it to the user as a
     finding that must be dealt with.
- Project STAGE (pre-launch or live, real users or not yet, which environments exist): infer it
  from evidence but do NOT settle it yourself. Interview the user to confirm the stage and its
  CONSEQUENCES.

## Step 2: PRESENT THE MIGRATION PROPOSAL (still touch no file)

Present the user a table: which content goes where (PROJECT.md / which section of DECISIONS.md /
LESSONS.md / HANDOFF.md / stays in CLAUDE.md / frozen as history); what duplicates get merged;
what conflicts with kt's injected rules (the `=== kt rules ===` block) or the machine rules and
needs the user to rule on it; which files must never be touched.
Include a recommendation for every point that needs a choice. Go to step 3 only after the user
approves.

## Step 3: BUILD

- Create `docs/agent/`: `PROJECT.md` (stage + consequences ALREADY confirmed by the user),
  `DECISIONS.md` (4 sections: decided / rejected / deferred with a due date / open decisions with
  a [BLOCKS MERGE] or [NON-BLOCKING] label and a risk area label), `LESSONS.md`, `HANDOFF.md`,
  `ACCESS.md` (access map from ore number 5, only locations and how to get in, no secret values).
  The content is the ore panned in step 1, NOT an empty template. Each file under ~80 lines,
  absolute dates.
- Hooks: create `.claude/hooks/session-start.sh`, `.claude/hooks/stop-gate.py` and the hooks
  section of `.claude/settings.json` exactly verbatim from the skeleton in `new.md` (heed the
  technical notes that come with the skeleton, including the `kt-skeleton <version>` line: keep
  the number of the installed version), `chmod +x` the sh script; if settings.json already
  exists, MERGE, do not overwrite existing keys; if the repo has a Stop prompt-hook from the old
  standard set, replace it with a command-hook. UPGRADING the skeleton of an adopted repo
  (/kt:load calls for it when the `kt-skeleton` stamp differs from the installed version or is
  missing): rerun only this step, copy the two scripts and the hooks section again, do not touch
  docs/agent.
- Existing `CLAUDE.md`: keep the good content; a GENERAL RULES BLOCK copied from kt (smallest
  scope, follow the plan, no guessing, tests are inviolable, run it for real...) must be REMOVED
  and replaced with one sentence pointing to the `=== kt rules ===` block, because a repo's
  CLAUDE.md beats the plugin rules, so the old copy would silently override the new version;
  keep only the repo's OWN rules. Add a section pointing to `docs/agent/` + the session start and
  end ritual (`/kt:load`, `/kt:save`); frequently changing state found in it moves to
  `docs/agent/`. The "Standard commands" section must have the two lines `Quick gate: <command>`
  (only the part related to the changed files) and `Full gate: <command>` (kt's go, save and lane
  point to exactly these two names; if the repo has no relevant test tooling, the two commands
  are the same), plus the per-machine lane limit if the repo runs parallel lanes; whatever is
  still missing, ask the user in step 2. Keep the file under ~100 lines.
- Old handoff/state files: keep them in place, note in HANDOFF.md that they are frozen history
  and that the only current pointer is `docs/agent/HANDOFF.md`.

## Step 4: CHECK, then report done

- Actually run the hook script for both the green case and the control case:
  `CLAUDE_PROJECT_DIR=$(pwd) sh .claude/hooks/session-start.sh` must print the bootstrap;
  run in a directory without docs/agent it must stay silent and exit 0. `settings.json` must
  parse.
- Scan every newly created file for em dashes (a kt rule forbids them outright).
- THE AGENT LAYER IS MACHINE-LOCAL, NEVER COMMITTED: add `CLAUDE.md`,
  `AGENTS.md`, `.claude/`, `docs/agent/` to `.git/info/exclude`; verify with
  `git check-ignore -v` on each path + `git status --porcelain` showing no standard-set file.
  No `git add -f`, never propose tracking them.
- Grandfather EXCEPTION: standard-set files the repo ALREADY TRACKED before
  (`git ls-files --error-unmatch CLAUDE.md` exits 0, the most common case in older repos):
  `check-ignore` exiting 1 and porcelain showing ` M` is CORRECT, not a red check. Such a file
  does not go into exclude, and no `git rm --cached` (it deletes the whole team's CLAUDE.md on
  the next push); if you change it, commit it like a normal file, same rule as save.md.
- The standard set is NOT committed. Only OLD repo files changed under the approved migration
  proposal (if any) get committed, as a separate commit with a one-sentence English message.
  Push per the end-of-session rule, EXCEPT in a repo that explicitly forbids auto-push.
- Final report: a "what went where" table, then the standard REPORT block of `/kt:report`
  (8 sections: STATE, DONE, EVIDENCE, DECIDED, BLOCKED, WAITING_ON, UNSURE, NEXT; an empty
  section reads `none`; the full format and rules live in that command). Invite the user to run
  `/kt:load` for acceptance: it must read the new set and retell the project correctly. If
  another agent assigned this work, send the REPORT block back to them with SendMessage.
