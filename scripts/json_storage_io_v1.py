"""Path-I/O adapters: logical .json inputs, ordinary behavior for other files.

Explicit .json.zst paths remain physical in this adapter (archive/inventory
callers need container bytes). Use json_storage_v1 for explicit logical I/O.
"""
from __future__ import annotations

import io
import hashlib
import fnmatch
import os
import shutil
from pathlib import Path

try:
    from . import json_storage_v1 as storage
    from .json_storage_policy_v2 import excluded, SKIP_DIRS
except ImportError:
    import json_storage_v1 as storage
    from json_storage_policy_v2 import excluded, SKIP_DIRS

ROOT = Path(__file__).resolve().parents[1]
# Enabled only after the complete consumer audit and regression gate.
AUTO_ROOTS: set[str] = set()
EXCLUDED_PARTS = {'game', 'games', 'wine-prefix', 'node_modules', '.git'}


def _path(value):
    return Path(value) if isinstance(value, (str, bytes, os.PathLike)) and not isinstance(value, bytes) else None


def logical(value):
    path = _path(value)
    return path is not None and path.suffix == '.json'


def _compressed(value):
    return logical(value) and os.path.lexists(storage.compressed_path(Path(value)))


def is_compressed(path):
    return _compressed(path)


def automatic(path):
    path = Path(path).absolute()
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return False
    return (len(rel.parts) > 2 and rel.parts[1] in AUTO_ROOTS and not excluded(rel))


def exists(value):
    if not _compressed(value):
        result = value.exists()
        if result or not _compressed(value):
            return result
    with storage._directory_lock(Path(value), exclusive=False):
        return storage.is_file(Path(value))


def is_file(value):
    if not _compressed(value):
        result = value.is_file()
        if result or not _compressed(value):
            return result
    with storage._directory_lock(Path(value), exclusive=False):
        return storage.is_file(Path(value))


def size(value):
    return storage.size(Path(value)) if _compressed(value) else value.stat().st_size


def stat_result(value, *args, **kwargs):
    if not _compressed(value):
        return value.stat(*args, **kwargs)
    selected = storage.physical_path(Path(value))
    original = selected.stat(*args, **kwargs)
    values = list(original)
    values[6] = storage.size(Path(value))
    return os.stat_result(values, {k: getattr(original, k) for k in dir(original)
                                  if k.startswith('st_') and k != 'st_size'})


def resolve(value, *args, **kwargs):
    if logical(value) and os.path.lexists(storage.compressed_path(Path(value))):
        storage.physical_path(Path(value))  # reject conflicting files and symlinks
        return Path(value).resolve(strict=False)
    return value.resolve(*args, **kwargs)


def unlink(value, *args, **kwargs):
    if _compressed(value):
        try:
            with storage._directory_lock(Path(value), exclusive=True):
                return storage.physical_path(Path(value)).unlink(*args, **kwargs)
        except FileNotFoundError:
            if kwargs.get('missing_ok'):
                return None
            raise
    return value.unlink(*args, **kwargs)


def move(value, target, *args, replace=False, **kwargs):
    if not isinstance(value, os.PathLike):
        return value.replace(target, *args, **kwargs) if replace else value.rename(target, *args, **kwargs)
    if str(target).endswith('.json.zst'):
        raise storage.StorageError('use a logical .json destination for JSON moves')
    if not _compressed(value) and not _compressed(target):
        return value.replace(target) if replace else value.rename(target)
    source = storage.physical_path(Path(value)) if _compressed(value) else Path(value)
    target_physical = storage.physical_path(Path(target)) if logical(target) and storage.is_file(Path(target)) else Path(target)
    if target_physical.exists() and os.path.samefile(source, target_physical):
        return Path(target)
    if source.is_file() and logical(target):
        data = storage.read_bytes(Path(value)) if logical(value) else source.read_bytes()
        selected = None if storage.is_file(Path(target)) else source.name.endswith('.json.zst')
        destination=storage.write_bytes(Path(target), data, compressed=selected, overwrite=True)
        shutil.copystat(source,destination)
        source.unlink()
        return Path(target)
    if logical(value) and source.name.endswith('.json.zst'):
        Path(target).write_bytes(storage.read_bytes(Path(value)))
        source.unlink()
        return Path(target)
    return value.replace(target) if replace else value.rename(target)


def read_bytes(value):
    if _compressed(value):
        return storage.read_bytes(Path(value))
    try:
        return value.read_bytes()
    except FileNotFoundError:
        if _compressed(value):
            return storage.read_bytes(Path(value))
        raise


def prefix(value, limit=128 * 1024, *, tail=False):
    if _compressed(value):
        return storage.read_prefix(Path(value), limit, tail=tail)
    with value.open('rb') as handle:
        if tail:
            handle.seek(max(0, value.stat().st_size - limit))
        return handle.read(limit)


