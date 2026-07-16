# Decision & Open-Points Register — lp2graph (library)

Running log of **decisions**, **open questions** and **notes** for this project.
Append-only; newest entries at the bottom. Managed by the `transcript` skill via
`register.py`. The central aggregate of all open points across projects lives at
[`~/DECISIONS.md`](/home/joern/DECISIONS.md).

**Lifecycle:** `open` → `decided` → (if architectural) graduate into a numbered
**ADR** in `docs/adr/`. ADRs stay immutable; this register is where things churn.

Entry fields: *Type* (decision/open-question/note), *Status*, *Date*, *Source*
(meeting/transcript), *Owner*, *Summary*, optional *Rationale* and *Next*.

---

### D-2026-0619-01 · Periodic model fails to solve despite coherence handling
- **Type:** open-question
- **Status:** open
- **Date:** 2026-06-19
- **Source:** meeting 2026-06-18 (~/meetings/2026-06-18-paper1-status-review.md)
- **Owner:** JM
- **Summary:** A periodic formulation does not solve although Paper-1's coherence handling should cover it ('I don't know why this isn't right; look into this'). Investigate in the lp2graph grounding/solver path.

