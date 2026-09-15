---
description: Run the active plan under the Execution rules, continuously, stopping only at a safe stop
---

Run the active plan under exactly the Execution rules (the rules live here and in kt rules §2-4,
never copied into the plan):

1. Read `.claude/active-plan`; if it is missing, STOP and report: no active plan, suggest
   `/kt:plan` (never run a plan that is not armed, even when the user names it explicitly: one
   plan at a time, audited against its base). Read the plan file the marker points to and the
   "Active plan" section in `docs/agent/HANDOFF.md`, and identify the next unfinished task in
   DAG order; if it is ambiguous which task is next, ask the user to choose, do not guess.
2. Restate the task's requirement in exactly ONE sentence (stick to the plan's wording, no
   interpretation), list the files it will touch (they must be inside the blast radius), and
   ACTUALLY read those files before editing.
3. Do EXACTLY that task: write files with Write/Edit/NotebookEdit (so the fence sees them), never
   through the shell; see the test RED first, then fix (kt rules §4); handle parked questions per
   kt rules §3 (blocking: ask right away; not blocking: add a line to the HANDOFF
   "Parked questions" section and carry on); a security hole in OTHER code is a BLOCKING parked
   question, the security of code YOU write is always in scope. The plan is a contract: do not
   edit the plan during execution; if the approach changes, record it in DECISIONS.md. If the
   plan is WRONG at one point, classify the deviation (kt rules §2): a NARROWING deviation
   (dropping a test case that cannot go red for the right reason, not rebuilding something that
   already exists, not widening the radius, not changing acceptance) gets a one-line report and
   work continues; a WIDENING deviation (a file outside the radius, a new surface, changed
   acceptance, touching engine/contract/event log/money/security) means STOP and wait for
   approval. If the fence blocks you, follow the fence's message; never remove the marker
   yourself.
4. Done: run the repo's QUICK GATE (the `Quick gate:` line in the repo's CLAUDE.md, only the part
   relevant to the changed files) and the task's acceptance, and paste the real output (if there
   is no check command, say so plainly); do not run the full gate after each task. Run the audit
   inside the repo (command below; the audit climbs up to find the marker) and paste the result:
   files written through the shell outside the radius surface HERE (the shell has no fence at
   write time), so fix them or record a parked question BEFORE committing; then commit the task
   (a one-sentence English message; a task that only touches machine-local files such as
   docs/agent has nothing to commit, so say that plainly instead of making an empty commit);
   write a progress line into the "Active plan" section of HANDOFF.md in the form
   `- [x] T<n> <name> | <command>: <result>`, and do NOT edit the plan file (the repo's stop gate
   also runs the audit itself when it sees a REPORT block, but the reader needs to see the
   numbers).

   ```
   KT=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['kt@kt'][0]['installPath'])")
   python3 "$KT/hooks/no-offplan-edit.py" --audit
   ```
5. Report briefly: the task just finished, evidence, audit, any new parked questions recorded,
   the next task. Then CONTINUE with the next task in the same run. Stop only on: a blocking
   parked question or a WIDENING deviation; touching an invariant, money, security, or an
   "Open decisions" entry of DECISIONS.md; a fence block with no path inside the radius; red
   acceptance that cannot be fixed within the task; the end of the plan. If the user says "one
   task at a time", stop after each task and wait for `/kt:go` again. At the END OF THE PLAN, and
   before any REPORT: run the repo's FULL GATE (the `Full gate:` line) exactly ONCE on a clean
   tree; if red, fix it within the plan before handing over; if green, record it in EVIDENCE in
   the `/kt:report` format (verbatim count line, sha, clean tree) so the receiver does not have
   to rerun it at the same sha.
