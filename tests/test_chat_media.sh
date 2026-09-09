#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; SCRIPT="$ROOT/plugins/obsidian-wiki/scripts/review-media.py"; TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
printf 'not-an-image' >"$TMP/file.bin"
python3 "$SCRIPT" "$TMP/file.bin" --json >"$TMP/out" || { cat "$TMP/out"; exit 1; }
jq -e '.review_status == "manual-review-required" and .ocr.status == "unavailable"' "$TMP/out" >/dev/null
echo "ALL OK"
