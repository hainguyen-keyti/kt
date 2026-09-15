---
description: "Independent second-opinion: one decision (one reviewer) or one artifact (panel of 2-3 lenses); clean context, reads only the artifact, compares agreements and disagreements"
---

Run an INDEPENDENT second-opinion on: $ARGUMENTS (if empty: ask the user which question to check,
suggesting one from the "4. Open decisions" section of `docs/agent/DECISIONS.md` or the latest
recommendation in the session).

Two modes: DECISION (default, one reviewer, steps 1-3) and PANEL (the subject is an artifact: a
plan, a design, a large diff; 2-3 reviewers with different lenses, last section). The vital
principle for both: a second opinion is worth something only when it is NOT contaminated by the
reasoning of the first opinion. Therefore:

## Step 1: Package a clean brief

- Write a NEUTRAL brief containing: the question to decide, the set of options (only the NAME and
  an objective description of each option, WITHOUT the current recommendation and without this
  session's arguments), and the list of relevant artifact files in the repo (code, spec,
  docs/agent/*).
- Self-check the brief: if reading it lets you guess the "desired answer", the brief is
  contaminated; rewrite it.

## Step 2: Run a clean-context reviewer

- Spawn one subagent (fresh context) with the brief above. Instruct it: read only the listed files
  and the files they point to; rank the options on its own; give its own recommendation with
  concrete evidence (file:line, numbers, spec quotes); state the weaknesses of the option it picks
  and one line "this recommendation is wrong if ...".
- Work in the auth or signature-verification area: do NOT hand it to a subagent (safeguards tend to
  refuse it); play the reviewer yourself in this session, but start from the artifact, set the
  earlier reasoning aside, and tell the user plainly that the independence is lower.

## Step 3: Compare and present

- SAME recommendation: report the agreement, with one sentence on where the two sides cite
  different evidence (if they do).
- DIFFERENT recommendations: present a comparison table EXACTLY AT THE DISAGREEMENT: which
  evidence each side relies on, which evidence a machine can check (if it can be run, offer to run
  it right away), and a concrete deciding question for the user.
- Do NOT settle it yourself. The user settles; the answer goes into DECISIONS.md following the
  `/kt:ask` ritual exactly.

## Panel mode: the subject is an artifact

- Spawn 2-3 clean-context subagents IN PARALLEL, one lens each, none seeing the reasoning of the
  session or of each other: (a) EXECUTOR simulates executing the artifact itself, pointing out
  where it has to guess, gets stuck, or two texts contradict; (b) COVERAGE QA lists paths the
  artifact's mechanism does not catch, rated by the probability that a real agent wanders into them
  by accident, with the cheapest way to close each; (c) CONCISE AND COMPLETE measures duplication,
  excess length, and gaps, in line counts. Each returns findings on a SHARED SCALE and TEMPLATE
  embedded in the brief (otherwise each uses its own scale and nothing can be merged): P1 = the
  agent does it WRONG or gets STUCK, or a mechanism promises what it does not hold; P2 = has to
  guess, costs extra rounds, a hole of medium probability; P3 = duplication, length, cosmetics.
  Output template: `## Findings` (each line `[P1|P2|P3] <title> | evidence: file:line or output |
  consequence | cheapest fix, or a neutral fork (A)/(B) that does not reveal which side the
  session leans toward`), `## Strengths` (at most 5 lines with evidence), `## Summary` (does it
  meet its self-declared purpose, strongest point, weakest point, P1/P2/P3 counts).
- Frame the brief as "audit the coverage of a guardrail" or "simulate execution", NOT as "play a
  lazy agent looking for a way around it": that frame triggers cyber-safeguard false positives and
  the reviewer dies midway (seen in practice).
- Synthesis: an AGREEMENT table (what must be fixed), a DISAGREEMENT table (which evidence each
  side relies on, the deciding question for the user), plus the session's own self-review
  presented AT THE SAME TIME for comparison, not earlier where it would bias the reading. Do not
  settle it yourself; the user decides following the `/kt:ask` ritual.
