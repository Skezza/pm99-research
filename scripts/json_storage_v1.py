"""Opt-in inline Zstandard storage for immutable research JSON.

A logical ``name.json`` has exactly one physical representation: that file or
``name.json.zst``. Hashes always describe the original bytes. This module does
not change Path, builtins, game inventories, or the JSON's canonical encoding.
Only migrate inactive files whose consumers have been audited.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # Plain readers remain usable outside the POSIX pilot.
    fcntl = None

MAX_DECODED_BYTES = 512 * 1024**2
CHUNK = 1024**2
AUTO_MIN_BYTES = 1024**2


class StorageError(OSError):
    """A compressed representation is unsafe, ambiguous, or corrupt."""


def logical_path(path: Path) -> Path:
    path = Path(path).expanduser()
    return path.with_suffix("") if path.name.endswith(".json.zst") else path


def compressed_path(path: Path) -> Path:
    path = logical_path(path)
    if path.suffix != ".json":
        raise StorageError("compression is restricted to .json inputs")
    return path.with_name(path.name + ".zst")


def _present(path: Path) -> bool:
    return os.path.lexists(path)


def physical_path(path: Path) -> Path:
    path = logical_path(path)
    if path.suffix != ".json":
        return path
    packed = compressed_path(path)
    plain_exists, packed_exists = _present(path), _present(packed)
    if plain_exists and packed_exists:
        raise StorageError(f"ambiguous JSON representations: {path} and {packed}")
    selected = path if plain_exists else packed
    if not plain_exists and not packed_exists:
        raise FileNotFoundError(str(path))
    if selected.is_symlink() or not selected.is_file():
        raise StorageError(f"expected a regular JSON file: {selected}")
    return selected


def is_file(path: Path) -> bool:
    try:
        return physical_path(path).is_file()
    except FileNotFoundError:
        return False


def _decoded_chunks(path: Path) -> Iterator[bytes]:
    # A temporary stderr file avoids a deadlock on a full stderr pipe.
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(
                ["zstd", "-q", "-d", "-c", "--", str(path)],
                stdout=subprocess.PIPE, stderr=errors,
            )
        except FileNotFoundError as exc:
            raise StorageError("zstd executable is required to read compressed JSON") from exc
        try:
            assert process.stdout is not None
            total = 0
            while block := process.stdout.read(CHUNK):
                total += len(block)
                if total > MAX_DECODED_BYTES:
                    raise StorageError(f"decoded JSON exceeds {MAX_DECODED_BYTES} bytes")
                yield block
            if process.wait() != 0:
                errors.seek(0)
                raise StorageError(f"cannot decompress {path}: {errors.read(4096).decode(errors='replace')}")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()


@contextmanager
def _directory_lock(path: Path, *, exclusive: bool):
    """Serialize cooperating readers/writers without creating lock files."""
    if fcntl is None:
        yield
        return
    descriptor = os.open(logical_path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        os.close(descriptor)


def _chunks_unlocked(path: Path) -> Iterator[bytes]:
    selected = physical_path(path)
    if selected.name.endswith(".json.zst"):
        yield from _decoded_chunks(selected)
    else:
        with selected.open("rb") as handle:
            while block := handle.read(CHUNK):
                yield block


def chunks(path: Path) -> Iterator[bytes]:
    with _directory_lock(path, exclusive=False):
        yield from _chunks_unlocked(path)


def read_bytes(path: Path) -> bytes:
    return b"".join(chunks(path))


def read_json(path: Path):
    return json.loads(read_bytes(path).decode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    for block in chunks(path):
        digest.update(block)
    return digest.hexdigest()


def size(path: Path) -> int:
    with _directory_lock(path, exclusive=False):
        selected = physical_path(path)
        if not selected.name.endswith(".json.zst"):
            return selected.stat().st_size
        s = selected.stat()
        return _decoded_size(str(selected), (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns))


@lru_cache(maxsize=256)
def _decoded_size(path: str, identity: tuple) -> int:
    return sum(len(block) for block in _decoded_chunks(Path(path)))


def iter_json_paths(directory: Path, pattern: str = "*.json", *, recursive: bool = False) -> Iterator[Path]:
    """Return logical paths once, including compressed files, without recursion."""
    if not pattern.endswith(".json"):
        raise ValueError("JSON discovery pattern must end in .json")
    try:
        from . import json_storage_io_v1 as adapter
    except ImportError:
        import json_storage_io_v1 as adapter
    for path in adapter.glob(Path(directory),pattern,recursive=recursive):
        if path.is_dir() or path.is_symlink():
            continue
        if adapter.is_file(path):
            yield path


def _snapshot(path: Path):
    s = path.lstat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _stage(path: Path, data: bytes, *, compressed: bool, mode: int) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".json-storage-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            if compressed:
                if len(data) > MAX_DECODED_BYTES:
                    raise StorageError("JSON exceeds the compressed reader's size limit")
                try:
                    result = subprocess.run(["zstd", "-1", "-q", "-c"], input=data,
                                            stdout=handle, stderr=subprocess.PIPE, check=False)
                except FileNotFoundError as exc:
                    raise StorageError("zstd executable is required to compress JSON") from exc
                if result.returncode:
                    raise StorageError(result.stderr.decode(errors="replace"))
            else:
                handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        if compressed:
            digest = hashlib.sha256()
            for block in _decoded_chunks(temporary):
                digest.update(block)
            if digest.hexdigest() != hashlib.sha256(data).hexdigest():
                raise StorageError("compressed JSON failed byte-hash verification")
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_bytes(path: Path, data: bytes, *, compressed: bool | str | None = None,
                 overwrite: bool = False) -> Path:
    """Write JSON atomically; default to plain, preserving an existing format.

    ``overwrite=False`` is race-safe and never overwrites existing evidence.
    Conversion between existing representations uses compress_file/restore_file.
    """
    path = logical_path(path)
    packed = compressed_path(path)
    json.loads(data.decode("utf-8"))
    existing = physical_path(path) if _present(path) or _present(packed) else None
    if existing is not None and not overwrite:
        raise FileExistsError(str(path))
    was_compressed = existing == packed
    if was_compressed and overwrite and existing.stat().st_nlink > 1:
        raise StorageError("shared compressed evidence is immutable; write a new logical artifact")
    automatic = compressed == "auto"
    if automatic:
        compressed = was_compressed if existing else len(data) >= AUTO_MIN_BYTES
    elif compressed is not None and type(compressed) is not bool:
        raise ValueError("compressed must be True, False, None or 'auto'")
    if compressed is None:
        compressed = was_compressed
    if compressed and fcntl is None:
        raise StorageError("compressed writes require POSIX directory locking in this pilot")
    if existing is not None and compressed != was_compressed:
        raise StorageError("use explicit migration to change an existing representation")
    destination = packed if compressed else path
    mode = stat.S_IMODE(existing.stat().st_mode) if existing else 0o644
    temporary = _stage(destination, data, compressed=compressed, mode=mode)
    try:
        if automatic and compressed and existing is None and temporary.stat().st_size > len(data) * .9:
            temporary.unlink()
            compressed = False
            destination = path
            temporary = _stage(destination, data, compressed=False, mode=mode)
        if overwrite and existing is not None:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)  # no-clobber publication
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def write_bytes(path: Path, data: bytes, *, compressed: bool | str | None = None,
                overwrite: bool = False) -> Path:
    """Atomically write JSON, preserving its format and no-clobber contract."""
    with _directory_lock(path, exclusive=True):
        return _write_bytes(path, data, compressed=compressed, overwrite=overwrite)


def _convert_locked(path: Path, *, compress: bool, expected_sha256: str | None = None) -> dict:
    if fcntl is None:
        raise StorageError("migration requires POSIX directory locking in this pilot")
    path = logical_path(path)
    packed = compressed_path(path)
    source = physical_path(path)
    expected = path if compress else packed
    if source != expected:
        raise StorageError(f"unexpected representation for conversion: {source}")
    before = source.stat()
    if before.st_nlink != 1:
        raise StorageError("migration refuses shared inodes; audit all aliases first")
    if before.st_uid != os.geteuid():
        raise StorageError("migration requires a file owned by the current user")
    if compress and before.st_size > MAX_DECODED_BYTES:
        raise StorageError("JSON exceeds the compressed reader's size limit")
    snapshot = _snapshot(source)
    data = b"".join(_chunks_unlocked(path))
    if expected_sha256 is not None and hashlib.sha256(data).hexdigest() != expected_sha256:
        raise StorageError("source no longer matches the manifest's original byte hash")
    json.loads(data.decode("utf-8"))
    destination = packed if compress else path
    temporary = _stage(destination, data, compressed=compress,
                       mode=stat.S_IMODE(before.st_mode))
    published = False
    try:
        if temporary.stat().st_gid != before.st_gid:
            os.chown(temporary, -1, before.st_gid)
        os.utime(temporary, ns=(before.st_atime_ns, before.st_mtime_ns))
        if _snapshot(source) != snapshot:
            raise StorageError("source changed during conversion")
        if compress and temporary.stat().st_blocks >= before.st_blocks:
            raise StorageError("compression would not release allocated space")
        os.link(temporary, destination)
        published = True
        _fsync_directory(path.parent)
        if _snapshot(source) != snapshot:
            raise StorageError("source changed before retirement")
        source.unlink()
        _fsync_directory(path.parent)
    except BaseException:
        # Retain the source on failure; remove only our own published inode.
        if published and source.exists() and destination.exists():
            if os.path.samefile(temporary, destination):
                destination.unlink()
        raise
    finally:
        temporary.unlink(missing_ok=True)
    after = destination.stat()
    return {"path": str(path), "physical_path": str(destination),
            "sha256": hashlib.sha256(data).hexdigest(), "logical_bytes": len(data),
            "allocated_before": before.st_blocks * 512,
            "allocated_after": after.st_blocks * 512,
            "allocated_released": (before.st_blocks - after.st_blocks) * 512}


def compress_file(path: Path, *, expected_sha256: str | None = None) -> dict:
    """Convert one audited inactive, unshared JSON file; verify before removal."""
    with _directory_lock(path, exclusive=True):
        return _convert_locked(path, compress=True, expected_sha256=expected_sha256)


def restore_file(path: Path, *, expected_sha256: str | None = None) -> dict:
    """Restore exact original bytes and permissions at the original JSON path."""
    with _directory_lock(path, exclusive=True):
        return _convert_locked(path, compress=False, expected_sha256=expected_sha256)


def read_prefix(path: Path, limit: int = 128 * 1024, *, tail: bool = False) -> bytes:
    """Bound memory for display snippets; this is not a complete integrity proof."""
    if limit < 0 or limit > CHUNK:
        raise ValueError("prefix limit must be between zero and one MiB")
    result = b""
    with _directory_lock(path, exclusive=False):
        iterator = _chunks_unlocked(path)
        try:
            for block in iterator:
                if tail:
                    result = (result + block)[-limit:] if limit else b""
                else:
                    result += block[:max(0, limit - len(result))]
                    if len(result) >= limit:
                        break
        finally:
            iterator.close()
    return result


def copy_json(source: Path, destination: Path, *, compressed: bool | None = None) -> Path:
    if compressed is None:
        compressed = physical_path(source).name.endswith(".json.zst")
    return write_bytes(destination, read_bytes(source), compressed=compressed)
