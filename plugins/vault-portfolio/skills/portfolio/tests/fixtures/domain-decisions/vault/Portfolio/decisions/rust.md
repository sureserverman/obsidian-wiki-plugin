# Rust decisions

Cross-project decisions binding every project on the `rust` domain. Ids: `GDEC-RS-NNN`.

---

## {GDEC}-RS-001 — Release builds pin the toolchain

- **Decided:** 2026-03-01
- **Status:** accepted
- **Reason:** An unpinned toolchain changed lint output between two release builds
  of the same commit. Pinning keeps a rebuild reproducible. Accepted cost: a
  deliberate bump step.
- **Applies to:**
  - apps/[[example-app]] (ships release builds; {DEC}-001)

## {GDEC}-RS-002 — Vendored dependencies for offline builds

- **Decided:** 2026-02-01
- **Status:** superseded by {GDEC}-RS-001
- **Reason:** Offline builds needed every crate on disk. Superseded once the
  pinned toolchain made the registry mirror reliable.
- **Applies to:**
  - apps/[[example-app]] (builds offline; {DEC}-001)
