"""Benchmark configuration — DB connection + backend endpoint.

Defaults mirror the local docker-compose stack (``backend/backend/settings/base.py``)
so the harness runs against a dev stack with zero flags, and every value is
overridable by env or CLI for staging/load hosts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DbConfig:
    """Read-only Postgres connection to the backend DB.

    The harness only ever SELECTs (latency readers + queue depth); it never
    writes to these tables. ``schema`` is set on the search_path at connect time
    so the PG-queue tables (which live in the ``unstract`` schema) resolve
    unqualified.
    """

    host: str = "localhost"
    port: int = 5432
    name: str = "unstract_db"
    user: str = "unstract_dev"
    password: str = "unstract_pass"
    schema: str = "unstract"

    @classmethod
    def from_env(cls) -> DbConfig:
        # Read defaults off a default instance, not the class: on a slots
        # dataclass ``cls.port`` is the slot descriptor, not the default value.
        d = cls()
        return cls(
            host=os.environ.get("DB_HOST", d.host),
            port=int(os.environ.get("DB_PORT", d.port)),
            name=os.environ.get("DB_NAME", d.name),
            user=os.environ.get("DB_USER", d.user),
            password=os.environ.get("DB_PASSWORD", d.password),
            schema=os.environ.get("DB_SCHEMA", d.schema),
        )

    def dsn_kwargs(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password,
            "options": f"-c search_path={self.schema},public",
        }
