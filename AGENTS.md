# Agent rules — app_black

## AI working plans → `.ai-plans/`

Multi-step plans, investigations and design notes an agent produces go in
`.ai-plans/` (one Markdown file per topic, e.g. `PLAN_F04_privilege_escalation.md`).

- The directory is **git-ignored** — these are local scratch, not repo history.
  Do not commit them and do not add them to a PR.
- Write a plan here **before** starting the implementation it describes, and
  keep it updated as the work lands.
- This is separate from **durable, shared docs** that belong in git — a roadmap,
  a decision record, an ADR. Those stay tracked at the repo root
  (e.g. `SECURITY_ROADMAP_1.6.md`). If a `.ai-plans/` note graduates into a
  decision the team should keep, move it out of `.ai-plans/` deliberately.
