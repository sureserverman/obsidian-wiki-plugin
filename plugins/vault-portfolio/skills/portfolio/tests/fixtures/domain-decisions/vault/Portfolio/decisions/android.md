# Android decisions

Cross-project decisions binding every project on the `android` domain. Ids: `GDEC-AND-NNN`.

---

## {GDEC}-AND-001 — Network access goes through one client

- **Decided:** 2026-04-01
- **Status:** accepted
- **Source:** code review
- **Reason:** Two HTTP stacks disagreed about proxy settings. One client keeps
  the policy in one place.
- **Applies to:**
  - apps/[[example-mobile]] (talks to the network; {DEC}-004)
