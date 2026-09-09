#!/usr/bin/env bash
set -eu
R="$(cd "$(dirname "$0")/.." && pwd)"
C="$R/plugins/obsidian-wiki/scripts"; P="$R/ports/cursor/obsidian-wiki/scripts"
for f in apply-chat.py build-chat-worklist.py build-index.py chat_records.py commit-chat-revision.py import-chat.py matrix_chat_adapter.py prepare-chat-pilot.py preview-chat.py review-media.py sanitize-chat.py validate-chat.py vault-write-protocol.py vault_write_protocol.py; do cmp -s "$C/$f" "$P/$f"; done
test -f "$R/ports/cursor/obsidian-wiki/skills/wiki-import-chat/SKILL.md"
test -f "$R/ports/cursor/obsidian-wiki/skills/wiki-review-chat/SKILL.md"
! test -e "$R/ports/cursor/obsidian-wiki/hooks"
echo ALL OK
