# Project Plan: Partial states
Date: 2026-07-24

Fixture for the `[~]` partial state. One task of each kind, so the counts must
read done=1 / partial=1 / total=3: a partial task is unfinished work — it
counts toward `total` but never toward `done`, and it is a legitimate
`next_task`. A `!= " "` classification would read done=2 and report in-flight
work as finished.

---

## Stage 1: Mixed states

**Goal:** Exercise all three Status characters.

### Task 1.1: Finish the base
- **Status:** [x]
- **Test:** `true`

### Task 1.2: Wire the middle
- **Status:** [~]
- **Test:** `true`

### Task 1.3: Cap it off
- **Status:** [ ]
- **Test:** `true`

### Stage 1 Gate
- [ ] all three states classified
