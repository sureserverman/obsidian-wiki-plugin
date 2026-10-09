"""Immutable derived SQLite data. Callers must guard every disclosure separately."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from .contracts import Refusal, QUERY_BYTES, STORE_BYTES, encode, text, integer

SCHEMA = 'wiki-store.v1'
RECIPE = 'section-or-unicode61-5-3-2-1-1.v1'
# Frozen research stopword rule; casefold only for membership/deduplication.
STOPWORDS = frozenset('what why how which where when does do the a an and or is are can i my in of to for that it with without its did should use from me at on as was but be after before'.split())
OPERATORS = frozenset(('and', 'or', 'not', 'near'))


def terms(query):
    text(query, QUERY_BYTES)
    tokens = re.findall(r'[\w]+(?:[./:+-][\w]+)*|--[\w-]+', query, re.UNICODE)
    if len(tokens) > 64:
        raise Refusal('invalid_request')
    seen = set(); result = []
    for token in tokens:
        key = token.casefold()
        if key not in STOPWORDS | OPERATORS and key not in seen:
            seen.add(key); result.append(token)
    if not result:
        raise Refusal('invalid_request')
    return result


def expression(query):
    return ' OR '.join('"'+token.replace('"', '""')+'"' for token in terms(query))


def capability():
    if sys.version_info < (3, 12):
        raise Refusal('index_unavailable')
    try:
        with sqlite3.connect(':memory:') as db:
            db.execute("CREATE VIRTUAL TABLE probe USING fts5(body, tokenize='unicode61')")
    except sqlite3.Error:
        raise Refusal('index_unavailable') from None


def section_rows(page):
    """Split declared ATX headings outside fences; offsets are UTF-8 bytes."""
    body = page['body']; raw = body.encode('utf-8')
    starts = []; offset = 0; fence = None
    for line in body.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)', line)
        if marker:
            mark = marker[1]
            if fence is None:
                fence = (mark[0], len(mark))
            elif mark[0] == fence[0] and len(mark) >= fence[1] and not marker[2].strip():
                fence = None
        elif fence is None:
            head = re.match(r'^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*\r?\n?$', line)
            if head:
                starts.append((offset, head[1]))
        offset += len(line.encode('utf-8'))
    if not starts or starts[0][0] != 0:
        starts.insert(0, (0, ''))
    for i, (start, heading) in enumerate(starts):
        end = starts[i+1][0] if i+1 < len(starts) else len(raw)
        if start == end:
            continue
        mapping = []
        for span in page['mapping']:
            lo, hi = max(start, span['start']), min(end, span['end'])
            if hi > lo:
                source = span['source_start'] + lo - span['start']
                mapping.append({'start': lo, 'end': hi, 'source_start': source,
                                'source_end': source + hi-lo})
        yield {'start': start, 'end': end, 'heading': heading,
               'body': raw[start:end].decode('utf-8'), 'mapping': mapping}


def validate_page(page):
    """Reject broken projection maps before creating a derived file."""
    try:
        if type(page) is not dict or set(page) != {'locator', 'metadata', 'body', 'mapping', 'omissions', 'source_hash', 'projection_hash'}:
            raise ValueError()
        if type(page['body']) is not str or type(page['metadata']) is not dict or type(page['mapping']) is not list or type(page['omissions']) is not list:
            raise ValueError()
        raw = page['body'].encode('utf-8')
        if hashlib.sha256(raw).hexdigest() != page['projection_hash']:
            raise ValueError()
        if not re.fullmatch('[0-9a-f]{64}', page['source_hash']):
            raise ValueError()
        text(page['locator']); text(page['metadata']['title'])
        for key in ('aliases', 'tags'):
            if type(page['metadata'][key]) is not list:
                raise ValueError()
            for item in page['metadata'][key]: text(item)
        cursor = 0; last_source = 0
        for span in page['mapping']:
            if type(span) is not dict or set(span) != {'start', 'end', 'source_start', 'source_end'} or any(type(v) is not int for v in span.values()):
                raise ValueError()
            if (span['start'] != cursor or not cursor < span['end'] <= len(raw)
                    or span['source_start'] < last_source
                    or span['source_end']-span['source_start'] != span['end']-cursor):
                raise ValueError()
            raw[cursor:span['end']].decode('utf-8')
            cursor = span['end']; last_source = span['source_end']
        if cursor != len(raw): raise ValueError()
        for omission in page['omissions']:
            if (type(omission) is not dict or set(omission) != {'kind', 'source_start', 'source_end'}
                    or omission['kind'] not in ('frontmatter', 'provenance')
                    or type(omission['source_start']) is not int or type(omission['source_end']) is not int
                    or not 0 <= omission['source_start'] < omission['source_end']):
                raise ValueError()
        encode(page)
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise Refusal('index_unavailable') from None


def build(path, pages, generation, *, byte_budget=STORE_BYTES):
    capability()
    integer(byte_budget, 4096, STORE_BYTES)
    if not re.fullmatch('[0-9a-f]{64}', generation):
        raise Refusal('index_unavailable')
    pages = list(pages)
    for page in pages: validate_page(page)
    if len({p['locator'] for p in pages}) != len(pages):
        raise Refusal('index_unavailable')
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA max_page_count='+str(byte_budget//4096))
            db.execute('PRAGMA journal_mode=OFF')
            db.execute('PRAGMA synchronous=OFF')
            db.executescript('''
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE pages(page_id TEXT PRIMARY KEY, locator TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL, metadata TEXT NOT NULL, body TEXT NOT NULL,
                    mapping TEXT NOT NULL, omissions TEXT NOT NULL,
                    source_hash TEXT NOT NULL, projection_hash TEXT NOT NULL);
                CREATE TABLE sections(section_id INTEGER PRIMARY KEY, page_id TEXT NOT NULL,
                    start INTEGER NOT NULL, end INTEGER NOT NULL, heading TEXT NOT NULL,
                    body TEXT NOT NULL, mapping TEXT NOT NULL);
                CREATE VIRTUAL TABLE search USING fts5(title, aliases, tags, heading, body,
                    tokenize='unicode61');
            ''')
            db.executemany('INSERT INTO meta VALUES (?, ?)',
                           [('schema', SCHEMA), ('recipe', RECIPE), ('generation', generation)])
            for page in sorted(pages, key=lambda p: p['locator']):
                page_id = hashlib.sha256(encode([generation, page['locator']])).hexdigest()
                meta = page['metadata']
                db.execute('INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?)',
                    (page_id, page['locator'], meta['title'], encode(meta).decode(), page['body'],
                     encode(page['mapping']).decode(), encode(page['omissions']).decode(),
                     page['source_hash'], page['projection_hash']))
                for row in section_rows(page):
                    cursor = db.execute('INSERT INTO sections(page_id,start,end,heading,body,mapping) VALUES (?,?,?,?,?,?)',
                        (page_id, row['start'], row['end'], row['heading'], row['body'], encode(row['mapping']).decode()))
                    db.execute('INSERT INTO search(rowid,title,aliases,tags,heading,body) VALUES (?,?,?,?,?,?)',
                        (cursor.lastrowid, meta['title'], ' '.join(meta['aliases']), ' '.join(meta['tags']), row['heading'], row['body']))
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise Refusal('index_unavailable')
            db.execute("INSERT INTO search(search) VALUES('integrity-check')")
        if path.stat().st_size > byte_budget:
            raise Refusal('budget_exhausted')
        with Store(path, generation): pass
    except sqlite3.Error as exc:
        if getattr(exc,'sqlite_errorcode',None) == sqlite3.SQLITE_FULL:
            raise Refusal('budget_exhausted') from None
        raise Refusal('index_unavailable') from None
    except OSError:
        raise Refusal('index_unavailable') from None


class Store:
    def __init__(self, path, generation):
        self.db = None
        try:
            self.db = sqlite3.connect(Path(path).absolute().as_uri()+'?mode=ro&immutable=1', uri=True)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA trusted_schema=OFF')
            meta = self.metadata()
            if meta.get('schema') != SCHEMA or meta.get('recipe') != RECIPE:
                raise Refusal('unsupported_schema')
            if meta.get('generation') != generation:
                raise Refusal('index_unavailable')
            if self.db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise Refusal('index_unavailable')
            # Physical integrity alone accepts a valid SQLite file with no pilot tables.
            expected = {'pages': ('page_id','locator','title','metadata','body','mapping','omissions','source_hash','projection_hash'),
                        'sections': ('section_id','page_id','start','end','heading','body','mapping'),
                        'search': ('title','aliases','tags','heading','body')}
            for table, columns in expected.items():
                if tuple(row['name'] for row in self.db.execute('PRAGMA table_info('+table+')')) != columns:
                    raise Refusal('index_unavailable')
            self.db.execute('SELECT rowid FROM search WHERE search MATCH ? LIMIT 1', ('"capabilityprobe"',)).fetchall()
        except (sqlite3.Error, OSError):
            self.close(); raise Refusal('index_unavailable') from None
        except Refusal:
            self.close(); raise

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def close(self):
        if self.db is not None:
            self.db.close(); self.db = None

    def metadata(self):
        return dict(self.db.execute('SELECT key,value FROM meta'))

    @staticmethod
    def unpack(row):
        result = dict(row)
        for key in ('metadata', 'mapping', 'omissions'):
            if key in result: result[key] = json.loads(result[key])
        return result

    def page(self, page_id):
        row = self.db.execute('SELECT * FROM pages WHERE page_id=?', (page_id,)).fetchone()
        return self.unpack(row) if row else None

    def sections(self):
        return [self.unpack(row) for row in self.db.execute('SELECT * FROM sections ORDER BY section_id')]

    def resolve(self, kind, value):
        if kind not in ('path', 'title', 'alias'): raise Refusal()
        text(value)
        rows = self.db.execute('SELECT * FROM pages ORDER BY locator')
        matches = []
        for row in rows:
            page = self.unpack(row)
            choices = ([page['locator']] if kind == 'path' else
                       [page['title']] if kind == 'title' else page['metadata']['aliases'])
            if value.casefold() in [c.casefold() for c in choices]: matches.append(page)
        return matches

    def search(self, query, limit, filters):
        integer(limit, 1, 10)
        # Validate filter grammar through the shared contract, never interpolate values.
        from .contracts import validate_request, SCHEMA as WIRE
        validate_request({'schema': WIRE, 'operation': 'search', 'query': query,
                          'limit': limit, 'filters': filters})
        rows = self.db.execute('''SELECT s.*, bm25(search,5,3,2,1,1) AS score
            FROM search JOIN sections s ON s.section_id=search.rowid
            WHERE search MATCH ? ORDER BY score,s.page_id,s.start''', (expression(query),))
        hits = []; seen = set()
        for row in rows:
            if row['page_id'] in seen: continue
            page = self.page(row['page_id']); meta = page['metadata']
            if not self.matches_filters(meta, filters): continue
            seen.add(row['page_id'])
            hits.append(dict(page, heading=row['heading'], excerpt=row['body'][:240], score=row['score']))
            if len(hits) == limit: break
        return hits

    @staticmethod
    def matches_filters(meta, filters):
        for key, value in filters.items():
            if key == 'tag':
                if value not in meta['tags']: return False
            elif key.endswith(('_from', '_to')):
                field, direction = key.rsplit('_', 1)
                if not meta.get(field) or (meta[field] < value if direction == 'from' else meta[field] > value): return False
            elif meta.get(key) != value: return False
        return True
