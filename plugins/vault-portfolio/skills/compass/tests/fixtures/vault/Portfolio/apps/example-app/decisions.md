# Decisions

Architectural decisions binding this project, newest first.

---

## {DEC}-002 — Ship the widget pipeline as one binary

- **Decided:** 2026-07-10
- **Status:** accepted
- **Domains:** rust, Ubuntu
- **Source:** plan `2026-06-01-widget-plan.md`
- **Reason:** Two binaries doubled the packaging surface for no gain; one
  binary keeps the .deb postinst trivial. Rejected: a split client/daemon.

## {DEC}-001 — Store widget state under XDG_STATE_HOME

- **Decided:** 2026-05-04
- **Status:** superseded by {DEC}-002
- **Domains:** ubuntu, none
- **Source:** direct
- **Reason:** ~/.widget collided with the packaged config; XDG keeps state out
  of the config tree. Accepted cost: one migration step on upgrade.

## {DEC}-3 - plain hyphen, unpadded id

- **Decided:** 2026-09-09
- **Status:** accepted
- **Domains:** ghosts
- **Source:** direct
- **Reason:** Malformed heading — must never reach count, domains, or
  last_decided.
