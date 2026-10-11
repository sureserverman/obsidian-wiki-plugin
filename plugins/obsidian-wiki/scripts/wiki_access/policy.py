"""Explicit admission and byte-exact projection; unsupported YAML fails closed."""
import datetime
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat

from .contracts import Refusal, encode

VERSION = 'policy.v1'
SOURCE_LIMIT = 2 * 1024 * 1024
CATEGORIES = ('Architecture', 'Decisions', 'Gotchas', 'Incidents', 'Patterns',
    'Plans', 'Platforms', 'Projects', 'Runbooks', 'Technologies', 'Threat Models',
    'Tooling', 'Sources', 'Systems')
LIST_KEYS = {'aliases', 'tags', 'sources', 'related', 'systems', 'devices',
             'depends_on', 'impacts'}
KEYS = LIST_KEYS | {'title', 'created', 'updated', 'type', 'status', 'sensitivity',
    'evidence-status', 'verification-status', 'evidence_status',
    'verification_status', 'platform', 'language', 'focus', 'distribution',
    'source-id', 'revision-id', 'inventory-status', 'extraction-status',
    'project', 'occurred', 'resolved', 'source-period'}
OMIT_KEYS = {'sources', 'source-id', 'revision-id', 'related', 'depends_on', 'impacts'}
UNSAFE = re.compile(r'(?i)(?:\b(?:raw|protected|originals?|identity[-_]maps?)\s*[/\\]'
    r'|\b(?:protected_locator_ref|identity[-_]map|participant[-_]id)\b'
    r'|<!--\s*(?:private|protected|sensitive)\b)')
DENIED_NAME = re.compile(r'(?i)(?:identity[-_ ]map|protected|original transcript|security[-_ ](?:review|report|audit))')
PROVENANCE = {'sources', 'source provenance', 'publication provenance',
              'provenance', 'source references', 'protected provenance'}
PUBLISHED_TYPES = {'note', 'published', 'source-card', 'system', 'platform',
    'runbook', 'plan', 'pattern', 'incident', 'decision', 'architecture',
    'technology', 'tooling', 'project', 'integration'}
PUBLISHED_STATUSES = {'', 'published', 'active', 'current', 'historical',
    'resolved', 'accepted', 'superseded', 'complete', 'completed', 'planned'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_parts(locator):
    if not isinstance(locator, str) or not locator or '\\' in locator or '\x00' in locator:
        raise Refusal('permission_refused')
    parts = locator.split('/')
    if any(not p or p in ('.', '..') or p.startswith('.') for p in parts):
        raise Refusal('permission_refused')
    return parts


class Policy:
    def __init__(self, categories, portfolio=()):
        if type(categories) is not list or not categories or any(type(c) is not str for c in categories):
            raise Refusal('permission_refused')
        if len(set(categories)) != len(categories):
            raise Refusal('permission_refused')
        if any(c not in CATEGORIES for c in categories):
            raise Refusal('permission_refused')
        if not isinstance(portfolio, (list, tuple)):
            raise Refusal('permission_refused')
        for path in portfolio:
            parts = relative_parts(path)
            if len(parts) != 4 or parts[0] != 'Portfolio' or parts[-1] != 'integration.md':
                raise Refusal('permission_refused')
        self.categories = tuple(sorted(categories))
        self.portfolio = tuple(sorted(set(portfolio)))
        self.fingerprint = digest(encode({'version': VERSION,
            'categories': self.categories, 'portfolio': self.portfolio}))

    def permits(self, locator):
        try:
            parts = relative_parts(locator)
        except Refusal:
            return False
        if DENIED_NAME.search(parts[-1]) or parts[-1].lower() in {'index.md', 'home.md', 'claude.md', 'log.md'}:
            return False
        return (len(parts) == 2 and parts[0] in self.categories and parts[-1].endswith('.md')) or locator in self.portfolio


def lines(text):
    """Split on LF only. str.splitlines also breaks on \\v, \\f, \\x1c-\\x1e, U+0085,
    U+2028 and U+2029, which would let a guarded token straddle two checks."""
    parts = text.split('\n')
    return [part + '\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def signature(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def read_bounded(fd, parent, name, before, ceiling):
    """Read an opened file; refuse if it grew past ceiling, changed or was replaced."""
    chunks = []; size = 0
    while True:
        chunk = os.read(fd, min(65536, ceiling + 1 - size))
        if not chunk:
            break
        chunks.append(chunk); size += len(chunk)
        if size > ceiling:
            raise Refusal('budget_exhausted')
    after = os.fstat(fd)
    live = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if signature(before) != signature(after) or signature(after) != signature(live):
        raise Refusal('generation_stale')
    return b''.join(chunks)


def safe_read(root, locator):
    """Walk using directory FDs; O_NOFOLLOW closes the check/open symlink race."""
    parts = relative_parts(locator)
    descriptors = []
    walked = []
    try:
        # Check ancestors of the configured root as well, without resolving links.
        absolute = os.path.abspath(root)
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(fd)
        for part in PurePosixPath(absolute).parts[1:]:
            parent = fd
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(fd)
            walked.append((parent, part, fd))
        for part in parts[:-1]:
            parent = fd
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(fd)
            walked.append((parent, part, fd))
        parent = fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > SOURCE_LIMIT:
            raise Refusal('permission_refused')
        raw = read_bounded(fd, parent, parts[-1], before, SOURCE_LIMIT)
        for parent, name, child in walked:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(child)
            if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise Refusal('generation_stale')
        return raw
    except OSError:
        raise Refusal('source_unavailable') from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def scalar(value):
    value = value.strip()
    if not value:
        return ''
    if value.startswith('"'):
        try:
            result = json.loads(value)
            if not isinstance(result, str):
                raise ValueError()
        except ValueError:
            raise Refusal('permission_refused') from None
        try:
            result.encode('utf-8')
        except UnicodeError:
            raise Refusal('permission_refused') from None
        return result
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'") or re.search(r"(?<!')'(?!')", value[1:-1]):
            raise Refusal('permission_refused')
        return value[1:-1].replace("''", "'")
    if re.search(r'[{}\[\]&*!|>]', value) or ': ' in value or ' #' in value:
        raise Refusal('permission_refused')
    return value


