# WF-WIKI-LOOKUP — Local published-note lookup

Status: implementation in progress; pilot inactive.

An operator refreshes a private local derived generation explicitly. Retrieval
reads the configured vault and never writes source notes. The read executable
accepts versioned JSON on stdin for search, resolve, get, verify_citations and
status. Administrative refresh/check use a separate executable.

Search returns discovery hints after complete source checks. Exact resolution
selects a unique published locator/title/alias or surfaces ambiguity. Get reads
one to five complete admitted projections from one generation. Stale, corrupt,
unsupported or unavailable inputs refuse with bounded codes; refusal cannot
become an empty result or an unrestricted direct-source fallback.

Each answer has a cumulative 24,000-byte serialized evidence-response budget.
Oversized notes are omitted completely and cannot be cited as read. Authentic
read receipts and exact UTF-8 spans bind each citation occurrence to returned
evidence. Structural provenance does not establish semantic claim support.
Absent evidence requires abstention; partial evidence requires explicit
omissions. Preserve dates, status, modality and contradictory observations;
dated endpoints do not establish continuous state between them.

Optional file-back requires separate owner confirmation and the existing
WF-VAULT-WRITE-MAINTENANCE / WF-CHAT-PUBLISH gates. Lookup does not acquire
publication authority or replace WF-CHAT-IMPORT. No hooks, automatic refresh,
link expansion, vault-context migration or normal-route adoption are included.
