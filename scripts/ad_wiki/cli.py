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
from .delivery import build_wiki_skill
from .health import inspect_wiki_health
from .code_wiki import (
    checkpoint_code_wiki,
    finalize_code_wiki,
    prepare_code_wiki,
    publish_code_wiki_bindings,
)
from .code_sources import (
    bind_code_worktree,
    inspect_code_repository,
    rebuild_code_source_registry,
    resolve_code_worktree,
)
from .code_index.cache import build_or_update_index, cache_root_for, load_current_index
from .code_index.query import query_graph
from .runtime import (
    apply_run,
    approve_run,
    freeze_run,
    migrate_repository,
    prepare_run,
    query_registered_raw,
    review_run,
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
        help=argparse.SUPPRESS,
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
    parser.add_argument(
        "--review-reason",
        action="append",
        default=[],
        choices=["explicit", "high-risk", "medium-risk", "multi-turn"],
        dest="review_reasons",
    )
    parser.add_argument(
        "--evidence-json",
        action="append",
        default=[],
        help="bounded Raw/code evidence object; repeat as needed",
    )
    parser.add_argument(
        "--impact-json",
        action="append",
        default=[],
        help="frozen impact {path,change,summary}; repeat as needed",
    )

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        evidence_bindings: list[dict[str, Any]] = []
        for raw in args.evidence_json:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ADWikiError("each --evidence-json value must be a JSON object")
            evidence_bindings.append(value)
        impact_summary: list[dict[str, Any]] = []
        for raw in args.impact_json:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ADWikiError("each --impact-json value must be a JSON object")
            impact_summary.append(value)
        return (
            prepare_run(
                args.repo,
                run_id=args.run_id,
                operation=args.operation,
                risk=args.risk,
                inputs=args.inputs,
                read_set=args.read_set,
                write_set=args.write_set,
                review_reasons=args.review_reasons,
                evidence_bindings=evidence_bindings,
                impact_summary=impact_summary,
            ),
            0,
        )

    return _execute(
        parser,
        runner,
        argv,
    )


def prepare_code_wiki_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Prepare a resumable full-Wiki Code Wiki compilation.")
    parser.add_argument("--code-repo", required=True, help="clean local Git code repository root")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--structural-index", action="store_true")
    return _execute(
        parser,
        lambda args: (
            prepare_code_wiki(
                args.repo,
                code_repo=args.code_repo,
                run_id=args.run_id,
                structural_index=args.structural_index,
            ),
            0,
        ),
        argv,
    )


def checkpoint_code_wiki_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Checkpoint one Concept in a full-Wiki Code Wiki compilation.")
    parser.add_argument("--code-repo", required=True, help="clean local Git code repository root")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--concept", required=True, dest="concept_id")
    parser.add_argument(
        "--status",
        required=True,
        choices=["enriched", "docs-only", "no-code-match", "needs-review", "failed"],
    )
    parser.add_argument("--result-json", required=True, help="JSON object with reason and evidence")
    parser.add_argument("--retry", action="store_true")

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        value = json.loads(args.result_json)
        if not isinstance(value, dict):
            raise ADWikiError("--result-json must be a JSON object")
        return (
            checkpoint_code_wiki(
                args.repo,
                code_repo=args.code_repo,
                run_id=args.run_id,
                concept_id=args.concept_id,
                status=args.status,
                result=value,
                retry=args.retry,
            ),
            0,
        )

    return _execute(parser, runner, argv)


def finalize_code_wiki_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Finalize a fully evaluated Code Wiki run for atomic Apply.")
    parser.add_argument("--code-repo", required=True, help="clean local Git code repository root")
    parser.add_argument("--run-id", required=True)
    return _execute(
        parser,
        lambda args: (
            finalize_code_wiki(args.repo, code_repo=args.code_repo, run_id=args.run_id),
            0,
        ),
        argv,
    )


def publish_code_bindings_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Publish structural Concept bindings after a validated Code Wiki Apply.")
    parser.add_argument("--run-id", required=True)
    return _execute(
        parser,
        lambda args: (publish_code_wiki_bindings(args.repo, run_id=args.run_id), 0),
        argv,
    )


def build_code_index_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Build or incrementally update a deterministic structural code index.")
    parser.add_argument("--code-repo", required=True)
    parser.add_argument("--workers", type=int, default=4)

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        code_source = inspect_code_repository(args.code_repo)
        cache_root = cache_root_for(args.repo, code_source)
        payload = build_or_update_index(
            args.code_repo,
            cache_root=cache_root,
            revision=code_source["revision"],
            workers=args.workers,
        )
        return {
            **payload,
            "cache_root": cache_root.relative_to(Path(args.repo).expanduser().resolve()).as_posix(),
            "code_source": code_source,
        }, 0

    return _execute(parser, runner, argv)


def bind_code_worktree_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Bind one explicit local Git worktree to portable code identity.")
    parser.add_argument("--code-repo", required=True)
    return _execute(
        parser,
        lambda args: (bind_code_worktree(args.repo, code_repo=args.code_repo), 0),
        argv,
    )


def resolve_code_worktree_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Resolve one exact local Git worktree without directory scanning.")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--canonical-remote")
    identity.add_argument("--repository-key")
    parser.add_argument("--revision")
    parser.add_argument("--require-clean", action="store_true")

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        payload = resolve_code_worktree(
            args.repo,
            canonical_remote=args.canonical_remote,
            repository_key=args.repository_key,
            revision=args.revision,
            require_clean=args.require_clean,
        )
        return payload, 0 if payload["status"] == "resolved" else 1

    return _execute(parser, runner, argv)


