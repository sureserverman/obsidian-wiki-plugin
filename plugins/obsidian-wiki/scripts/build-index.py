#!/usr/bin/env python3
"""Deterministic builder for <vault>/index.md (obsidian-wiki:index skill).

Reads every page under the vault's category directories in one complete pass and
writes the machine-readable index. Deterministic by design: no LLM, no token
limits, identical output for identical input — so it never truncates on large
vaults the way a delegated read-pass can.

Division of labour with the skill:
  - The skill resolves the vault path and the category-dir list (from the vault's
    CLAUDE.md schema) and passes them in. The skill appends the log entry and
    reports to the user.
  - This script owns the walk, per-page extraction, assembly, idempotency compare,
    and the write. It prints parseable stats the skill uses for the log line.

Usage:
  build-index.py --vault /path/to/vault [--category Architecture --category Gotchas ...]
                 [--date YYYY-MM-DD] [--dry-run]

If no --category is given, categories are auto-detected: immediate subdirectories
of the vault that contain at least one .md file, excluding infrastructure dirs
(raw, Portfolio, .obsidian, and any dotted dir). Pass explicit --category flags to
honor a vault schema that differs from this heuristic.

Stats printed to stdout (one key=value per line):
  TOTAL_PAGES=<N>
  STATUS=new|identical|changed
  CHANGED_BLOCKS=<M>   ADDED=<a>   REMOVED=<r>     (only when STATUS=changed)
  ADDED_PATHS=...; REMOVED_PATHS=...               (only when STATUS=changed)
"""
import argparse
import datetime
import os
import re
import sys

# Root-level vault files that are never pages, defended against even if they
# somehow appear inside a category dir.
SKIP_BASENAMES = {"index.md", "home.md", "claude.md", "log.md"}
# Infra dirs excluded from category auto-detection.
EXCLUDE_DIRS = {"raw", "portfolio", ".obsidian", ".git"}

STOP = {
    "the","this","that","these","those","there","then","thus","they","their","them",
    "and","but","for","nor","yet","with","without","into","onto","over","under","via",
    "per","from","when","while","after","before","because","since","here","its","your",
    "you","our","his","her","each","every","some","any","all","not","now","use","used",
    "using","note","also","see","both","either","neither","same","other","another",
    "such","most","more","less","many","few","one","two","three","four","first","second",
    "third","among","between","during","within","across","through","multiple","avoid",
    "what","which","where","whose","why","how","who","whom","does","did","has","have",
    "had","will","would","should","could","can","may","might","must","are","was","were",
    "been","being","i.e","e.g","example","key","problem","overview","details","sources",
    "tldr","workaround","workarounds","fix","solution","detail","background","context",
    "summary","reason","cause","root","step","steps","result",
    # structural / imperative-verb noise that leaks from list items & sentence starts
    "make","keep","block","assign","mark","set","setup","enable","enabled","disable",
    "install","build","test","verify","run","add","remove","create","check","ensure",
    "configure","update","drop","push","pull","open","close","start","stop","restart",
    "requires","require","required","single","double","existing","option","core","info",
    "standard","path","version","code","name","type","types","implementation","platform",
    "developer","tradeoffs","tradeoff","everything","anything","traffic","position",
    "mitigation","attack","forge","poison","tamper","compromised","signed","unsigned",
    "relevant","entire","local","adjacent","instead","finally","additionally","however",
    "therefore","given","based","follow","following","prefer","recommended","pragmatic",
    "viable","full","mostly","simply","often","dr",
}


