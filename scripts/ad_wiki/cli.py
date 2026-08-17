from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

from .core import (
    ADWikiError,
    ALLOWED_OPERATIONS,
    ALLOWED_RISKS,
    ALLOWED_STATES,
    build_indexes,
    guard_raw,
    initialize_repository,
    register_source,
    validate_repository,
    write_run_report,
)
from .doctor import inspect_plugin
from .runtime import (
    apply_run,
    approve_run,
    build_query_context,
    migrate_repository,
    prepare_run,
    query_registered_raw,
    review_run,
    search_repository,
)


Runner = Callable[[argparse.Namespace], tuple[dict[str, Any], int]]


def _base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--repo", default=".", help="AD-Wiki repository root (default: current directory)")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    return parser


def _render(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if payload.get("status") == "error":
        print(f"error: {payload['error']}", file=sys.stderr)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _execute(parser: argparse.ArgumentParser, runner: Runner, argv: Sequence[str] | None) -> int:
    args = parser.parse_args(argv)
    try:
        payload, exit_code = runner(args)
    except (ADWikiError, OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {"error": str(exc), "status": "error"}
        exit_code = 2
    _render(payload, args.json)
    return exit_code


def init_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Initialize an independent AD-Wiki knowledge repository.")
    parser.add_argument("--domain", default="general", help="domain name stored in ad-wiki.yaml")
    parser.add_argument(
        "--language",
        default="zh-CN",
        choices=["zh-CN", "en"],
        help="generated Wiki content language (default: zh-CN)",
    )
    parser.add_argument(
        "--owner",
        action="append",
        default=[],
        dest="owners",
        help="high-risk human approver as human:<id>; repeat as needed",
    )
    return _execute(
        parser,
        lambda args: (
            initialize_repository(
                args.repo,
                args.domain,
                content_language=args.language,
                owners=args.owners,
            ),
            0,
        ),
        argv,
    )


def register_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Register an immutable Raw source idempotently.")
    parser.add_argument("--source", required=True, help="source file inside raw/")
    parser.add_argument("--canonical-locator", required=True, help="stable URL, URN, or other canonical locator")
    parser.add_argument("--author", help="optional OKF actor string for the source author")
    return _execute(
        parser,
        lambda args: (
            register_source(args.repo, args.source, args.canonical_locator, args.author),
            0,
        ),
        argv,
    )


def validate_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Validate OKF structure and the AD-Wiki profile.")
    parser.add_argument("--today", help="override current date as YYYY-MM-DD for deterministic checks")

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        current = date.fromisoformat(args.today) if args.today else None
        payload = validate_repository(args.repo, current)
        return payload, 0 if payload["ok"] else 1

    return _execute(parser, runner, argv)


def index_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Build deterministic OKF index.md files.")
    return _execute(parser, lambda args: (build_indexes(args.repo), 0), argv)


def guard_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Verify registered Raw source bytes have not changed.")

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        payload = guard_raw(args.repo)
        return payload, 0 if payload["ok"] else 1

    return _execute(parser, runner, argv)


def report_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Create or advance an AD-Wiki operation report.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--operation", required=True, choices=sorted(ALLOWED_OPERATIONS))
    parser.add_argument("--state", required=True, choices=sorted(ALLOWED_STATES))
    parser.add_argument("--risk", required=True, choices=sorted(ALLOWED_RISKS))
    parser.add_argument("--input", action="append", default=[], dest="inputs")
    parser.add_argument("--read", action="append", default=[], dest="read_set")
    parser.add_argument("--write", action="append", default=[], dest="write_set")
    parser.add_argument(
        "--validation-json",
        action="append",
        default=[],
        help="JSON object describing one validation result; repeat as needed",
    )

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        validations: list[dict[str, Any]] = []
        for raw in args.validation_json:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ADWikiError("each --validation-json value must be a JSON object")
            validations.append(value)
        payload = write_run_report(
            args.repo,
            run_id=args.run_id,
            operation=args.operation,
            state=args.state,
            risk=args.risk,
            inputs=args.inputs,
            read_set=args.read_set,
            write_set=args.write_set,
            validations=validations,
        )
        return payload, 0

    return _execute(parser, runner, argv)


def prepare_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Prepare a baseline-bound staged AD-Wiki write transaction.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--operation", required=True, choices=["ingest", "writeback", "lint", "migrate"])
    parser.add_argument("--risk", required=True, choices=["low", "medium", "high"])
    parser.add_argument("--input", action="append", default=[], dest="inputs")
    parser.add_argument("--read", action="append", default=[], dest="read_set")
    parser.add_argument("--write", action="append", required=True, dest="write_set")
    return _execute(
        parser,
        lambda args: (
            prepare_run(
                args.repo,
                run_id=args.run_id,
                operation=args.operation,
                risk=args.risk,
                inputs=args.inputs,
                read_set=args.read_set,
                write_set=args.write_set,
            ),
            0,
        ),
        argv,
    )


def approve_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Approve a complete staged AD-Wiki transaction.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--by", dest="actor", help="real approval actor; required for medium/high risk")
    return _execute(
        parser,
        lambda args: (approve_run(args.repo, run_id=args.run_id, actor=args.actor), 0),
        argv,
    )


def apply_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Apply, index, log, validate, and finalize an approved staged transaction.")
    parser.add_argument("--run-id", required=True)
    return _execute(parser, lambda args: (apply_run(args.repo, run_id=args.run_id), 0), argv)


def review_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Record a real review of a validated AD-Wiki transaction.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--by", required=True, dest="actor")
    parser.add_argument("--decision", required=True, choices=["approved", "rejected"])
    parser.add_argument("--note")
    return _execute(
        parser,
        lambda args: (
            review_run(
                args.repo,
                run_id=args.run_id,
                actor=args.actor,
                decision=args.decision,
                note=args.note,
            ),
            0,
        ),
        argv,
    )


def search_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Discover lightweight candidate pages in the current AD-Wiki Bundle.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=12)
    return _execute(
        parser,
        lambda args: (search_repository(args.repo, query=args.query, limit=args.limit), 0),
        argv,
    )


def query_context_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Hydrate full Markdown for explicitly selected AD-Wiki Concepts.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--concept", action="append", required=True, dest="concept_ids")
    parser.add_argument("--max-chars", type=int, default=30_000)
    return _execute(
        parser,
        lambda args: (
            build_query_context(
                args.repo,
                query=args.query,
                concept_ids=args.concept_ids,
                max_chars=args.max_chars,
            ),
            0,
        ),
        argv,
    )


def raw_fallback_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Build a bounded Raw fallback context from selected Concept provenance.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--concept", action="append", required=True, dest="concept_ids")
    parser.add_argument("--max-sources", type=int, default=2)
    parser.add_argument("--max-chars", type=int, default=6_000)
    return _execute(
        parser,
        lambda args: (
            query_registered_raw(
                args.repo,
                query=args.query,
                concept_ids=args.concept_ids,
                max_sources=args.max_sources,
                max_chars=args.max_chars,
            ),
            0,
        ),
        argv,
    )


def migrate_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Inspect or run a supported deterministic AD-Wiki Profile migration.")
    parser.add_argument("--target-profile", default="0.1")
    return _execute(
        parser,
        lambda args: (migrate_repository(args.repo, target_profile=args.target_profile), 0),
        argv,
    )


def doctor_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the local AD-Wiki Plugin package and optional Wiki.")
    parser.add_argument(
        "--plugin-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="AD-Wiki Plugin root (default: packaged root)",
    )
    parser.add_argument("--repo", help="optional initialized AD-Wiki repository to validate")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    args = parser.parse_args(argv)
    try:
        payload = inspect_plugin(args.plugin_root, repo=args.repo)
        exit_code = 0 if payload["ready"] else 1
    except (ADWikiError, OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {"error": str(exc), "status": "error"}
        exit_code = 2
    _render(payload, args.json)
    return exit_code
