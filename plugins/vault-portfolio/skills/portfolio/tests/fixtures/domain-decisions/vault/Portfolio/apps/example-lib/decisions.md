# Decisions

Architectural decisions binding this project, newest first.

---

## {DEC}-001 — Release builds pin the toolchain too

- **Decided:** 2026-03-05
- **Status:** accepted
- **Domains:** rust
- **Source:** direct
- **Reason:** The library is built by the same release job, so it inherits the
  same reproducibility problem.
