# Decisions

Architectural decisions binding this project, newest first.

---

## {DEC}-003 — Keep the cache format private

- **Decided:** 2026-06-01
- **Status:** accepted
- **Domains:** rust
- **Source:** direct
- **Reason:** The on-disk cache layout changes with every release. Nothing
  outside this project reads it.
- **Global:** none — project-local, promotion considered

## {DEC}-002 — Errors carry a stable code

- **Decided:** 2026-05-01
- **Status:** accepted
- **Domains:** rust
- **Source:** direct
- **Reason:** Callers matched on message text, which broke on every rewording.
  A stable code is what a caller may match. Rejected: matching on the type name.

## {DEC}-001 — Release builds pin the toolchain

- **Decided:** 2026-03-01
- **Status:** accepted
- **Domains:** rust
- **Source:** direct
- **Reason:** An unpinned toolchain changed lint output between two release
  builds of the same commit.
- **Global:** [[decisions/rust#{GDEC}-RS-001]]
