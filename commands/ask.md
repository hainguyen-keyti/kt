---
description: Gather every pending user decision and ask them in one turn, with a Recommended option
---

Gather and ask the user, in ONE turn, everything that is waiting on a decision:

1. Sources: the "Open decisions" section of `docs/agent/DECISIONS.md` + every ambiguity that came
   up in this session that you are having to guess at (guessing is forbidden, so each one must
   become a question here).
2. Present them as a numbered list, important or blocking questions first. For each question:
   - Context in 1-2 sentences: why it must be decided, what it is blocking.
   - 2-4 options, the FIRST option marked (Recommended) with a concrete reason (cost, risk,
     durability, fit with the project stage).
   - Every option must carry concrete evidence (file:line, a measured number, a spec quote), not
     just adjectives. The (Recommended) option must also state: the real drawbacks of THAT option
     itself, what gets left behind and the consequence, and one line "This recommendation is
     wrong if ..." naming the condition that would break it.
   - The quality bar for options is taken whole from the kt rules block: only options that are
     correct by the standard and durable; a temporary patch must be labeled and come with the
     proper fix alongside it.
3. Use AskUserQuestion when available, at most 4 questions per turn; if more remain, ask the next
   batch after the user answers the first one.
4. A question in the money or security area, or labeled [BLOCKS MERGE]: before the user settles
   it, proactively offer to run `/kt:second` for that question (the independent ritual lives
   entirely in that command); if the second opinion matches, say it matches; if it diverges,
   present a table comparing exactly the points where it diverges.
5. Right after the user answers: record the answer in DECISIONS.md ("Decided" or "Rejected", with
   date + reason), then summarize what was just settled and which work it unblocks.

Do not ask a string of petty yes/no questions. Do not re-ask anything already in the "Decided" or
"Rejected" section.