def rebuild_code_source_registry_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Rebuild portable code source identity from validated Code Wiki runs.")
    return _execute(parser, lambda args: (rebuild_code_source_registry(args.repo), 0), argv)


def query_code_index_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Query the successful deterministic structural code index.")
    parser.add_argument("--code-repo", required=True)
    parser.add_argument("--request-json", required=True)

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        request = json.loads(args.request_json)
        if not isinstance(request, dict):
            raise ADWikiError("--request-json must be a JSON object")
        code_source = inspect_code_repository(args.code_repo)
        graph, manifest = load_current_index(cache_root_for(args.repo, code_source))
        if graph.get("revision") != code_source["revision"]:
            raise ADWikiError("structural index revision does not match code repository HEAD")
        return {**query_graph(graph, request), "graph_sha256": manifest["graph_sha256"]}, 0

    return _execute(parser, runner, argv)


def inspect_code_impact_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Find structurally affected nodes for changed code paths.")
    parser.add_argument("--code-repo", required=True)
    parser.add_argument("--path", action="append", required=True, dest="paths")
    parser.add_argument("--max-depth", type=int, default=3)

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        code_source = inspect_code_repository(args.code_repo)
        graph, manifest = load_current_index(cache_root_for(args.repo, code_source))
        changed = {Path(item).as_posix() for item in args.paths}
        file_nodes = [
            item["id"]
            for item in graph["nodes"]
            if item.get("kind") == "file" and item.get("source_file") in changed
        ]
        affected_ids: set[str] = set(file_nodes)
        diagnostics: list[str] = []
        for node_id in file_nodes:
            result = query_graph(
                graph,
                {"mode": "affected", "source_id": node_id, "max_depth": args.max_depth},
            )
            affected_ids.update(item["id"] for item in result["nodes"])
            diagnostics.extend(result["diagnostics"])
        missing = sorted(changed - {item.get("source_file") for item in graph["nodes"]})
        if missing:
            diagnostics.append("changed paths absent from graph: " + ", ".join(missing))
        return {
            "revision": graph["revision"],
            "graph_sha256": manifest["graph_sha256"],
            "changed_paths": sorted(changed),
            "affected_node_ids": sorted(affected_ids),
            "diagnostics": diagnostics,
        }, 0

    return _execute(parser, runner, argv)


def approve_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Deprecated compatibility shim; approval is no longer required.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--by", dest="actor", help=argparse.SUPPRESS)
    return _execute(
        parser,
        lambda args: (approve_run(args.repo, run_id=args.run_id, actor=args.actor), 0),
        argv,
    )


def apply_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Apply, index, log, validate, and finalize a staged transaction.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-digest")
    return _execute(
        parser,
        lambda args: (
            apply_run(
                args.repo,
                run_id=args.run_id,
                candidate_digest=args.candidate_digest,
            ),
            0,
        ),
        argv,
    )


def freeze_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Freeze a review-gated staged transaction before Apply.")
    parser.add_argument("--run-id", required=True)
    return _execute(parser, lambda args: (freeze_run(args.repo, run_id=args.run_id), 0), argv)


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


def health_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Inspect AD-Wiki health without mutating the Wiki or its sources.")
    parser.add_argument("--assessment", help="optional repo-contained Wiki Health Assessment v1 JSON")
    parser.add_argument("--code-repo", help="optional latest clean Git code repository")
    parser.add_argument("--today", help="override current date as YYYY-MM-DD for deterministic checks")
    parser.add_argument(
        "--require-healthy",
        action="store_true",
        help="exit 1 when the valid report is unhealthy or incomplete",
    )

    def runner(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        current = date.fromisoformat(args.today) if args.today else None
        payload = inspect_wiki_health(
            args.repo,
            assessment_path=args.assessment,
            code_repo=args.code_repo,
            today=current,
        )
        exit_code = 1 if args.require_healthy and payload["overall_status"] != "healthy" else 0
        return payload, exit_code

    return _execute(parser, runner, argv)


def ship_main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser("Build one standalone read-only Skill from a validated AD Wiki.")
    parser.add_argument("--output", required=True, help="explicit parent directory for the generated Skill")
    parser.add_argument("--wiki-name", help="explicit Wiki delivery identity; defaults to repository basename")
    parser.add_argument(
        "--format",
        default="directory",
        dest="output_format",
        help="delivery format: directory, zip, or both (default: directory)",
    )
    return _execute(
        parser,
        lambda args: (
            build_wiki_skill(
                args.repo,
                output_parent=args.output,
                wiki_name=args.wiki_name,
                output_format=args.output_format,
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
