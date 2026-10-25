# Decisions

---

## {DEC}-004 — Requests retry with backoff inside the worker

- **Decided:** 2026-01-21
- **Status:** accepted
- **Domains:** mobile, network
- **Source:** direct
- **Reason:** A retry outside the worker races the queue it feeds.
- **Global:** [[decisions/mobile#{GDEC}-MOB-009]]

---

## {DEC}-003 — Links a real domain entry but names the wrong domain file

- **Decided:** 2026-01-22
- **Status:** accepted
- **Domains:** mobile
- **Source:** direct
- **Reason:** {GDEC}-MOB-011 lives in mobile.md, not systems.md — the mistyped
  domain segment must be reported instead of silently resolving on the id alone.
- **Global:** [[decisions/systems#{GDEC}-MOB-011]]
