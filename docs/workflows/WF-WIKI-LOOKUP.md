# WF-WIKI-LOOKUP — Local published-note lookup

Status: core implemented; command adapter opt-in, actual client qualification pending; pilot inactive.

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

Admission uses an owner-local explicit category list (the fourteen schema-listed
published categories on the selected vault); Portfolio integration records require
individual opt-in paths. Missing sensitivity is accepted only on a supported ordinary
published-note shape with title and valid created date. Explicit nonpublic sensitivity,
drafts, protected filenames/markers, unsafe locator mentions outside removed provenance,
unknown metadata keys and unsupported YAML refuse. Scalars and flat string lists are
the supported YAML subset. Frontmatter and recognized provenance sections are omitted
from the body; safe dates/statuses are separately labeled. No participant identity or
raw/protected locator enters a projection or denial. Reading walks every path component
with directory file descriptors and O_NOFOLLOW, checks regular-file identity before/after
reading, and refuses changes before returning bytes.

Supported Portfolio integration exceptions use their existing `project` and fixed
`depends_on`/`impacts` target/why schema; unknown or incomplete edges refuse.
They do not need ordinary-note title/created fields. Edge metadata is omitted
from output. Reserved protected/identity marker names outside removed provenance
refuse independently of Markdown/JSON/key-value presentation. Supported ordinary
record types/statuses are explicit allowlists, rather than a short denylist.

The user-typed Claude command `ask --local-pilot` is the only adapter entry.
Its grant names `${CLAUDE_PLUGIN_ROOT}/scripts/wiki-access.py` exactly; skills
and agents hold no Bash grant. Questions enter JSON stdin, never shell arguments.
One get per answer enforces cumulative evidence bytes; repeated gets, automatic
refresh/retry and unrestricted source fallback are forbidden. The ordinary ask
route retains its index entry and reports an oversized whole-index read as
unsupported. Configured-client permission matching requires an actual trace;
static grant checks do not prove it. Cursor remains on its existing manual path.
