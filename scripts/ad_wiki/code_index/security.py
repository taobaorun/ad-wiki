from __future__ import annotations

from pathlib import Path

from ..core import ADWikiError


DEFAULT_MAX_SOURCE_BYTES = 2 * 1024 * 1024
DENIED_PARTS = {".git", "build", "dist", "node_modules", "target", "vendor"}
DENIED_NAMES = {".env", "id_dsa", "id_ed25519", "id_rsa"}
DENIED_SUFFIXES = {".der", ".jks", ".key", ".p12", ".pfx", ".pem"}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def read_text_source(
    root: str | Path,
    source: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> bytes:
    root_path = Path(root).expanduser().resolve()
    unresolved = Path(source).expanduser()
    candidate = unresolved if unresolved.is_absolute() else root_path / unresolved
    if candidate.is_symlink():
        raise ADWikiError("source path must not use a symlink")
    resolved = candidate.resolve()
    if not _inside(resolved, root_path):
        raise ADWikiError("source path resolves outside code repository")
    relative = resolved.relative_to(root_path)
    if (
        any(part in DENIED_PARTS for part in relative.parts)
        or relative.name in DENIED_NAMES
        or relative.suffix.lower() in DENIED_SUFFIXES
    ):
        raise ADWikiError("source path is generated, vendored, or sensitive")
    if not resolved.is_file():
        raise ADWikiError("source path must be a regular file")
    size = resolved.stat().st_size
    if size > max_bytes:
        raise ADWikiError(f"source file size {size} exceeds limit {max_bytes}")
    raw = resolved.read_bytes()
    if b"\x00" in raw:
        raise ADWikiError("source file appears binary")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ADWikiError("source file must be UTF-8 text") from exc
    if any(ord(char) < 32 and char not in "\t\n\r" for char in text):
        raise ADWikiError("source file contains unsupported control characters")
    return raw
