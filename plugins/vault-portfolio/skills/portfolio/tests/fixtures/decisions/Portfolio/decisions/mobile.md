# Mobile decisions

Cross-project decisions binding every mobile project in the portfolio.
Domain tag: MOB

---

## {GDEC}-MOB-003 — Long work runs off the UI thread

- **Decided:** 2026-01-20
- **Status:** accepted
- **Reason:** The platform kills an app whose UI thread stalls, and network
  work stalls it whenever the network is slow. A worker is the only shape that
  survives a slow network.
- **Applies to:**
  - apps/[[example-app]] (ships the worker; {DEC}-007)
  - apps/[[example-widget]] (no decisions.md — unresolved on purpose)

---

## {GDEC}-MOB-011 — Target the latest stable platform minus one

- **Decided:** 2025-12-10
- **Status:** accepted
- **Reason:** Gives store reviewers a settled platform to test on.
- **Applies to:**
  - apps/[[example-app]] (asymmetric on purpose — no back-link)
