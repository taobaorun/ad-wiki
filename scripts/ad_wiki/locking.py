from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .core import ADWikiError, _resolve_inside, _utc_now


@contextmanager
def repository_lock(root: Path, owner_id: str) -> Iterator[None]:
    lock_path = _resolve_inside(root, ".ad-wiki/lock", "lock path")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ADWikiError("another AD-Wiki writer holds .ad-wiki/lock") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"acquired_at": _utc_now(), "owner_id": owner_id, "pid": os.getpid()}, handle)
            handle.write("\n")
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
