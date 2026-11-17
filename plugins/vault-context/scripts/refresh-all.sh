#!/usr/bin/env bash
# refresh-all.sh --registry <path> [--vault <path>] [--dry-run]
#
# Regenerate the vault-context sidecar of every registered project that already has
# one — the same three-step pipeline the `link` skill runs, once per project, from
# that project's folder:
#
#   extract-project-signals.sh | match-index.py <vault>/index.md | write-context.sh <name> <vault> <sidecar>
#
# It never links a project: a registered directory without `.claude/vault-context.md`
# is left alone. A directory lib/eligibility.sh does not call a project (an area
# directory, W DEC-001) is skipped with a line saying so; a registered folder that
# no longer exists is reported and the run continues. --dry-run lists what it would
# do and changes no file.
#
# Exit: 0 every linked project refreshed; 1 at least one failed (each named);
#       2 usage, unreadable registry, or no vault.
set -u

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY=""; VAULT=""; DRY=0
while [ $# -gt 0 ]; do
    case "$1" in
        --registry) REGISTRY="${2:-}"; shift 2 ;;
        --vault)    VAULT="${2:-}"; shift 2 ;;
        --dry-run)  DRY=1; shift ;;
        *) echo "usage: $0 --registry <path> [--vault <path>] [--dry-run]" >&2; exit 2 ;;
    esac
done
[ -n "$REGISTRY" ] || { echo "usage: $0 --registry <path> [--vault <path>] [--dry-run]" >&2; exit 2; }
[ -r "$REGISTRY" ] || { echo "refresh-all: cannot read registry $REGISTRY" >&2; exit 2; }
if [ -z "$VAULT" ]; then
    VAULT="$(bash "$SCRIPTS/resolve-vault.sh" 2>/dev/null)" || VAULT=""
fi
[ -n "$VAULT" ] && [ -f "$VAULT/index.md" ] || { echo "refresh-all: vault not reachable (no index.md at '${VAULT}')" >&2; exit 2; }

# The containment rule and write-context.sh read the same registry this run walks.
export VAULT_CONTEXT_REGISTRY="$REGISTRY"
# shellcheck source=lib/eligibility.sh
. "$SCRIPTS/lib/eligibility.sh"

entries="$(python3 - "$REGISTRY" <<'EOF'
import os, re, sys
cur = None
out = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = re.sub(r"\s+#.*$", "", line)
    mp = re.match(r"\s*-\s*path:\s*(.+?)\s*$", line)
    if mp:
        cur = {"path": os.path.expanduser(mp.group(1).strip("\"'"))}
        out.append(cur)
        continue
    mn = re.match(r"\s+name:\s*(.+?)\s*$", line)
    if mn and cur is not None and "name" not in cur:
        cur["name"] = mn.group(1).strip("\"'")
for e in out:
    name = e.get("name") or os.path.basename(e["path"].rstrip("/"))
    if "\t" in e["path"] or "\n" in e["path"] or "\t" in name:
        continue
    print(f"{e['path']}\t{name}")
EOF
)" || { echo "refresh-all: cannot parse registry $REGISTRY" >&2; exit 2; }

refreshed=0; failed=0; skipped=0
while IFS=$'\t' read -r path name; do
    [ -n "$path" ] || continue
    if [ ! -d "$path" ]; then
        echo "skipped: folder missing: $path"; skipped=$((skipped + 1)); continue
    fi
    phys="$(cd "$path" && pwd -P)"
    if ! project_eligible "$phys"; then
        echo "skipped: area directory: $path"; skipped=$((skipped + 1)); continue
    fi
    sidecar="$phys/.claude/vault-context.md"
    if [ ! -f "$sidecar" ]; then
        skipped=$((skipped + 1)); continue   # not linked; never link here
    fi
    if [ "$DRY" = 1 ]; then
        echo "would refresh: $name ($path)"; refreshed=$((refreshed + 1)); continue
    fi
    errf="$(mktemp)"
    # Success is write-context.sh's exit, as in the link skill's pipeline: the signal
    # extractor exits non-zero in a repo with no commits yet still prints its signals,
    # and a matcher failure reaches write-context.sh as input it refuses.
    if ( cd "$phys" \
         && bash "$SCRIPTS/extract-project-signals.sh" </dev/null \
          | python3 "$SCRIPTS/match-index.py" "$VAULT/index.md" \
          | bash "$SCRIPTS/write-context.sh" "$name" "$VAULT" "$sidecar" >/dev/null ) 2>"$errf"; then
        echo "refreshed: $name"; refreshed=$((refreshed + 1))
        # Keep warnings a successful run printed (an unparseable stack page, say).
        grep -E '^(render-stacks|sync-stack-rules|write-context):' "$errf" | sed "s|^|  $name: |" || true
    else
        echo "FAILED: $name ($path): $(tail -n 3 "$errf" | tr '\n' ' ')"; failed=$((failed + 1))
    fi
    rm -f "$errf"
done <<<"$entries"

verb="refreshed"; [ "$DRY" = 1 ] && verb="would refresh"
echo "refresh-all: $verb $refreshed, failed $failed, skipped $skipped"
[ "$failed" -eq 0 ]
