# Decisions

Architectural decisions binding this project, newest first.

---

## {DEC}-007 — Sync runs in a background worker, not on the UI thread

- **Decided:** 2026-01-20
- **Status:** accepted
- **Domains:** mobile, network
- **Source:** plans/2026-01-15-sync-plan.md — Stage 2
- **Reason:** A sync on the UI thread stalls input whenever the network is
  slow, and the platform kills an app that stalls for too long. A worker
  keeps input responsive at the cost of a queue between the two.
- **Global:** [[decisions/mobile#{GDEC}-MOB-003]]

---

## {DEC}-006 — Ship one build per architecture

- **Decided:** 2026-01-02
- **Status:** superseded by {DEC}-007
- **Domains:** mobile
- **Source:** plans/2026-01-01-packaging-plan.md — Stage 2
- **Reason:** Reproducible builds failed on the universal package.

---

## {DEC}-005 — Malformed on purpose

- **Decided:** 2026-01-01
- **Status:** accepted
