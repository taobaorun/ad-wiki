"""Deterministic helpers for the AD-Wiki plugin."""

from .core import (
    ADWikiError,
    build_indexes,
    guard_raw,
    initialize_repository,
    register_source,
    validate_repository,
    write_run_report,
)
from .runtime import (
    apply_run,
    approve_run,
    migrate_repository,
    prepare_run,
    query_registered_raw,
    review_run,
)
from .doctor import inspect_plugin

__all__ = [
    "ADWikiError",
    "build_indexes",
    "guard_raw",
    "initialize_repository",
    "inspect_plugin",
    "register_source",
    "validate_repository",
    "write_run_report",
    "prepare_run",
    "query_registered_raw",
    "approve_run",
    "apply_run",
    "review_run",
    "migrate_repository",
]