def read_text(value, *args, **kwargs):
    if not _compressed(value):
        try:
            return value.read_text(*args, **kwargs)
        except FileNotFoundError:
            if not _compressed(value):
                raise
    encoding = kwargs.get('encoding', args[0] if args else None)
    errors = kwargs.get('errors', args[1] if len(args) > 1 else None)
    with io.TextIOWrapper(io.BytesIO(storage.read_bytes(Path(value))), encoding=encoding, errors=errors) as handle:
        return handle.read()


def write_bytes(value, data):
    if not logical(value):
        return value.write_bytes(data)
    path = Path(value)
    packed = storage.compressed_path(path)
    if automatic(path) or os.path.lexists(packed):
        storage.write_bytes(path, bytes(data), compressed='auto' if automatic(path) else None, overwrite=True)
        return len(data)
    return value.write_bytes(data)


def write_text(value, data, *args, **kwargs):
    encoding = kwargs.get('encoding', args[0] if args else None)
    errors = kwargs.get('errors', args[1] if len(args) > 1 else None)
    newline = kwargs.get('newline', args[2] if len(args) > 2 else None)
    if logical(value) and (automatic(value) or os.path.lexists(storage.compressed_path(Path(value)))):
        buffer = io.BytesIO()
        handle = io.TextIOWrapper(buffer, encoding=encoding, errors=errors, newline=newline)
        handle.write(data);handle.flush();data_bytes=buffer.getvalue();handle.close()
        write_bytes(value, data_bytes)
        return len(data)
    return value.write_text(data, *args, **kwargs)


def glob(value, pattern, *, recursive=False):
    if isinstance(value, Path) and isinstance(pattern, str) and pattern.endswith('.json'):
        def collect():
            if not value.is_dir():
                return iter(())
            patterns = tuple(Path(pattern).parts)
            if recursive:
                patterns = ('**',) + patterns
            directories = [value]
            if recursive or '/' in pattern:
                directories=[]
                for parent,dirs,files in os.walk(value,followlinks=False):
                    directory=Path(parent);directories.append(directory)
                    depth=len(directory.relative_to(value).parts)
                    if '**' not in patterns:
                        if depth>=len(patterns)-1:dirs[:]=[]
                        else:dirs[:]=[d for d in dirs if fnmatch.fnmatchcase(d,patterns[depth])]
            def matches(parts, pats):
                if not pats:return not parts
                if pats[0]=='**':return matches(parts,pats[1:]) or (bool(parts) and matches(parts[1:],pats))
                return bool(parts) and fnmatch.fnmatchcase(parts[0],pats[0]) and matches(parts[1:],pats[1:])
            result = set()
            for directory in directories:
                try:
                    with storage._directory_lock(directory / 'discovery.json', exclusive=False):
                        for entry in directory.iterdir():
                            logical_entry=storage.logical_path(entry)
                            relative=logical_entry.relative_to(value)
                            if matches(relative.parts,patterns):result.add(logical_entry)
                except PermissionError:
                    continue  # pathlib discovery skips inaccessible directories too
            return iter(sorted(result))
        return collect()
    return value.rglob(pattern) if recursive else value.glob(pattern)


class _WriteBuffer(io.BytesIO):
    def __init__(self, path, mode):
        super().__init__()
        self.path, self.mode, self.abort = path, mode, False

    def close(self):
        if not self.closed:
            try:
                if not self.abort:
                    storage.write_bytes(self.path, self.getvalue(),
                                        compressed='auto' if automatic(self.path) else None,
                                        overwrite='x' not in self.mode)
            finally:
                super().close()

    def __exit__(self, kind, value, traceback):
        self.abort = kind is not None
        self.close()

    def __del__(self):
        self.abort = True
        super().close()


class _WriteText(io.TextIOWrapper):
    def __del__(self):
        # TextIOWrapper's own finalizer closes the binary buffer; mark it aborted
        # first so abandoned text handles cannot publish otherwise-valid prefixes.
        try:
            self.buffer.abort=True
            self.close()
        except Exception:
            pass

    def __exit__(self, kind, value, traceback):
        self.buffer.abort = kind is not None
        return super().__exit__(kind, value, traceback)


def open_file(value, *args, **kwargs):
    if not logical(value):
        return value.open(*args, **kwargs)
    mode = kwargs.get('mode', args[0] if args else 'r')
    path = Path(value)
    packed = _compressed(path)
    if not packed and ('r' in mode or not automatic(path)):
        try:
            return value.open(*args, **kwargs)
        except FileNotFoundError:
            if not _compressed(path):
                raise
    if '+' in mode or 'a' in mode:
        raise storage.StorageError('compressed JSON does not support append/update file handles')
    if 'r' in mode:
        buffer = io.BytesIO(storage.read_bytes(path))
        return buffer if 'b' in mode else io.TextIOWrapper(
            buffer, encoding=kwargs.get('encoding', args[2] if len(args)>2 else None),
            errors=kwargs.get('errors', args[3] if len(args)>3 else None),
            newline=kwargs.get('newline', args[4] if len(args)>4 else None))
    if 'x' in mode and storage.is_file(path):
        raise FileExistsError(str(path))
    buffer = _WriteBuffer(path, mode)
    return buffer if 'b' in mode else _WriteText(
        buffer, encoding=kwargs.get('encoding', args[2] if len(args)>2 else None),
        errors=kwargs.get('errors', args[3] if len(args)>3 else None),
        newline=kwargs.get('newline', args[4] if len(args)>4 else None))


