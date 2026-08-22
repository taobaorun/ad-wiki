from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

from ..core import ADWikiError


NODE_KINDS = {
    "annotation",
    "config-key",
    "constructor",
    "field",
    "file",
    "method",
    "module",
    "package",
    "property",
    "type",
    "unresolved",
}
LANGUAGE = re.compile(r"^[a-z][a-z0-9-]*$")


def normalize_repo_path(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.replace("\\", "/").strip())
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ADWikiError("symbol path must be repository-relative")
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        raise ADWikiError("symbol path must be repository-relative")
    return "/".join(parts)


def stable_symbol_id(language: str, kind: str, path: str, symbol: str | None = None) -> str:
    if not LANGUAGE.fullmatch(language):
        raise ADWikiError("symbol language must be lowercase and stable")
    if kind not in NODE_KINDS:
        raise ADWikiError(f"unsupported symbol kind: {kind}")
    relative = normalize_repo_path(path)
    result = f"{language}:{kind}:{relative}"
    if symbol is not None:
        normalized_symbol = unicodedata.normalize("NFC", symbol).strip()
        if not normalized_symbol:
            raise ADWikiError("symbol name must be non-empty")
        result += f"#{normalized_symbol}"
    return result
