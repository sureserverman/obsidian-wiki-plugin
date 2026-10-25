# Systems decisions

Domain tag: SYS

---

## {GDEC}-SYS-001 — Desktop apps use the toolkit bindings, never raw FFI

- **Decided:** 2025-11-11
- **Status:** accepted
- **Reason:** Raw FFI reintroduces the lifetime bugs the bindings exist to prevent.
- **Applies to:**
  - tools/[[example-viewer]] (desktop viewer; {DEC}-002)

---

## {GDEC}-SYS-002 — Entry with an unprefixed applies-to link

- **Decided:** 2025-11-12
- **Status:** accepted
- **Reason:** The bare wikilink below has no `<area>/` prefix on purpose.
- **Applies to:**
  - [[example-viewer]] (missing the area prefix — must be flagged)
