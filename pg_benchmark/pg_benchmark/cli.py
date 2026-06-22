"""CLI entrypoint for the PG-vs-Celery benchmark harness.

Slice 1 ships the measurement spine: ``report`` reads finished executions
straight from the DB and prints a per-transport latency comparison. Load
generation (``run``) and live transport sampling are later slices and plug into
these same readers.
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import DbConfig
from .db import Transport, connect, fetch_recent, queue_depth
from .probe import RunResult
from .report import build_reports, render, render_load
from .runner import run_load
from .trigger import TriggerConfig

_TRANSPORT_CHOICES = {t.value: t for t in Transport}


def _add_db_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-host", help="override DB_HOST")
    parser.add_argument("--db-port", type=int, help="override DB_PORT")
    parser.add_argument("--db-name", help="override DB_NAME")
    parser.add_argument("--db-user", help="override DB_USER")
    parser.add_argument("--db-password", help="override DB_PASSWORD")


def _db_config(args: argparse.Namespace) -> DbConfig:
    base = DbConfig.from_env()
    return DbConfig(
        host=args.db_host or base.host,
        port=args.db_port or base.port,
        name=args.db_name or base.name,
        user=args.db_user or base.user,
        password=args.db_password or base.password,
        schema=base.schema,
    )


def _cmd_report(args: argparse.Namespace) -> int:
    transport = _TRANSPORT_CHOICES.get(args.transport) if args.transport else None
    conn = connect(_db_config(args))
    try:
        executions = fetch_recent(conn, limit=args.last, transport=transport)
        print(
            f"Sampled {len(executions)} terminal executions "
            f"(last {args.last}{', ' + args.transport if args.transport else ''}).\n"
        )
        print(render(build_reports(executions)))
    finally:
        conn.close()
    return 0


def _cmd_queue_depth(args: argparse.Namespace) -> int:
    conn = connect(_db_config(args))
    try:
        depth = queue_depth(conn)
        if not depth:
            print("pg_queue_message is empty.")
        else:
            for name, count in sorted(depth.items(), key=lambda kv: -kv[1]):
                print(f"  {name:<28} {count}")
    finally:
        conn.close()
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    api_key = args.api_key or os.environ.get("PGBENCH_API_KEY", "")
    if not args.path:
        print("error: --path (API deployment execute path) is required", file=sys.stderr)
        return 2
    if not api_key:
        print("error: --api-key or PGBENCH_API_KEY is required", file=sys.stderr)
        return 2
    trigger_cfg = TriggerConfig(
        base_url=args.base_url,
        path=args.path,
        api_key=api_key,
        files=args.file or [],
        auth_header=args.auth_header,
        auth_prefix=args.auth_prefix,
    )
    db_cfg = _db_config(args)
    done = {"n": 0}

    def _progress(result: RunResult) -> None:
        done["n"] += 1
        tag = (result.transport.value if result.transport else "?").upper()
        state = "ok" if result.ok else f"FAIL({result.error})"
        wc = f"{result.wall_clock_e2e:.1f}s" if result.wall_clock_e2e else "-"
        print(f"  [{done['n']}/{args.n}] {tag} {state} wall={wc}", file=sys.stderr)

    print(
        f"Driving {args.n} executions at concurrency {args.concurrency} "
        f"against {trigger_cfg.url} ...\n",
        file=sys.stderr,
    )
    outcome = run_load(
        trigger_cfg,
        db_cfg,
        n=args.n,
        concurrency=args.concurrency,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
        on_result=_progress,
    )
    print()
    print(render_load(outcome))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pg_benchmark",
        description="PG-queue vs Celery execution benchmark harness.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser(
        "report", help="compare recent executions by transport (read-only)"
    )
    report.add_argument(
        "--last", type=int, default=100, help="how many recent executions to sample"
    )
    report.add_argument(
        "--transport",
        choices=sorted(_TRANSPORT_CHOICES),
        help="restrict to one transport (default: all, side by side)",
    )
    _add_db_args(report)
    report.set_defaults(func=_cmd_report)

    qd = sub.add_parser("queue-depth", help="current pg_queue_message depth per queue")
    _add_db_args(qd)
    qd.set_defaults(func=_cmd_queue_depth)

    run = sub.add_parser(
        "run", help="drive N executions at concurrency C and measure latency"
    )
    run.add_argument("--n", type=int, default=10, help="total executions to trigger")
    run.add_argument(
        "--concurrency", type=int, default=4, help="max executions in flight at once"
    )
    run.add_argument(
        "--base-url", default=os.environ.get("PGBENCH_BASE_URL", "http://localhost:8000")
    )
    run.add_argument(
        "--path",
        default=os.environ.get("PGBENCH_DEPLOY_PATH", ""),
        help="API deployment execute path, e.g. /deployment/api/<org>/<api>/",
    )
    run.add_argument("--api-key", help="API key (or set PGBENCH_API_KEY)")
    run.add_argument("--file", action="append", help="local file to upload (repeatable)")
    run.add_argument("--auth-header", default="Authorization")
    run.add_argument("--auth-prefix", default="Bearer ")
    run.add_argument("--poll-interval", type=float, default=0.5)
    run.add_argument("--timeout", type=float, default=600.0)
    _add_db_args(run)
    run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
