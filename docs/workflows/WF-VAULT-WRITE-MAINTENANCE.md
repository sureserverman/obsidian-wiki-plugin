---
id: WF-VAULT-WRITE-MAINTENANCE
title: Shared vault exclusive-maintenance protocol
status: accepted
date: 2026-09-06
---

# Shared vault exclusive-maintenance protocol

## Boundary

The Matrix publication workflow uses an owner-confirmed exclusive maintenance
window. It is selected because the live vault mount has no demonstrated shared
lock primitive. `vault_write_protocol.py` is a cooperative write gate, not a
distributed lock: do not use `start` concurrently or claim that it arbitrates
unannounced writers.

Before starting a window, the owner confirms that no other vault writer will
run. During the window, the named operator is the only permitted writer. The
capability token is a secret: keep it in the operator environment and never
put it in a vault page, log, batch, preview, or source record.

```bash
python3 plugins/obsidian-wiki/scripts/vault-write-protocol.py \
  --vault <vault> start --owner <operator> --purpose <change> --lease-seconds <seconds>
export OBSIDIAN_WIKI_MAINTENANCE_TOKEN=<returned-token>
```

`check` permits writes when no window exists. While a window is active it
permits only the current token. A writer must check immediately before every
mutation, then recheck the affected files' base hashes as part of its own
transaction. `finish` removes the window only with the current token.

If an operator disconnects, the lease expires and all participating writers
refuse work. An owner who has checked that the former writer is gone may run
`recover --acknowledge-stale`; recovery stores the prior manifest under
`.obsidian-wiki/maintenance-history/` and creates a new capability. It never
silently overwrites an active or stale owner.

## Writer inventory and required behavior

| Surface | Files affected | Required behavior |
| --- | --- | --- |
| Matrix apply and recovery | proposed pages, `Sources/`, `Systems/`, raw registry, log, index | call `require_write_access` before each journal transition; recheck base hashes |
| `/obsidian-wiki:index` | `index.md` | `build-index.py` calls the gate before writing |
| `/obsidian-wiki:ingest` | category pages, `Home.md`, `log.md` | read maintenance state before proposing or applying edits; stop without the token |
| `/obsidian-wiki:merge` | survivor, inbound pages, `Home.md`, `log.md` | read maintenance state before every confirmed phase; stop without the token |
| `/obsidian-wiki:import-session` | `raw/sessions/`, `log.md` | read maintenance state before creating the raw record or log entry |
| `/obsidian-wiki:rebuild-home` | `Home.md`, `log.md` | read maintenance state before every confirmed edit |
| `vault-schema-maintain` | `CLAUDE.md`, `log.md` | read maintenance state before its approved surgical edit |
| Claude `vault-writer` agent | category pages and raw sources | refuse work when maintenance is held by another operator |
| Cursor `wiki-vault-writer` agent | category pages and raw sources | follow the same refusal rule |
| Hooks and queues | local queue/state only | never write the vault; they must not trigger a vault writer during maintenance |

`/obsidian-wiki:log`, scanners, `ask`, `related`, validation, and preview are
read-only. They do not need a capability and must not infer authorization for a
later write. Cursor has no hook writer; its manual writer follows the same
maintenance state.

## Failure rules

- A missing, malformed, expired, or foreign maintenance manifest blocks writes.
- A changed base hash is a conflict, even when this operator owns the window.
- A failed apply leaves its journal and any completed postimages visible for
  recovery. Do not delete evidence to make a batch appear complete.
- The Stage 3 fixture tests show the protocol behavior. Cross-host contention,
  interruption, and recovery on the actual mount remain P5 evidence.