def parse_frontmatter(text):
    """Return (meta, body). meta has title/updated/tags."""
    meta = {"title": None, "updated": None, "tags": []}
    if not text.startswith("---"):
        return meta, text
    lines = text.split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return meta, text
    fm = lines[1:end]
    body = "\n".join(lines[end + 1:])
    i = 0
    while i < len(fm):
        m = re.match(r'^(\w[\w-]*):\s*(.*)$', fm[i])
        if not m:
            i += 1
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "title":
            meta["title"] = val.strip('"\'')
        elif key == "updated":
            meta["updated"] = val.strip('"\'')
        elif key == "tags":
            if val.startswith("["):
                inner = val.strip("[]")
                meta["tags"] = [t.strip().strip('"\'') for t in inner.split(",") if t.strip()]
            elif val:
                meta["tags"] = [t.strip().strip('"\'') for t in val.split(",") if t.strip()]
            else:
                j = i + 1
                tags = []
                while j < len(fm) and re.match(r'^\s+-\s+', fm[j]):
                    tags.append(re.sub(r'^\s+-\s+', '', fm[j]).strip().strip('"\''))
                    j += 1
                meta["tags"] = tags
                i = j - 1
        i += 1
    return meta, body


def strip_md(s):
    s = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', s)   # [[a|b]] -> b
    s = re.sub(r'\[\[([^\]]+)\]\]', r'\1', s)              # [[a]]   -> a
    s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)         # [t](u)  -> t
    s = re.sub(r'[`*_]', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def headings_of(body):
    hs = set()
    for line in body.split("\n"):
        m = re.match(r'^#{1,6}\s+(.*)$', line)
        if m:
            hs.add(strip_md(m.group(1)).lower())
    return hs


def first_sentence(s):
    if not s:
        return ""
    m = re.search(r'(.+?[.!?])(\s|$)', s)
    sent = m.group(1) if m else s
    if len(sent) > 200:
        sent = sent[:200].rsplit(" ", 1)[0] + "…"
    return sent


def extract_summary(body):
    lines = body.split("\n")
    # 1) TL;DR block
    for i, line in enumerate(lines):
        if re.match(r'^#{1,6}\s*TL;?DR', line, re.I):
            para = []
            for l in lines[i + 1:]:
                if l.strip() == "":
                    if para:
                        break
                    continue
                if l.startswith("#"):
                    break
                para.append(l.strip())
            if para:
                return first_sentence(strip_md(" ".join(para)))
    # 2) first prose paragraph
    in_fence = False
    para = []
    for line in lines:
        st = line.strip()
        if st.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if st == "":
            if para:
                break
            continue
        if st.startswith("#") or st.startswith("|") or st.startswith(">"):
            if para:
                break
            continue
        if re.match(r'^[-*]\s+', st) or re.match(r'^\d+\.\s+', st):
            if para:
                break
            continue
        para.append(st)
    if para:
        return first_sentence(strip_md(" ".join(para)))
    return ""


def extract_topics(body, headings):
    body = re.sub(r'```.*?```', ' ', body, flags=re.S)
    prose = [l for l in body.split("\n")
             if not (l.strip().startswith(("#", "|", ">")))]
    text = "\n".join(prose)
    seen = {}
    pat = re.compile(r'[A-Z][\w.+\-]*(?:\s+[A-Z][\w.+\-]*)*')
    for raw in pat.findall(text):
        words = raw.split()
        while words and words[0].lower().strip('.,;:') in STOP:
            words.pop(0)
        while words and words[-1].lower().strip('.,;:') in STOP:
            words.pop()
        if not words or len(words) > 4:
            continue
        tok = " ".join(words).strip(" .,;:'\"")
        if len(tok) < 4:
            continue
        low = tok.lower()
        if low in STOP or low in headings or not re.search(r'[A-Za-z]', tok):
            continue
        if low not in seen:
            seen[low] = tok
        if len(seen) >= 30:
            break
    return list(seen.values())


def page_block(title, rel, summary, tags, topics, updated):
    return (
        f"### [[{title}]]\n"
        f"- path: {rel}\n"
        f"- summary: {summary}\n"
        f"- tags: {', '.join(tags)}\n"
        f"- topics: {', '.join(topics)}\n"
        f"- updated: {updated}\n"
    )


def detect_categories(vault):
    cats = []
    for name in sorted(os.listdir(vault)):
        d = os.path.join(vault, name)
        if not os.path.isdir(d) or name.startswith(".") or name.lower() in EXCLUDE_DIRS:
            continue
        if any(f.endswith(".md") for f in os.listdir(d)):
            cats.append(name)
    return cats


def parse_blocks(text):
    """path -> block text, for diffing."""
    blocks, cur, path = {}, [], None
    for line in text.split("\n"):
        if line.startswith("### "):
            if path:
                blocks[path] = "\n".join(cur).strip()
            cur, path = [line], None
        elif cur:
            cur.append(line)
            m = re.match(r'^- path:\s*(.*)$', line)
            if m and path is None:
                path = m.group(1).strip()
    if path:
        blocks[path] = "\n".join(cur).strip()
    return blocks


def build(vault, categories, date):
    blocks_by_cat, total = {}, 0
    for cat in categories:
        d = os.path.join(vault, cat)
        if not os.path.isdir(d):
            continue
        entries = []
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md") or fn.lower() in SKIP_BASENAMES:
                continue
            fp = os.path.join(d, fn)
            if not os.path.isfile(fp):
                continue
            text = open(fp, encoding="utf-8", errors="replace").read()
            meta, body = parse_frontmatter(text)
            title = meta["title"] or fn[:-3]
            updated = meta["updated"] or datetime.date.fromtimestamp(
                os.path.getmtime(fp)).isoformat()
            hs = headings_of(body)
            block = page_block(title, f"{cat}/{fn}", extract_summary(body),
                               meta["tags"], extract_topics(body, hs), updated)
            entries.append((title.lower(), block))
            total += 1
        entries.sort(key=lambda x: x[0])
        blocks_by_cat[cat] = [b for _, b in entries]

    out = ["# Vault Index\n",
           f"Auto-generated by /obsidian-wiki:index on {date}. Do not hand-edit.\n"
           "Re-run after ingesting new sources.\n",
           f"Vault: {vault}\nPages indexed: {total}\n"]
    for cat in categories:
        if blocks_by_cat.get(cat):
            out.append(f"## {cat}/\n")
            out.append("\n".join(blocks_by_cat[cat]))
    return "\n".join(out).rstrip("\n") + "\n", total


def main():
    ap = argparse.ArgumentParser(description="Build <vault>/index.md deterministically.")
    ap.add_argument("--vault", required=True, help="vault root path")
    ap.add_argument("--category", action="append", default=[],
                    help="category dir to index (repeatable); auto-detected if omitted")
    ap.add_argument("--date", default=datetime.date.today().isoformat(),
                    help="date stamp for the header (default: today)")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and diff but do not write")
    args = ap.parse_args()

    vault = os.path.abspath(args.vault)
    if not os.path.isdir(vault):
        sys.exit(f"error: vault not found: {vault}")

    categories = args.category or detect_categories(vault)
    content, total = build(vault, categories, args.date)
    print(f"TOTAL_PAGES={total}")
    print(f"CATEGORIES={', '.join(categories)}")

    idx = os.path.join(vault, "index.md")
    if not os.path.exists(idx):
        if not args.dry_run:
            open(idx, "w", encoding="utf-8").write(content)
        print("STATUS=new")
        return
    old = open(idx, encoding="utf-8", errors="replace").read()
    if old == content:
        print("STATUS=identical")
        return
    ob, nb = parse_blocks(old), parse_blocks(content)
    changed = sum(1 for p, b in nb.items() if ob.get(p) != b)
    added = sorted(p for p in nb if p not in ob)
    removed = sorted(p for p in ob if p not in nb)
    if not args.dry_run:
        open(idx, "w", encoding="utf-8").write(content)
    print(f"STATUS=changed CHANGED_BLOCKS={changed} ADDED={len(added)} REMOVED={len(removed)}")
    print("ADDED_PATHS=" + "; ".join(added))
    print("REMOVED_PATHS=" + "; ".join(removed))


if __name__ == "__main__":
    main()