def link(source, target, *args, **kwargs):
    if any(str(p).endswith('.json.zst') for p in (source,target)):
        raise storage.StorageError('use logical .json names for links')
    if logical(source) or logical(target):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for parent in sorted({Path(p).parent for p in (source,target)}):
                stack.enter_context(storage._directory_lock(parent / 'link.json', exclusive=True))
            if logical(target) and (os.path.lexists(target) or os.path.lexists(storage.compressed_path(Path(target)))):
                raise FileExistsError(str(target))
            if _compressed(source) and not logical(target):
                raise storage.StorageError('compressed links require a logical .json destination')
            selected = storage.physical_path(Path(source)) if _compressed(source) else source
            destination = storage.compressed_path(Path(target)) if _compressed(source) and logical(target) else target
            return os.link(selected, destination, *args, **kwargs)
    return os.link(source, target, *args, **kwargs)


def copy_file(source, target, *, metadata=False, **kwargs):
    original_target = target
    if (str(source).endswith('.json.zst') and logical(target)) or (logical(source) and str(target).endswith('.json.zst')):
        raise storage.StorageError('do not mix explicit frame names and logical JSON in copies')
    if _compressed(target) and not logical(source):
        source=Path(source)
        storage.write_bytes(Path(target),source.read_bytes(),overwrite=True)
        if metadata:shutil.copystat(source,storage.physical_path(Path(target)),**kwargs)
        return original_target
    if not _compressed(source) and not _compressed(target):
        return shutil.copy2(source,target,**kwargs) if metadata else shutil.copyfile(source,target,**kwargs)
    if logical(source):
        target = Path(target)
        if target.is_dir():
            target = target / Path(source).name
        if logical(target):
            # copyfile historically permits replacing an existing destination.
            data = storage.read_bytes(Path(source))
            source_physical = storage.physical_path(Path(source))
            existing = storage.is_file(target)
            if existing and os.path.samefile(source_physical, storage.physical_path(target)):
                raise shutil.SameFileError(str(source))
            compressed = None if existing else source_physical.name.endswith('.json.zst')
            destination = storage.write_bytes(target, data, compressed=compressed, overwrite=True)
            if metadata:
                shutil.copystat(storage.physical_path(Path(source)), destination,
                                follow_symlinks=kwargs.get('follow_symlinks', True))
            return original_target
        if _compressed(source):
            target.write_bytes(storage.read_bytes(Path(source)))
            if metadata:shutil.copystat(storage.physical_path(Path(source)),target,**kwargs)
            return original_target
    return shutil.copy2(source, target, **kwargs) if metadata else shutil.copyfile(source, target, **kwargs)


def replace_file(source,target):
    """os.replace equivalent for logical JSON and ordinary physical paths."""
    return move(Path(source),Path(target),replace=True)


def rename_file(source,target):
    return move(Path(source),Path(target))


def physical_path(value):
    """Select the actual stored name for a logical JSON archive input."""
    return storage.physical_path(Path(value)) if logical(value) else Path(value)


def physical_sha256_file(value):
    """Hash explicit filesystem/container bytes; never decode a .json.zst member."""
    with Path(value).open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def assert_plain_reference_scan(roots):
    """Stop a legacy plain-only retirement guard from overlooking stored frames."""
    for root in map(Path,roots):
        for directory,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if name.endswith('.json.zst'):
                    raise storage.StorageError('plain-only reference scan would miss compressed JSON: '+str(Path(directory,name))+'; use decoded storage readers before retiring sources')


def find_json_reference(roots, needle):
    """Find a literal reference in decoded metadata, failing closed on read errors."""
    from contextlib import closing
    encoded=needle.encode('utf8')
    if not encoded:raise ValueError('reference needle must not be empty')
    seen=set()
    for root in map(Path,roots):
        if not root.is_dir():raise FileNotFoundError(str(root))
        def failed(error):raise error
        for directory,dirs,files in os.walk(root,followlinks=False,onerror=failed):
            dirs[:]=[d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if not name.endswith(('.json','.json.zst')):continue
                path=storage.logical_path(Path(directory,name));selected=storage.physical_path(path)
                meta=selected.stat();key=(meta.st_dev,meta.st_ino,meta.st_size,meta.st_mtime_ns,meta.st_ctime_ns)
                if key in seen:continue
                seen.add(key);tail=b''
                with closing(storage.chunks(path)) as blocks:
                    for block in blocks:
                        combined=tail+block
                        if encoded in combined:return path
                        tail=combined[-(len(encoded)-1):] if len(encoded)>1 else b''
    return None
