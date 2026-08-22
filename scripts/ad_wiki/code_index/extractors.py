from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from ..core import ADWikiError
from .security import read_text_source


class Extractor(Protocol):
    name: str
    version: str

    def supports(self, path: Path) -> bool: ...

    def extract(self, path: Path, *, root: Path, content: bytes) -> dict: ...


def _providers() -> tuple[Extractor, ...]:
    from .java import JAVA_EXTRACTOR
    from .maven_xml import MAVEN_XML_EXTRACTOR
    from .properties import PROPERTIES_EXTRACTOR

    return (JAVA_EXTRACTOR, MAVEN_XML_EXTRACTOR, PROPERTIES_EXTRACTOR)


def provider_for(path: Path) -> Extractor | None:
    return next((item for item in _providers() if item.supports(path)), None)


def extract_file(path: str | Path, *, root: str | Path) -> dict:
    root_path = Path(root).expanduser().resolve()
    path_value = Path(path).expanduser()
    resolved = path_value.resolve() if path_value.is_absolute() else (root_path / path_value).resolve()
    content = read_text_source(root_path, resolved)
    provider = provider_for(resolved)
    if provider is None:
        raise ADWikiError(f"no structural extractor supports: {resolved.relative_to(root_path).as_posix()}")
    fragment = provider.extract(resolved, root=root_path, content=content)
    fragment["source"]["sha256"] = hashlib.sha256(content).hexdigest()
    fragment["source"]["bytes"] = len(content)
    return fragment
