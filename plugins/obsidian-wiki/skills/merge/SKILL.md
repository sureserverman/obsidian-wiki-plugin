---
name: merge
description: >
  Use when the user asks to merge two Obsidian vault pages into one, consolidate
  duplicate notes, mentions "/obsidian-wiki:merge", or says "these two pages are about the
  same thing". Trigger on "merge these notes", "consolidate X and Y", "this is a
  duplicate of", or "fold this page into".
---

> **Vault path:** `<vault>` refers to the path returned by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`. Run it first to resolve the vault location.

# Vault Merge

Merge two pages in `<vault>` into one canonical page and update every inbound
`[[wikilink]]` across the vault to point to the survivor. This is the consolidation
operation — what you do when ingest discovered a duplicate, or when you found two
pages on the same topic by different names.

This skill is **destructive**: the loser page is deleted. It always produces a plan
first and waits for confirmation per step.

## Step 1 — Identify the survivor and the loser

The user names two pages. Decide which one survives:

- **Survivor**: the page whose path is more canonical (better category, better filename),
  or the one with more content.
- **Loser**: the page being absorbed.

If the choice is ambiguous, ask the user explicitly. Do not guess. This is a one-way
operation.

## Step 2 — Merge the content

Read both pages. Build the merged body:

- **Frontmatter**: union of `tags`, union of `aliases` (add the loser's title to
  survivor's aliases — important for backlink resolution), union of `related`, union
  of `sources`, latest `updated:` date, earlier `created:` date.
- **TL;DR**: keep the better one. If they conflict, keep both as bullets and ask the
  user to refine.
- **Key points / Details**: deduplicate. If the same fact appears in both pages with
  different wording, keep the clearer version. If both pages say contradicting things,
  surface the contradiction in a `## Conflicts` section — do not silently pick one.
- **Sources**: merge both lists.

Show the user the proposed merged page in full and wait for approval before writing.

## Step 3 — Find inbound wikilinks

Grep the entire vault for `[[<loser-basename>]]` and `[[<loser-basename>|...]]` link
forms. Also check for the loser's `aliases:` — any page that linked to an alias needs
updating too.

Build a list of (file, line, current link form) tuples. This is the inbound link
inventory.

## Step 4 — Show the rewrite plan

Present a numbered plan:

```markdown
# Merge plan: `Gotchas/old-name.md` → `Gotchas/canonical-name.md`

## Content merge
- Survivor: `Gotchas/canonical-name.md` (will be rewritten with merged content)
- Loser: `Gotchas/old-name.md` (will be deleted)

## Inbound link rewrites (N)
1. `Architecture/X.md:42` — `[[old-name]]` → `[[canonical-name]]`
2. `Patterns/Y.md:18` — `[[old-name|alias]]` → `[[canonical-name|alias]]`
3. ...

## Home.md
- Remove row for `[[old-name]]` (loser no longer exists)
- (Survivor row stays as-is)
```

Ask for confirmation per phase: content merge, link rewrites, deletion, Home.md
update. Do not batch.

## Step 5 — Apply, in this order

The order matters. If you delete the loser first, the inbound links become broken
before they're rewritten — `lint` would flag every one.

1. **Write the merged content** to the survivor. Use Write (this is a full rewrite of
   the survivor) only after the user has approved the merged body in Step 2.
2. **Rewrite each inbound link** using Edit. One link at a time. Confirm groups of
   ~5 if the count is large.
3. **Update `Home.md`**: remove the loser's row using Edit. Do not touch the survivor's
   row.
4. **Delete the loser** with the Bash `rm` tool. Only after every link has been
   rewritten and Home.md updated.
5. **Append to log.md**:
   ```
   ## [YYYY-MM-DD] merge | <loser> → <survivor>
   - Inbound links rewritten: <N>
   - Home.md updated: yes/no
   - Reason: <user's reason>
   ```

Type `merge` is an extension to the standard log types. If `CLAUDE.md` doesn't permit
it yet, mention this as a candidate schema update.

## What never to do

- **Delete the loser before rewriting links.** Always link-rewrite first.
- **Auto-resolve content conflicts.** Surface them.
- **Forget to add the loser's title to the survivor's `aliases:`.** Without this,
  future ingest passes might recreate the loser as a "new" page.
- **Skip Home.md.** Leaving an orphaned row in the index breaks the wiki.
- **Merge across categories without confirmation.** Moving a page from `Gotchas/` to
  `Patterns/` is a structural decision the user must make.

## Delegation (optional, for cost/speed)

Step 2 (building the merged body: frontmatter union, TL;DR consolidation, key-
points dedup, contradiction surfacing) is a Sonnet-tier content job. If you are
on Opus, delegate the body build to the `vault-writer` subagent (model: sonnet)
via the Agent tool with `subagent_type: vault-writer`. Give it:

- both page paths and the chosen survivor/loser assignment,
- the frontmatter-merge rules from Step 2 (union semantics, date rules, alias
  addition),
- the instruction to surface any contradictions as a `## Conflicts` section
  rather than silently pick.

Write mode for `vault-writer` is "merge two overlapping pages." It returns the
merged body for you to show the user for approval; it does **not** perform the
deletion, the inbound link rewrites, Home.md updates, or the log append — those
stay in this session because they span multiple files and require per-phase
confirmation as Step 5 describes.

## Common pitfalls

- Missing alias-form inbound links. Grep for both `[[loser]]` and `[[loser|`.
- Missing inbound links in `raw/` source files. Don't rewrite those — `raw/` is
  immutable. Just note them in the report so the user can decide.
- Forgetting that the survivor might also need new `tags` or `related:` from the loser.
- Treating the merged TL;DR as something to auto-generate. Ask the user if both
  pages had distinct framings.
