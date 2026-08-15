from __future__ import annotations

import argparse
import json
import sys
from datetime import date
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
    return _execute(parser, lambda args: (initialize_repository(args.repo, args.domain), 0), argv)


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