def inline_list(value):
    if not value.startswith('[') or not value.endswith(']'):
        raise Refusal('permission_refused')
    inner = value[1:-1]; tokens = []; start = 0; quote = None; escaped = False
    for i, char in enumerate(inner):
        if escaped:
            escaped = False
        elif char == '\\' and quote == '"':
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == ',':
            tokens.append(scalar(inner[start:i])); start = i+1
    if quote:
        raise Refusal('permission_refused')
    if inner.strip():
        tokens.append(scalar(inner[start:]))
    if any(not token for token in tokens):
        raise Refusal('permission_refused')
    return tokens


def frontmatter(raw, *, integration=False):
    try:
        rows = lines(raw.decode('utf-8'))
    except UnicodeError:
        raise Refusal('permission_refused') from None
    if not rows or rows[0].strip() != '---':
        raise Refusal('permission_refused')
    metadata = {}; list_key = None; offset = len(rows[0].encode())
    for line in rows[1:]:
        offset += len(line.encode())
        if offset > 65536:
            raise Refusal('permission_refused')
        if line.strip() == '---':
            if integration:
                for key in ('depends_on', 'impacts'):
                    for edge in metadata.get(key, []):
                        if type(edge) is not dict or set(edge) != {'target', 'why'}:
                            raise Refusal('permission_refused')
            return metadata, offset
        if not line.strip() or line.startswith('#'):
            continue
        if line.startswith((' ', '\t')):
            if integration and list_key in ('depends_on', 'impacts'):
                target = re.fullmatch(r'  - target: (.+)\r?\n?', line)
                reason = re.fullmatch(r'    why: (.+)\r?\n?', line)
                if target:
                    value = target[1].strip()
                    if value.startswith('[[') and value.endswith(']]') and re.fullmatch(r'\[\[[a-zA-Z0-9_ /.-]+\]\]', value):
                        value = value[2:-2]
                    else:
                        value = scalar(value)
                    metadata[list_key].append({'target': value})
                elif reason and metadata[list_key] and 'why' not in metadata[list_key][-1]:
                    metadata[list_key][-1]['why'] = scalar(reason[1])
                else:
                    raise Refusal('permission_refused')
                continue
            match = re.fullmatch(r'  - (.+)\r?\n?', line)
            if list_key is None or not match:
                raise Refusal('permission_refused')
            metadata[list_key].append(scalar(match[1]))
            continue
        match = re.fullmatch(r'([a-z][a-z0-9_-]*):[^\S\r\n]*(.*?)\r?\n?', line)
        if not match or match[1] not in KEYS or match[1].replace('-', '_') in {k.replace('-', '_') for k in metadata}:
            raise Refusal('permission_refused')
        key, value = match[1], match[2]
        if integration and key not in {'project', 'depends_on', 'impacts'}:
            raise Refusal('permission_refused')
        list_key = key if key in LIST_KEYS and not value else None
        if key in LIST_KEYS:
            # Wikilink list syntax is allowed only in omitted provenance metadata.
            if key == 'related' and value.startswith('[[') and value.endswith(']]'):
                metadata[key] = [value]
            else:
                metadata[key] = inline_list(value) if value else []
        else:
            metadata[key] = scalar(value)
    raise Refusal('permission_refused')


