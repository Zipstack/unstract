"""Trigger a workflow execution over HTTP against a running stack.

Targets an Unstract **API deployment** (`POST .../execute/` with file uploads) —
the realistic load path that exercises the full dispatch → fan-out → executor
pipeline. The endpoint path and auth header are config so the same harness drives
local, staging, or any deployment without code changes.

The response carries the ``execution_id`` (async deployments return it
immediately; sync ones return it alongside the finished status) — that id is the
join key the probe uses to read server-side latency from the DB.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import requests


@dataclass(frozen=True, slots=True)
class TriggerConfig:
    """How to POST one execution to an API deployment."""

    base_url: str  # e.g. http://localhost:8000
    path: str  # e.g. /deployment/api/<org>/<api_name>/
    api_key: str
    files: list[str] = field(default_factory=list)  # local paths to upload
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    request_timeout: float = 600.0
    extra_fields: dict[str, str] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.path.lstrip("/")

    @classmethod
    def from_env(cls, **overrides: object) -> TriggerConfig:
        base = {
            "base_url": os.environ.get("PGBENCH_BASE_URL", "http://localhost:8000"),
            "path": os.environ.get("PGBENCH_DEPLOY_PATH", ""),
            "api_key": os.environ.get("PGBENCH_API_KEY", ""),
        }
        base.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**base)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class TriggerResult:
    """Outcome of a single trigger POST."""

    execution_id: str | None
    http_status: int
    http_latency: float  # seconds, request → response
    error: str | None = None


def _extract_execution_id(payload: object) -> str | None:
    """Pull the execution id out of common Unstract response shapes."""
    if not isinstance(payload, dict):
        return None
    for key in ("execution_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    # Some responses nest under "execution" or "data".
    for key in ("execution", "data"):
        nested = payload.get(key)
        found = _extract_execution_id(nested)
        if found:
            return found
    return None


def trigger_execution(
    cfg: TriggerConfig, session: requests.Session | None = None
) -> TriggerResult:
    """POST one execution; return the execution id + HTTP latency.

    Opens each upload file fresh (so the same config is reusable across many
    concurrent triggers) and always closes them.
    """
    session = session or requests.Session()
    headers = {cfg.auth_header: f"{cfg.auth_prefix}{cfg.api_key}"}
    handles = [open(path, "rb") for path in cfg.files]  # noqa: SIM115 — closed below
    try:
        files = [
            ("files", (os.path.basename(path), fh, "application/octet-stream"))
            for path, fh in zip(cfg.files, handles, strict=True)
        ]
        start = time.monotonic()
        try:
            resp = session.post(
                cfg.url,
                headers=headers,
                files=files or None,
                data=cfg.extra_fields or None,
                timeout=cfg.request_timeout,
            )
        except requests.RequestException as exc:
            return TriggerResult(
                execution_id=None,
                http_status=0,
                http_latency=time.monotonic() - start,
                error=f"request failed: {exc}",
            )
        latency = time.monotonic() - start
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        execution_id = _extract_execution_id(payload)
        error = None
        if resp.status_code >= 400:
            error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        elif execution_id is None:
            error = f"no execution_id in response: {str(payload)[:200]}"
        return TriggerResult(
            execution_id=execution_id,
            http_status=resp.status_code,
            http_latency=latency,
            error=error,
        )
    finally:
        for fh in handles:
            fh.close()
