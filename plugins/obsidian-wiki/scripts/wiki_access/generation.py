"""Local durable publication, pinned readers and complete source revalidation.

Source scans describe observations on this host, not an instantaneous NFS snapshot.
Only the local derived store is writable; no source maintenance lock is acquired.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import secrets

from . import policy as source_policy
from .contracts import Refusal, STORE_BYTES, decode, encode, strict_object

VERSION = 'generation.v1'
LOCAL_FILESYSTEMS = {'ext2', 'ext3', 'ext4', 'xfs', 'btrfs', 'zfs', 'tmpfs', 'ramfs', 'overlay', 'f2fs'}
NAME = re.compile(r'[0-9a-f]{64}')


def filesystem(path):
    """Longest mount prefix from the running kernel; unknown placement refuses."""
    selected = ('', '')
    try:
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            before, after = line.split(' - ', 1)
            mount = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), before.split()[4])
            if (str(path) == mount or str(path).startswith(mount.rstrip('/')+'/')) and len(mount) >= len(selected[0]):
                selected = (mount, after.split()[0])
    except (OSError, ValueError, IndexError):
        raise Refusal('permission_refused') from None
    return selected[1]


@contextmanager
def directory(path):
    """Hold and revalidate every ancestor, including the configured root itself."""
    descriptors = []; edges = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(parent)
        for part in Path(os.path.abspath(path)).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(child); edges.append((parent, part, child)); parent = child
        yield parent
        for parent, part, child in edges:
            live = os.stat(part, dir_fd=parent, follow_symlinks=False); opened = os.fstat(child)
            if not stat.S_ISDIR(live.st_mode) or (live.st_dev, live.st_ino) != (opened.st_dev, opened.st_ino):
                raise Refusal('generation_stale')
    except OSError:
        raise Refusal('source_unavailable') from None
    finally:
        for fd in reversed(descriptors): os.close(fd)


def private_stat(st, *, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != (0o700 if directory else 0o600) or (not directory and st.st_nlink != 1):
        raise Refusal('permission_refused')


def read_private(path, ceiling=STORE_BYTES):
    with directory(path.parent) as parent:
        return read_private_at(parent, path.name, ceiling)


def read_private_at(parent, name, ceiling=STORE_BYTES):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        private_stat(os.fstat(fd)); before = os.fstat(fd)
        if before.st_size > ceiling: raise Refusal('budget_exhausted')
        chunks = []; size = 0
        while True:
            chunk = os.read(fd, min(65536, ceiling+1-size))
            if not chunk: break
            chunks.append(chunk); size += len(chunk)
            if size > ceiling: raise Refusal('budget_exhausted')
        live = os.stat(name, dir_fd=parent, follow_symlinks=False); opened = os.fstat(fd)
        signature = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if signature(before) != signature(opened) or signature(live) != signature(opened):
            raise Refusal('generation_stale')
        return b''.join(chunks)
    finally: os.close(fd)


def write_private_at(parent, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as output:
            output.write(raw); output.flush(); os.fsync(fd)
    finally: os.close(fd)


def sync_directory(path):
    with directory(path) as fd: os.fsync(fd)


@contextmanager
def private_directory_at(parent, name):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        private_stat(os.fstat(fd), directory=True)
        if os.fstat(fd).st_dev != os.fstat(parent).st_dev:
            raise Refusal('permission_refused')
        yield fd
        live = os.stat(name,dir_fd=parent,follow_symlinks=False)
        if not stat.S_ISDIR(live.st_mode) or (live.st_dev,live.st_ino) != (os.fstat(fd).st_dev,os.fstat(fd).st_ino):
            raise Refusal('generation_stale')
    finally: os.close(fd)


def check_lock(parent, fd):
    live = os.stat('refresh.lock',dir_fd=parent,follow_symlinks=False)
    private_stat(live)
    if (live.st_dev, live.st_ino) != (os.fstat(fd).st_dev, os.fstat(fd).st_ino):
        raise Refusal('generation_stale')


def snapshot(root, policy):
    """Observe all potentially admitted names, including denied-record changes."""
    pages = []; inventory = []; names = []; listings = {}
    with directory(root) as root_fd:
        identity = os.fstat(root_fd)
        for category in policy.categories:
            try:
                with directory(root/category) as fd:
                    listings[category] = sorted(name for name in os.listdir(fd) if name.endswith('.md'))
                    names.extend(category+'/'+name for name in listings[category])
            except Refusal:
                # A genuinely absent category is empty; symlinks/unavailable roots refuse.
                if os.path.lexists(root/category): raise
                listings[category] = None
                continue
        names.extend(policy.portfolio)
        for locator in sorted(set(names)):
            if not policy.permits(locator): continue
            raw = source_policy.safe_read(root, locator)
            record = {'locator': locator, 'source_hash': source_policy.digest(raw), 'eligible': False}
            try:
                page = source_policy.project(locator, raw, policy)
            except Refusal as refusal:
                if refusal.code != 'permission_refused': raise
            else:
                record.update(eligible=True, projection_hash=page['projection_hash'])
                pages.append(page)
            inventory.append(record)
        # Catch additions/removals during source reads, including a formerly absent root.
        for category, listing in listings.items():
            if listing is None:
                if os.path.lexists(root/category): raise Refusal('generation_stale')
            else:
                with directory(root/category) as fd:
                    if sorted(name for name in os.listdir(fd) if name.endswith('.md')) != listing:
                        raise Refusal('generation_stale')
    return {'version': VERSION, 'policy_version': source_policy.VERSION,
            'policy_hash': policy.fingerprint, 'source_root': str(root),
            'root_identity': [identity.st_dev, identity.st_ino], 'inventory': inventory}, pages


def identity(snapshot_value):
    # DB bytes are recorded separately so generation identity has no self-hash cycle.
    from .store import SCHEMA, RECIPE
    return source_policy.digest(encode({'snapshot': snapshot_value, 'store_schema': SCHEMA, 'recipe': RECIPE}))


class Manager:
    def __init__(self, source_root, state_root, policy):
        self.root = Path(os.path.abspath(source_root))
        self.state = Path(os.path.abspath(state_root))
        self.policy = policy

    def placement(self, *, create=False):
        if self.state == self.root or self.state.is_relative_to(self.root):
            raise Refusal('permission_refused')
        if filesystem(self.state) not in LOCAL_FILESYSTEMS: raise Refusal('permission_refused')
        with directory(self.root): pass
        if create:
            # Existing parent directories retain their permissions; each new directory
            # is private from mkdir, before a manifest or index can be written.
            chain = []; path = self.state
            while not os.path.lexists(path): chain.append(path); path = path.parent
            with directory(path): pass
            for path in reversed(chain):
                with directory(path.parent) as parent:
                    try: os.mkdir(path.name, mode=0o700, dir_fd=parent)
                    except FileExistsError: pass
                with directory(path) as fd: private_stat(os.fstat(fd), directory=True)
        with directory(self.state) as fd: private_stat(os.fstat(fd), directory=True)
        generations = self.state/'generations'
        if filesystem(generations) not in LOCAL_FILESYSTEMS: raise Refusal('permission_refused')
        if create:
            with directory(self.state) as parent:
                try: os.mkdir('generations', mode=0o700, dir_fd=parent)
                except FileExistsError: pass
        with directory(self.state) as parent, private_directory_at(parent, 'generations'):
            pass

    @contextmanager
    def lock(self, *, exclusive=False, create=False):
        self.placement(create=create)
        with directory(self.state) as parent:
            fd = os.open('refresh.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if create else 0), 0o600, dir_fd=parent)
            try:
                private_stat(os.fstat(fd))
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                check_lock(parent, fd)
                yield parent, fd
                check_lock(parent, fd)
            finally: os.close(fd)

    def pointer(self):
        with directory(self.state) as parent:
            return self.pointer_at(parent)

    def pointer_at(self, parent):
        value = decode(read_private_at(parent, 'current.json', 1024))
        if (type(value) is not dict or set(value) != {'generation', 'manifest_hash'}
                or any(type(v) is not str or not NAME.fullmatch(v) for v in value.values())):
            raise Refusal('index_unavailable')
        return value

    def manifest(self, path, pointer=None):
        with directory(path) as fd:
            return self.manifest_at(fd, pointer)

    def manifest_at(self, fd, pointer=None):
        raw = read_private_at(fd, 'manifest.json', 8 * 1024 * 1024)
        try:
            manifest = json.loads(raw, object_pairs_hook=strict_object,
                parse_constant=lambda _: (_ for _ in ()).throw(Refusal('index_unavailable')))
        except (ValueError, UnicodeError, RecursionError):
            raise Refusal('index_unavailable') from None
        if (type(manifest) is not dict or set(manifest) != {'schema','generation','snapshot','database_hash'}
                or manifest['schema'] != VERSION or type(manifest['snapshot']) is not dict
                or type(manifest['generation']) is not str or not NAME.fullmatch(manifest['generation'])
                or type(manifest['database_hash']) is not str or not NAME.fullmatch(manifest['database_hash'])
                or identity(manifest['snapshot']) != manifest['generation']):
            raise Refusal('index_unavailable')
        if pointer and (manifest['generation'] != pointer['generation'] or source_policy.digest(raw) != pointer['manifest_hash']):
            raise Refusal('index_unavailable')
        return manifest

    def storage_size(self, parent=None):
        if parent is None:
            with directory(self.state) as fd: return self.storage_size(fd)
        def count(fd, depth=0):
            if depth > 3: raise Refusal('permission_refused')
            size = 0
            for name in os.listdir(fd):
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(st.st_mode):
                    with private_directory_at(fd, name) as child: size += count(child, depth+1)
                else:
                    private_stat(st); size += st.st_size
                if size > STORE_BYTES: raise Refusal('budget_exhausted')
            return size
        size = count(parent)
        if size > STORE_BYTES: raise Refusal('budget_exhausted')
        return size

    def reclaim(self, parent, active):
        """Only recognize our sealed generations or disposable private staging paths."""
        for name in sorted(os.listdir(parent)):
            if name == active: continue
            if not NAME.fullmatch(name) and not re.fullmatch(r'staging-[a-z0-9_]+', name):
                raise Refusal('index_unavailable')
            with private_directory_at(parent, name) as fd:
                try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: continue
                names = os.listdir(fd)
                if set(names) - {'manifest.json', 'index.sqlite'}: raise Refusal('permission_refused')
                if NAME.fullmatch(name):
                    manifest = self.manifest_at(fd)
                    if manifest['generation'] != name: raise Refusal('index_unavailable')
                for file_name in names: private_stat(os.stat(file_name, dir_fd=fd, follow_symlinks=False))
                for file_name in names: os.unlink(file_name, dir_fd=fd)
            os.rmdir(name, dir_fd=parent)
        os.fsync(parent)

    def refresh(self):
        from .store import build
        try:
            with self.lock(exclusive=True, create=True) as (parent, lock_fd), private_directory_at(parent, 'generations') as generations:
                before, pages = snapshot(self.root, self.policy)
                generation = identity(before)
                current = self.pointer_at(parent) if 'current.json' in os.listdir(parent) else None
                self.reclaim(generations, current['generation'] if current else None)
                self.storage_size(parent)
                if generation in os.listdir(generations):
                    with private_directory_at(generations, generation) as fd:
                        manifest = self.manifest_at(fd)
                        if manifest['generation'] != generation or source_policy.digest(read_private_at(fd,'index.sqlite')) != manifest['database_hash']:
                            raise Refusal('index_unavailable')
                else:
                    staging = 'staging-'+secrets.token_hex(8)
                    os.mkdir(staging, mode=0o700, dir_fd=generations)
                    try:
                        with private_directory_at(generations, staging) as staging_fd:
                            manifest = {'schema': VERSION, 'generation': generation,
                                        'snapshot': before, 'database_hash': '0'*64}
                            manifest_size = len(encode(manifest))
                            reserve = manifest_size + len(encode({'generation':generation,'manifest_hash':'0'*64}))
                            available = STORE_BYTES-self.storage_size(parent)-reserve
                            if available < 4096 or manifest_size > 8*1024*1024:
                                raise Refusal('budget_exhausted')
                            build(Path('/proc/self/fd')/str(staging_fd)/'index.sqlite', pages, generation, byte_budget=available)
                            manifest['database_hash'] = source_policy.digest(read_private_at(staging_fd,'index.sqlite'))
                            db_fd = os.open('index.sqlite',os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,dir_fd=staging_fd)
                            try:
                                private_stat(os.fstat(db_fd)); os.fsync(db_fd)
                            finally: os.close(db_fd)
                            write_private_at(staging_fd, 'manifest.json', encode(manifest))
                            os.fsync(staging_fd)
                    except BaseException:
                        # Only the directory this writer exclusively created is removed.
                        # fd-relative unlinking cannot chase a replaced state path.
                        with private_directory_at(generations,staging) as staging_fd:
                            for name in os.listdir(staging_fd):
                                if name not in {'manifest.json','index.sqlite'}: raise Refusal('permission_refused')
                                private_stat(os.stat(name,dir_fd=staging_fd,follow_symlinks=False))
                                os.unlink(name,dir_fd=staging_fd)
                        os.rmdir(staging,dir_fd=generations); os.fsync(generations)
                        raise
                    self.storage_size(parent)
                    after, _ = snapshot(self.root, self.policy)
                    if before != after: raise Refusal('generation_stale')
                    os.replace(staging, generation, src_dir_fd=generations, dst_dir_fd=generations)
                    os.fsync(generations)
                after, _ = snapshot(self.root, self.policy)
                if before != after: raise Refusal('generation_stale')
                check_lock(parent, lock_fd)
                pointer = {'generation': generation, 'manifest_hash': source_policy.digest(encode(manifest))}
                temp = 'pointer-'+generation+'.tmp'
                # A previous interrupted pointer can contain only operational hashes.
                if temp in os.listdir(parent):
                    private_stat(os.stat(temp,dir_fd=parent,follow_symlinks=False)); os.unlink(temp,dir_fd=parent)
                write_private_at(parent, temp, encode(pointer)); self.storage_size(parent)
                os.replace(temp, 'current.json', src_dir_fd=parent, dst_dir_fd=parent); os.fsync(parent)
                self.reclaim(generations, generation)
                return {'generation': generation, 'pages': len(pages)}
        except OSError:
            raise Refusal('index_unavailable') from None

    @contextmanager
    def pin(self):
        pin = None
        try:
            with self.lock() as (parent, _):
                pointer = self.pointer_at(parent)
                with private_directory_at(parent,'generations') as generations, private_directory_at(generations,pointer['generation']) as child:
                    dir_fd = os.dup(child); fcntl.flock(dir_fd, fcntl.LOCK_SH)
                db_fd = None
                try:
                    manifest = self.manifest_at(dir_fd, pointer)
                    db_fd = os.open('index.sqlite', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
                    private_stat(os.fstat(db_fd))
                except BaseException:
                    if db_fd is not None: os.close(db_fd)
                    os.close(dir_fd); raise
                pin = Pinned(self, pointer, manifest, dir_fd, db_fd)
            pin.check()
            yield pin
        except OSError:
            raise Refusal('index_unavailable') from None
        finally:
            if pin is not None: pin.close()


class Pinned:
    def __init__(self, manager, pointer, manifest, dir_fd, db_fd):
        self.manager = manager; self.pointer = pointer; self.manifest = manifest
        self.dir_fd = dir_fd; self.db_fd = db_fd
        self.generation = pointer['generation']

    @property
    def database_path(self):
        # SQLite opens the pinned inode, never a mutable pathname/symlink replacement.
        return Path('/proc/self/fd')/str(self.db_fd)

    def check(self):
        self.manager.placement()
        if self.manager.pointer() != self.pointer: raise Refusal('generation_stale')
        path = self.manager.state/'generations'/self.generation
        if self.manager.manifest(path, self.pointer) != self.manifest: raise Refusal('index_unavailable')
        with directory(self.manager.state) as parent, private_directory_at(parent,'generations') as generations, private_directory_at(generations,self.generation) as fd:
            if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != (os.fstat(self.dir_fd).st_dev, os.fstat(self.dir_fd).st_ino):
                raise Refusal('generation_stale')
        observed, _ = snapshot(self.manager.root, self.manager.policy)
        if observed != self.manifest['snapshot']: raise Refusal('generation_stale')
        # pread leaves SQLite's file offset independent of hash verification.
        digest = hashlib.sha256(); offset = 0
        while True:
            block = os.pread(self.db_fd, 65536, offset)
            if not block: break
            digest.update(block); offset += len(block)
            if offset > STORE_BYTES: raise Refusal('budget_exhausted')
        if digest.hexdigest() != self.manifest['database_hash']: raise Refusal('index_unavailable')

    def close(self):
        os.close(self.db_fd); os.close(self.dir_fd)