def heading(line, fence):
    match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)', line)
    if match:
        mark = match[1]
        if fence is None:
            return None, (mark[0], len(mark))
        if mark[0] == fence[0] and len(mark) >= fence[1] and not match[2].strip():
            return None, None
        return None, fence
    if fence:
        return None, fence
    match = re.match(r'^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*\r?\n?$', line)
    return ((len(match[1]), match[2]) if match else None), fence


def project(locator, raw, policy):
    if not policy.permits(locator):
        raise Refusal('permission_refused')
    integration = locator in policy.portfolio
    meta, offset = frontmatter(raw, integration=integration)
    if integration:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', meta.get('project', '')):
            raise Refusal('permission_refused')
        meta['title'] = 'Integration: ' + meta['project']
    elif not isinstance(meta.get('title'), str) or not meta['title'].strip() or not meta.get('created'):
        raise Refusal('permission_refused')
    if meta.get('sensitivity', 'published').lower() not in ('published', 'public', 'ordinary'):
        raise Refusal('permission_refused')
    if meta.get('status', '').lower() not in PUBLISHED_STATUSES or ('type' in meta and meta['type'].lower() not in PUBLISHED_TYPES):
        raise Refusal('permission_refused')
    for key, value in meta.items():
        if key not in OMIT_KEYS and UNSAFE.search(str(value)):
            raise Refusal('permission_refused')
        if key in {'created', 'updated', 'occurred', 'resolved'} and value:
            try:
                if datetime.date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except ValueError:
                raise Refusal('permission_refused') from None
    metadata = {key.replace('-', '_'): meta[key] for key in ('title', 'aliases', 'tags',
        'created', 'updated', 'status', 'language', 'evidence-status', 'verification-status',
        'evidence_status', 'verification_status', 'occurred', 'resolved', 'source-period') if key in meta}
    metadata.setdefault('aliases', []); metadata.setdefault('tags', [])
    metadata['category'] = locator.split('/')[0]
    metadata['date_basis'] = 'frontmatter; created/updated are page lifecycle dates'
    body = []; mapping = []; omissions = [{'kind': 'frontmatter', 'source_start': 0, 'source_end': offset}]
    fence = None; omitted_level = None; projection_offset = 0
    for line in lines(raw[offset:].decode('utf-8')):
        data = line.encode(); head, fence = heading(line, fence)
        if head:
            if omitted_level is not None and head[0] <= omitted_level:
                omitted_level = None
            if head[1].strip().lower() in PROVENANCE:
                omitted_level = head[0]
        if omitted_level is not None:
            if omissions[-1]['kind'] == 'provenance' and omissions[-1]['source_end'] == offset:
                omissions[-1]['source_end'] += len(data)
            else:
                omissions.append({'kind': 'provenance', 'source_start': offset, 'source_end': offset+len(data)})
        else:
            if UNSAFE.search(line):
                raise Refusal('permission_refused')
            body.append(line)
            if mapping and mapping[-1]['source_end'] == offset:
                mapping[-1]['source_end'] += len(data); mapping[-1]['end'] += len(data)
            else:
                mapping.append({'start': projection_offset, 'end': projection_offset+len(data),
                    'source_start': offset, 'source_end': offset+len(data)})
            projection_offset += len(data)
        offset += len(data)
    projection = ''.join(body)
    return {'locator': locator, 'metadata': metadata, 'body': projection,
        'mapping': mapping, 'omissions': omissions,
        'source_hash': digest(raw), 'projection_hash': digest(projection.encode())}
