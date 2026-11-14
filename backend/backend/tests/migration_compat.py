"""Backward-compatibility rules for Django migrations.

During an upgrade the schema changes while pods of the previous release are still
serving, and rolling back the image puts that release back on the new schema. So every
migration has to leave the previous release working. This module finds the operations
that do not.

It reads Django operation objects and the project state. It runs no SQL and opens no
database connection. Nothing here is imported by application code: the module lives
under a ``tests`` directory, which the image build ignores.

Terms
-----
released   A migration listed in a ``migration_baseline.txt``: it is on the newest
           release branch. Released migrations are not checked. The state they build
           is what the previous release's models look like.
new        Any other first-party migration. Every operation in it is checked.
           A table or column that only new migrations created is exempt, because no
           released code can be using it.

``test_migration_compat.py`` runs it. How to write a migration that passes, and how to
waive a finding, is in backend/README.md under "Writing migrations".
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import sqlparse
from django.contrib.postgres import operations as pg
from django.db import connection, migrations, models
from django.db.backends.utils import truncate_name
from django.db.migrations.graph import MigrationGraph
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
from django.db.migrations.utils import resolve_relation
from django.db.models.fields import NOT_PROVIDED
from django.test import override_settings

Key = tuple[str, str]  # (app label, migration name) or (app label, model name)

WAIVER_ATTRIBUTE = "backward_compat_waivers"
MIN_REASON_LENGTH = 20
REASON_PLACEHOLDER = "<why the previous release keeps working>"
# One file per repository that adds migrations to this backend. This repository's is
# backend/tests/migration_baseline.txt; the guard reads every match and takes the union.
BASELINE_GLOB = "*/tests/migration_baseline.txt"
THIRD_PARTY = "third-party"
RELEASED_THROUGH = re.compile(
    r"^# released-through: (?:origin/)?release/\d+\.\d+ @ [0-9a-f]+$", re.M
)

# Tables that a service outside this repository also reads and writes. That service is
# not on this release train, so it never becomes "the previous release": waiting a
# release does not make a change safe for it. table -> who else uses it.
SHARED_TABLES = {"user": "Unstract ID inserts and reads this table"}

# rule id -> (why it breaks, what to do instead). The first ten are certain to break
# the previous release if it uses the object (state-drop-not-null breaks the new one).
# For the rest the guard cannot tell, and the waiver states the fact it lacks.
RULES: dict[str, tuple[str, str]] = {
    "add-not-null": (
        "Django 4.2 drops the default it used to fill existing rows, so the column is "
        "NOT NULL with no database default. The previous release does not know the "
        "column: every INSERT it makes into this table fails with a NOT NULL violation.",
        "In the same migration, after the AddField, add migrations.RunSQL('ALTER TABLE "
        "<table> ALTER COLUMN <column> SET DEFAULT <value>', reverse_sql=...) "
        "(see account_v2/migrations/0010_user_profile_fields.py), or make the column "
        "nullable.",
    ),
    "set-not-null": (
        "The previous release's model still allows NULL, so it can write a NULL and get "
        "a NOT NULL violation. SET NOT NULL also scans the whole table under an ACCESS "
        "EXCLUSIVE lock.",
        "Release 1: stop writing NULL, backfill, and change the model with a state-only "
        "AlterField (SeparateDatabaseAndState). Release 2: SET NOT NULL with RunSQL.",
    ),
    "drop-column": (
        "The previous release's model still declares the column. The ORM names every "
        "column in SELECT and INSERT, so every query that release runs on this model "
        "fails with 'column does not exist'.",
        "Release 1: remove the field from the model with a state-only RemoveField "
        "(SeparateDatabaseAndState; add DROP NOT NULL if the column is NOT NULL). "
        "Release 2: drop the column with RunSQL.",
    ),
    "drop-table": (
        "The previous release's models still use the table, so its queries fail with "
        "'relation does not exist'.",
        "Release 1: delete the model with a state-only DeleteModel (or state-only "
        "RemoveField for a ManyToManyField). Release 2: drop the table with RunSQL.",
    ),
    "rename-column": (
        "The previous release still reads and writes the old column name, so its "
        "queries on this model fail.",
        "Rename only in Python and keep the database name with db_column=<old name>. "
        "To really rename: add the new column, write both, backfill, switch reads, and "
        "drop the old column a release later.",
    ),
    "rename-table": (
        "The previous release still queries the old table name (for RenameModel also "
        "the auto-created many-to-many tables and their <model>_id columns).",
        "Rename only in Python and pin Meta.db_table to the old name. To really rename "
        "a table, create the new one and move over across releases.",
    ),
    "alter-column-type": (
        "The previous release reads and writes the old type, and most type changes "
        "rewrite the table under an ACCESS EXCLUSIVE lock.",
        "Add a new column with the new type, write both, backfill, switch reads, and "
        "drop the old column a release later. Widening a varchar is allowed as is.",
    ),
    "add-unique": (
        "The previous release can still write duplicates and gets an IntegrityError it "
        "does not handle. The migration itself fails if duplicates already exist, and "
        "building the index blocks writes.",
        "Release 1: stop creating duplicates and clean up existing ones. Release 2: "
        "build the unique index CONCURRENTLY and attach the constraint. Release 2 is "
        "reported too, once per statement: put each statement in its own RunSQL and "
        "waive each, naming the release that stopped creating duplicates. If the table "
        "is in SHARED_TABLES (backend/backend/tests/migration_compat.py), the waiver "
        "should also say what the other service writes; this finding does not say the "
        "table is shared.",
    ),
    "add-constraint": (
        "The previous release can still write rows that violate the constraint and "
        "gets an IntegrityError it does not handle. Validating it scans the table under "
        "a lock.",
        "Release 1: make the code obey the rule and fix existing rows. Release 2: add "
        "the constraint. Release 2 is reported too: add a waiver naming the release "
        "that stopped writing violating rows. If the table is in SHARED_TABLES "
        "(backend/backend/tests/migration_compat.py), the waiver should also say what "
        "the other service writes; this finding does not say the table is shared.",
    ),
    "state-drop-not-null": (
        "The field leaves the model but its column stays NOT NULL with no database "
        "default. This breaks the NEW release: its INSERTs no longer send the column.",
        "Add 'ALTER TABLE <table> ALTER COLUMN <column> DROP NOT NULL' to "
        "database_operations of the same SeparateDatabaseAndState.",
    ),
    "drop-unique": (
        "The previous release may name these columns in INSERT ... ON CONFLICT (raw SQL "
        "in workers and platform-service) or bulk_create(update_conflicts=True). "
        "Without the unique constraint every such statement fails.",
        "Grep backend/, workers/ and platform-service/ for ON CONFLICT and "
        "update_conflicts on this table. If nothing in the previous release targets "
        "the constraint, add a waiver that says so; otherwise drop it a release after "
        "the code stopped using it.",
    ),
    "shared-table": (
        "A service outside this repository also uses this table. It is not released "
        "with this code, so it keeps its queries however many releases pass: the "
        "two-release recipes do not make this change safe for it.",
        "Change that service first and wait until no deployment runs its old version. "
        "Then add a waiver that names the version from which it no longer needs the "
        "old shape. A column it inserts without keeps its database default for good.",
    ),
    "contract-drop": (
        "The released models no longer declare this, so Django code of the previous "
        "release does not use it. The guard cannot see raw SQL (workers, "
        "platform-service) or Unstract ID, and a drop cannot be rolled back.",
        "Check that nothing outside the ORM reads or writes it, and that this change is "
        "not backported to the release line that removed it from the models. Then add "
        "a waiver naming the release in which it stopped being used.",
    ),
    "blocking-index": (
        "CREATE INDEX without CONCURRENTLY holds a SHARE lock for the whole build: "
        "every write to the table from the pods still serving waits.",
        "Use AddIndexConcurrently (django.contrib.postgres.operations) in a migration "
        "with atomic = False; see "
        "account_usage/migrations/0003_add_performance_indexes.py.",
    ),
    "implicit-index": (
        "Adding a column with unique=True, db_index=True or a ForeignKey builds an "
        "index (and validates the foreign key) inside the ALTER TABLE. Writes to the "
        "table wait while it runs.",
        "On a small table, waive it and state the row count. On a large table add the "
        "field with db_index=False and build the index with AddIndexConcurrently. A "
        "ForeignKey is still reported, because the ALTER TABLE validates its constraint "
        "by scanning the table under the lock: waive it with the row count, or, with "
        "db_index=False, set db_constraint=False if the database need not enforce the "
        "relation. A unique column always needs the waiver.",
    ),
    "data-migration": (
        "The data change runs while the previous release is serving. The guard cannot "
        "tell whether that release still works on the rewritten rows, or how long the "
        "change holds locks.",
        "Add a waiver that answers: which released tables does this function (or "
        "statement) write, and what does the previous release read from them? Say "
        "roughly how many rows it touches.",
    ),
    "raw-sql": (
        "The guard cannot classify this SQL (the line above says why), so it cannot "
        "tell what it does to tables the previous release uses.",
        "Use a Django operation if one exists. Otherwise add a waiver that says what "
        "the statement does and why the previous release is unaffected.",
    ),
    "unclassified-operation": (
        "The guard has no rule for this operation class.",
        "Classify it in backend/backend/tests/migration_compat.py (SAFE_OPERATIONS or "
        "a rule), or add a waiver that says what it does to existing tables.",
    ),
}

# On a table in SHARED_TABLES a finding of one of these rules brings a shared-table
# finding with it: the other service is affected whatever the previous release does.
# add-unique and add-constraint are not listed, and their findings do not name a
# shared table. Their "Do instead" asks the waiver to say what the other service
# writes; nothing checks that but the reviewer of the waiver.
_UNSAFE_FOR_OTHER_WRITERS = frozenset(
    {
        "drop-column",
        "drop-table",
        "drop-unique",
        "contract-drop",
        "rename-column",
        "rename-table",
        "alter-column-type",
        "set-not-null",
    }
)

# Operations that cannot break the previous release.
SAFE_OPERATIONS = (
    migrations.RemoveIndex,  # includes RemoveIndexConcurrently
    migrations.RenameIndex,
    migrations.AlterModelOptions,
    migrations.AlterModelManagers,
    migrations.AlterModelTableComment,
    pg.AddIndexConcurrently,
    pg.CreateExtension,
    pg.ValidateConstraint,
)


def _from_django(op) -> bool:
    """An operation class as Django ships it. A subclass defined in the project can run
    any SQL from database_forwards, so it gets neither the exemption nor the rule of
    its base class.
    """
    return type(op).__module__.startswith(
        ("django.db.migrations.", "django.contrib.postgres.")
    )


@dataclass(frozen=True)
class Finding:
    app_label: str
    migration: str
    op: str  # "3", or "3.db.0" for database_operations[0] of operations[3]
    rule: str
    detail: str

    def render(self) -> str:
        why, instead = RULES[self.rule]
        return (
            f"{self.app_label}.{self.migration} operations[{self.op}]  [{self.rule}]\n"
            f"    {self.detail}\n"
            f"    Why: {why}\n"
            f"    Do instead: {instead}\n"
            f"    Or waive in the migration, with a reviewer's agreement:\n"
            f'        {WAIVER_ATTRIBUTE} = [{{"op": "{self.op}", "rule": "{self.rule}", '
            f'"reason": "{REASON_PLACEHOLDER}"}}]'
        )


# ── Physical names, computed from the state without rendering models ──────────────


def _norm(identifier: str) -> str:
    return identifier.strip().strip('"').lower()


def _has_table(model_state) -> bool:
    options = model_state.options
    return options.get("managed", True) and not options.get("proxy", False)


def _table(model_state) -> str:
    name = model_state.options.get("db_table") or truncate_name(
        f"{model_state.app_label}_{model_state.name_lower}", 63
    )
    return _norm(name)


def _bound(field, name: str):
    """A copy of the field that knows its name, as it would on a model class."""
    bound = field.clone()
    bound.set_attributes_from_name(name)
    return bound


def _column(field, name: str) -> str:
    return _norm(_bound(field, name).column)


def _auto_m2m_table(model_state, field, name: str) -> str | None:
    """The table Django creates for a ManyToManyField, or None when it creates none."""
    if not field.many_to_many or field.remote_field.through is not None:
        return None
    return _norm(field.db_table or truncate_name(f"{_table(model_state)}_{name}", 63))


def _column_type(state: ProjectState, model_key: Key, name: str, depth: int = 0) -> str:
    """The database type of a column; a foreign key has the type of the key it points at."""
    field = state.models[model_key].fields[name]
    if field.remote_field is not None and field.remote_field.model and depth < 5:
        target_key = resolve_relation(field.remote_field.model, *model_key)
        target = state.models.get(target_key)
        if target is None:
            return f"reference to {target_key[0]}.{target_key[1]}"
        to_field = _referenced_field(state, field, model_key)
        if to_field in target.fields:
            return _column_type(state, target_key, to_field, depth + 1)
        return f"reference to {target_key[0]}.{target_key[1]}"
    return str(field.db_type(connection))


def _referenced_field(state: ProjectState, field, model_key: Key) -> str:
    """The name of the field a ForeignKey points at: to_field, or the primary key."""
    name = getattr(field.remote_field, "field_name", None)
    if name:
        return name
    target = state.models.get(resolve_relation(field.remote_field.model, *model_key))
    fields = target.fields if target else {}
    return next((n for n, f in fields.items() if f.primary_key), "id")


def _widens(old: str, new: str) -> bool:
    """varchar(n) -> varchar(m >= n), unbounded varchar or text: no rewrite, and the
    previous release's shorter values still fit.
    """
    was = re.fullmatch(r"varchar\((\d+)\)", old)
    now = re.fullmatch(r"varchar\((\d+)\)", new)
    if was and now:
        return int(now.group(1)) >= int(was.group(1))
    return (bool(was) or old == "varchar") and new in ("varchar", "text")


def released_schema(state: ProjectState) -> dict[str, dict[str, object]]:
    """table -> column -> field, as the previous release's models see the database."""
    schema: dict[str, dict[str, object]] = {}
    for model_state in state.models.values():
        if not _has_table(model_state):
            continue
        columns = schema.setdefault(_table(model_state), {})
        for name, model_field in model_state.fields.items():
            if model_field.many_to_many:
                through = _auto_m2m_table(model_state, model_field, name)
                if through:
                    schema.setdefault(through, {})
            else:
                columns[_column(model_field, name)] = model_field
    return schema


# ── RunSQL ─────────────────────────────────────────────────────────────────────────
#
# Statements are matched with string literals blanked out, case-insensitively. An
# identifier may be quoted, bare or schema-qualified. Anything not recognised is a
# raw-sql finding, so unknown SQL fails closed.

_ID = r'(?:"[^"]+"|[A-Za-z_][\w$]*)'
_NAME = rf"(?:{_ID}\s*\.\s*)?({_ID})"  # optional schema, then the captured name
_ALTER_TABLE = re.compile(
    rf"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?{_NAME}\s+(.*)", re.I | re.S
)
_ALTER_COLUMN = re.compile(rf"ALTER\s+(?:COLUMN\s+)?({_ID})\s+(.*)", re.I | re.S)
_DROP_COLUMN = re.compile(
    rf"DROP\s+(?!CONSTRAINT\b)(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?({_ID})"
    r"(?:\s+(?:CASCADE|RESTRICT))?",
    re.I,
)
_ADD_COLUMN = re.compile(
    rf"ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?({_ID})\s+(.*)", re.I | re.S
)
# A table constraint does not need the word CONSTRAINT: ADD UNIQUE (code) is valid.
_ADD_TABLE_CONSTRAINT = re.compile(
    r"ADD\s+(CONSTRAINT|UNIQUE|PRIMARY\s+KEY|CHECK|FOREIGN\s+KEY|EXCLUDE)\b", re.I
)
_CREATE_INDEX = re.compile(
    rf"CREATE\s+(UNIQUE\s+)?INDEX\s+(CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
    rf"(?:({_ID})\s+)?ON\s+(?:ONLY\s+)?{_NAME}",
    re.I,
)
_DROP_INDEX = re.compile(
    r"DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+EXISTS\s+)?(.+?)"
    r"(?:\s+(?:CASCADE|RESTRICT))?",
    re.I | re.S,
)
# Without IF NOT EXISTS the statement fails on an existing table, so the table is new.
_CREATE_TABLE = re.compile(rf"CREATE\s+TABLE\s+(?!IF\b){_NAME}", re.I)
_DROP_TABLE = re.compile(
    r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(.+?)(?:\s+(?:CASCADE|RESTRICT))?", re.I | re.S
)
_DATA = re.compile(r"(UPDATE|INSERT|DELETE|TRUNCATE|MERGE|COPY|WITH)\b", re.I)
_DATA_TARGET = re.compile(
    rf"(?:UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+(?:ONLY\s+)?{_NAME}", re.I
)
# What lets an INSERT that omits the column succeed. SET DEFAULT NULL does not.
_SETS_DEFAULT = re.compile(r"SET\s+DEFAULT\s+(?!NULL\b)", re.I)
_DROPS_NOT_NULL = re.compile(r"DROP\s+NOT\s+NULL\b", re.I)
_REMOVES_DEFAULT = re.compile(r"(DROP\s+DEFAULT|SET\s+DEFAULT\s+NULL)\b", re.I)
# What a DO block may not contain to count as read-only. An assignment or a sequence
# function writes without any statement keyword: v := setval(...). SELECT ... INTO a
# variable stays allowed, because the index checks use it (workflow_v2 0029).
_WRITES = re.compile(
    r"\b(ALTER|CREATE|DROP|UPDATE|INSERT|DELETE|TRUNCATE|EXECUTE|PERFORM|CALL|GRANT|REVOKE"
    r"|SETVAL|NEXTVAL|LOCK|COPY)\b|:=",
    re.I,
)
_HARMLESS = re.compile(
    r"(CREATE\s+TABLE|CREATE\s+EXTENSION|COMMENT\s+ON"
    r"|SET\s+(LOCAL\s+)?(lock_timeout|statement_timeout))\b",
    re.I,
)
_DO_BLOCK = re.compile(r"DO\s+\$(\w*)\$(.*)\$\1\$", re.I | re.S)
# A quoted identifier comes first so that an apostrophe inside one ("it's") does not
# start a string; it is matched only to be skipped.
_LITERAL = re.compile(r""""[^"]*"|'(?:[^']|'')*'|\$(\w*)\$.*?\$\1\$""", re.S)


def _statements(sql) -> Iterator[str]:
    """The single statements of a RunSQL argument, without comments, on one line."""
    parts = sql if isinstance(sql, (list, tuple)) else [sql]
    for part in parts:
        text = part[0] if isinstance(part, (list, tuple)) else part  # (sql, params)
        for statement in sqlparse.split(str(text)):
            cleaned = sqlparse.format(statement, strip_comments=True)
            cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(";").strip()
            if cleaned:
                yield cleaned


def _without_literals(text: str) -> str:
    """The text with the inside of every '...' and $tag$...$tag$ replaced by spaces, so
    that a comma, bracket, semicolon or keyword in a string is not read as SQL.
    """

    def blank(match: re.Match) -> str:
        found = match.group(0)
        if found.startswith('"'):
            return found
        return found[0] + " " * (len(found) - 2) + found[-1]

    return _LITERAL.sub(blank, text)


def _read_only_block(statement: str) -> bool:
    """A DO block that only reads and raises, like the index checks that follow
    CREATE INDEX CONCURRENTLY (workflow_v2 0029). Text inside string literals is
    ignored, so an error message may mention DROP INDEX.
    """
    block = _DO_BLOCK.fullmatch(statement)
    return bool(block) and not _WRITES.search(_without_literals(block.group(2)))


def _split_actions(rest: str) -> list[str]:
    """Split the comma-separated actions of one ALTER TABLE, ignoring commas in ()."""
    actions, depth, start = [], 0, 0
    for i, char in enumerate(rest):
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            actions.append(rest[start:i].strip())
            start = i + 1
    actions.append(rest[start:].strip())
    return [a for a in actions if a]


def _walk_database_operations(
    operations, prefix: str = ""
) -> Iterator[tuple[str, object]]:
    """(path, operation) for every operation that reaches the database, in the order
    Django runs them.
    """
    for i, op in enumerate(operations):
        path = f"{prefix}{i}"
        if isinstance(op, migrations.SeparateDatabaseAndState):
            yield from _walk_database_operations(op.database_operations, f"{path}.db.")
        else:
            yield path, op


def _alter_table_actions(
    operations, after: str | None = None
) -> Iterator[tuple[str, str]]:
    """(table, action) for every ALTER TABLE action that RunSQL runs in these
    operations; with ``after``, only in operations that come later than that path.
    """
    counting = after is None
    for path, op in _walk_database_operations(operations):
        if not counting:
            counting = path == after
        elif isinstance(op, migrations.RunSQL):
            for statement in _statements(op.sql):
                alter = _ALTER_TABLE.fullmatch(_without_literals(statement))
                if alter:
                    for action in _split_actions(alter.group(2)):
                        yield _norm(alter.group(1)), action


def kept_defaults(operations, after: str | None = None) -> set[tuple[str, str]]:
    """(table, column) pairs that RunSQL in these operations gives a database default
    (or makes nullable), so an INSERT that omits the column succeeds.
    """
    with_default, nullable = set(), set()
    for table, action in _alter_table_actions(operations, after):
        column = _ALTER_COLUMN.fullmatch(action)
        if not column:
            continue
        pair, change = (table, _norm(column.group(1))), column.group(2)
        if _SETS_DEFAULT.match(change):
            with_default.add(pair)
        elif _REMOVES_DEFAULT.match(change):
            with_default.discard(pair)  # a later statement took the default away
        elif _DROPS_NOT_NULL.match(change):
            nullable.add(pair)
    return with_default | nullable


def _built_indexes(operations) -> set[str]:
    """The names of the indexes that these operations build in the database."""
    built = set()
    for _path, op in _walk_database_operations(operations):
        if isinstance(op, migrations.AddIndex):  # AddIndexConcurrently too
            built.add(_norm(op.index.name))
        elif isinstance(op, migrations.RunSQL):
            for statement in _statements(op.sql):
                index = _CREATE_INDEX.match(_without_literals(statement))
                if index and index.group(3):
                    built.add(_norm(index.group(3)))
    return built


def _dropped_columns(operations) -> set[tuple[str, str]]:
    """(table, column) pairs dropped by RunSQL in these operations."""
    dropped = set()
    for table, action in _alter_table_actions(operations):
        drop = _DROP_COLUMN.fullmatch(action)
        if drop:
            dropped.add((table, _norm(drop.group(1))))
    return dropped


# ── The walk ───────────────────────────────────────────────────────────────────────


class _Linter:
    """Checks each operation of the new migrations against the state, then applies it."""

    def __init__(self, state: ProjectState):
        self.state = state  # running state; mutated as operations are applied
        self.schema = released_schema(state)  # the previous release's tables and columns
        # Meta.indexes of the previous release's models: never unique.
        self.released_plain_indexes = {
            _norm(index.name)
            for model_state in state.models.values()
            for index in model_state.options.get("indexes", ())
        }
        # What new migrations created. Models and fields are kept by name and not
        # looked up in `schema`, so a state-only rename in a new migration does not
        # hide a released table.
        self.new_models: set[Key] = set()
        self.new_fields: set[tuple[Key, str]] = set()
        self.new_sql_tables: set[str] = set()  # CREATE TABLE in RunSQL
        # Indexes that this release builds in the database, in the migration being
        # checked or an earlier new one. A state-only AddIndex is not one: it can
        # name an index that exists already.
        self.new_indexes: set[str] = set()
        self.findings: list[Finding] = []
        self._migration = None
        self._kept: set[tuple[str, str]] = set()  # in the migration being checked
        self._kept_so_far: set[tuple[str, str]] = set()  # in it or an earlier new one

    # -- helpers --
    def _report(
        self, path: str, rule: str, detail: str, table: str | None = None
    ) -> None:
        """Record a finding. ``table`` is the table the operation changes, for the
        rules that also matter to the other writers of a shared table.
        """
        m = self._migration
        self.findings.append(Finding(m.app_label, m.name, path, rule, detail))
        if rule in _UNSAFE_FOR_OTHER_WRITERS:
            self._report_if_shared(path, table, detail)

    def _report_if_shared(self, path: str, table: str | None, detail: str) -> None:
        if table in SHARED_TABLES:
            m = self._migration
            detail = f"{detail} [{table}: {SHARED_TABLES[table]}]"
            self.findings.append(
                Finding(m.app_label, m.name, path, "shared-table", detail)
            )

    def _model(self, app_label: str, model_name: str):
        key = (app_label, model_name.lower())
        return key, self.state.models.get(key)

    def _released_model(self, key: Key) -> bool:
        """True when the previous release has this model's table."""
        model_state = self.state.models.get(key)
        if model_state is None or not _has_table(model_state):
            return False
        # A state-only CreateModel can adopt a table an earlier release created (a
        # model moved between apps, an explicit through model for an existing
        # many-to-many). The model is new then, but the table is not.
        return key not in self.new_models or _table(model_state) in self.schema

    def _released_field(self, key: Key, name: str) -> bool:
        if not self._released_model(key):
            return False
        if (key, name) not in self.new_fields:
            return True
        # A state-only AddField can adopt a column an earlier release created (a
        # field declared again after a state-only RemoveField). The field is new
        # then, but the column is not.
        model_state = self.state.models[key]
        model_field = model_state.fields.get(name)
        if model_field is None or model_field.many_to_many:
            return False
        return _column(model_field, name) in self.schema.get(_table(model_state), {})

    def _born_new(self, table: str, column: str | None = None) -> bool:
        """True when only new migrations created this table (or this column of it)."""
        if table in self.new_sql_tables:
            return True
        if column is not None and column in self.schema.get(table, {}):
            return False  # the previous release has the column, whoever declares it now
        for key, model_state in self.state.models.items():
            if not _has_table(model_state) or _table(model_state) != table:
                continue
            if key in self.new_models and table not in self.schema:
                return True
            if any(
                (key, name) in self.new_fields and _column(f, name) == column
                for name, f in model_state.fields.items()
                if not f.many_to_many
            ):
                return True
        return False

    # -- entry points --
    def migration(self, migration) -> None:
        self._migration = migration
        self._kept = kept_defaults(migration.operations)
        self._kept_so_far |= self._kept
        self.new_indexes |= _built_indexes(migration.operations)
        for i, op in enumerate(migration.operations):
            self._operation(migration.app_label, op, str(i))

    def _operation(self, app_label: str, op, path: str) -> None:
        if isinstance(op, migrations.SeparateDatabaseAndState):
            if not _from_django(op):
                self._report_project_class(op, path)
            # database_operations reach the database only. Django evolves a private
            # copy of the state through them; the real state changes through
            # state_operations.
            real, self.state = self.state, self.state.clone()
            for j, db_op in enumerate(op.database_operations):
                self._check_and_apply(app_label, db_op, f"{path}.db.{j}")
            self.state = real
            self._state_only(app_label, op.state_operations, path, op.database_operations)
        elif isinstance(op, migrations.RunSQL):
            # RunSQL(sql, state_operations=[...]) is the same split in one operation.
            self._check(app_label, op, path)
            self._state_only(app_label, op.state_operations, path, [op])
        else:
            self._check_and_apply(app_label, op, path)
            self._track(app_label, op)

    def _check_and_apply(self, app_label: str, op, path: str) -> None:
        if isinstance(op, migrations.RemoveField):
            _key, model_state = self._model(app_label, op.model_name)
            if model_state is not None and op.name not in model_state.fields:
                # A state-only RemoveField earlier in this release took the field out
                # of the state. Django raises KeyError here; report that instead.
                self._report(
                    path,
                    "drop-column",
                    f"RemoveField {op.model_name}.{op.name}: the field is no longer in "
                    "the migration state (a state-only RemoveField removed it), so "
                    "Django cannot run this operation",
                    _table(model_state),
                )
                return
        self._check(app_label, op, path)
        op.state_forwards(app_label, self.state)

    def _state_only(
        self, app_label: str, operations, path: str, database_operations
    ) -> None:
        dropped = _dropped_columns(database_operations)
        for op in operations:
            self._check_state_only(app_label, op, path, dropped)
            self._track(app_label, op)
            op.state_forwards(app_label, self.state)

    def _track(self, app_label: str, op) -> None:
        """Remember what this operation creates, through renames, until it is removed."""
        if isinstance(op, migrations.CreateModel):
            self.new_models.add((app_label, op.name_lower))
        elif isinstance(op, migrations.DeleteModel):
            self.new_models.discard((app_label, op.name_lower))
        elif isinstance(op, migrations.RenameModel):
            old, new = (app_label, op.old_name_lower), (app_label, op.new_name_lower)
            if old in self.new_models:
                self.new_models.discard(old)
                self.new_models.add(new)
            for key, name in [f for f in self.new_fields if f[0] == old]:
                self.new_fields.discard((key, name))
                self.new_fields.add((new, name))
        elif isinstance(op, migrations.AddField):
            self.new_fields.add(((app_label, op.model_name_lower), op.name))
        elif isinstance(op, migrations.RemoveField):
            self.new_fields.discard(((app_label, op.model_name_lower), op.name))
        elif isinstance(op, migrations.RenameField):
            key = (app_label, op.model_name_lower)
            if (key, op.old_name) in self.new_fields:
                self.new_fields.discard((key, op.old_name))
                self.new_fields.add((key, op.new_name))

    # -- the one rule on state-only operations --
    def _check_state_only(self, app_label: str, op, path: str, dropped) -> None:
        if not isinstance(op, migrations.RemoveField):
            return
        key, model_state = self._model(app_label, op.model_name)
        if model_state is None or not self._released_field(key, op.name):
            return
        model_field = model_state.fields[op.name]
        if model_field.many_to_many or model_field.null or model_field.primary_key:
            return
        table, column = _table(model_state), _column(model_field, op.name)
        if (table, column) not in self._kept and (table, column) not in dropped:
            self._report(
                path,
                "state-drop-not-null",
                f"state-only RemoveField {op.model_name}.{op.name} leaves "
                f"{table}.{column} NOT NULL",
            )

    # -- rules on operations that reach the database --
    def _check(self, app_label: str, op, path: str) -> None:
        """Check one operation against the state as it is before the operation."""
        if not _from_django(op):
            self._report_project_class(op, path)
            return
        if isinstance(op, (*SAFE_OPERATIONS, migrations.CreateModel)):
            return  # a new table is never a finding; _track records it
        for operation_class, rule in self._RULES:
            if isinstance(op, operation_class):
                rule(self, app_label, op, path)
                return
        self._report(path, "unclassified-operation", type(op).__qualname__)

    def _report_project_class(self, op, path: str) -> None:
        self._report(
            path,
            "unclassified-operation",
            f"{type(op).__qualname__} is defined outside Django, so the guard cannot "
            "tell what its database_forwards runs",
        )

    def _run_python(self, app_label: str, op, path: str) -> None:
        if op.code is not migrations.RunPython.noop:
            name = getattr(op.code, "__name__", repr(op.code))
            self._report(path, "data-migration", f"RunPython({name})")

    def _add_field(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.model_name)
        new = op.field
        if not self._released_model(key) or new.many_to_many:
            return  # a new table, or a many-to-many (its own new table)
        table, column = _table(model_state), _column(new, op.name)
        where = f"AddField {table}.{column}"
        # db_default arrives with Django 5.0; until then only RunSQL keeps a default.
        has_db_default = getattr(new, "db_default", NOT_PROVIDED) is not NOT_PROVIDED
        if not new.null and not has_db_default and (table, column) not in self._kept:
            self._report(
                path, "add-not-null", f"{where} is NOT NULL, no database default"
            )
        if new.unique and not new.null:
            self._report(path, "add-unique", f"{where} is unique and NOT NULL")
            return
        foreign_key = new.remote_field is not None and getattr(new, "db_constraint", True)
        if new.unique or new.db_index or foreign_key:
            kind = "ForeignKey" if new.remote_field is not None else "index"
            self._report(path, "implicit-index", f"{where} ({kind}) on existing table")

    def _alter_field(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.model_name)
        if not self._released_model(key):
            return
        old, new = model_state.fields[op.name], op.field
        table = _table(model_state)
        if not self._released_field(key, op.name):
            self._alter_new_column(table, old, new, op, path)
        elif old.many_to_many or new.many_to_many:
            self._alter_many_to_many(key, model_state, old, new, op, path)
        else:
            self._alter_released_column(app_label, key, table, old, new, op, path)

    def _alter_new_column(self, table: str, old, new, op, path: str) -> None:
        """A column added earlier in this release. The previous release never writes
        it, so it can only be hurt by a NOT NULL with no default or by an index build.
        """
        if new.many_to_many:
            return
        column = _column(new, op.name)
        # Django ends this AlterField with DROP DEFAULT, so only a default that is
        # set after it survives.
        kept_later = kept_defaults(self._migration.operations, after=path)
        if old.null and not new.null and (table, column) not in kept_later:
            self._report(
                path,
                "add-not-null",
                f"AlterField {table}.{column} (added in this release) becomes "
                "NOT NULL, no database default",
            )
        if (new.unique and not old.unique) or (new.db_index and not old.db_index):
            self._report(
                path, "blocking-index", f"AlterField {table}.{column} gains an index"
            )

    def _alter_many_to_many(self, key: Key, model_state, old, new, op, path: str) -> None:
        before = _auto_m2m_table(model_state, old, op.name) if old.many_to_many else None
        after = _auto_m2m_table(model_state, new, op.name) if new.many_to_many else None
        where = f"AlterField {op.model_name}.{op.name}"
        if before != after:
            self._report(
                path,
                "rename-table",
                f"{where}: many-to-many table {before or '(none)'} becomes {after or '(none)'}",
                before,
            )
        elif before and _target(old, key) != _target(new, key):
            self._report(
                path,
                "rename-column",
                f"{where}: the join column of {before} is renamed for the new target model",
                before,
            )

    def _alter_released_column(
        self, app_label: str, key: Key, table: str, old, new, op, path: str
    ) -> None:
        old_column, new_column = _column(old, op.name), _column(new, op.name)
        where = f"AlterField {table}.{old_column}"
        if old_column != new_column:
            self._report(path, "rename-column", f"{where} becomes {new_column}", table)
        after = self.state.clone()
        op.state_forwards(app_label, after)
        old_type = _column_type(self.state, key, op.name)
        new_type = _column_type(after, key, op.name)
        changes = []
        if old_type != new_type and not _widens(old_type, new_type):
            changes.append(f"{old_type} -> {new_type}")
        # The suffix carries the identity default: BigAutoField -> BigIntegerField keeps
        # the type and drops it, and INSERTs that leave the key out then fail.
        old_suffix = old.db_type_suffix(connection)
        new_suffix = new.db_type_suffix(connection)
        if old_suffix != new_suffix:
            changes.append(
                f"{old_suffix or 'no identity'} -> {new_suffix or 'no identity'}"
            )
        if changes:
            # One finding for both, so that one waiver can answer for the operation.
            self._report(
                path, "alter-column-type", f"{where}: {'; '.join(changes)}", table
            )
        if old.null and not new.null and not new.primary_key:
            self._report(path, "set-not-null", f"{where} becomes NOT NULL", table)
        self._alter_released_constraints(key, old, new, op.name, where, table, path)

    def _alter_released_constraints(
        self, key: Key, old, new, name: str, where: str, table: str, path: str
    ) -> None:
        was_relation = old.remote_field is not None
        is_relation = new.remote_field is not None
        constrained = is_relation and getattr(new, "db_constraint", True)
        if not was_relation and not is_relation:
            # IntegerField -> PositiveIntegerField keeps the type and adds a CHECK.
            old_check = _bound(old, name).db_check(connection)
            new_check = _bound(new, name).db_check(connection)
            if new_check and new_check != old_check:
                self._report(path, "add-constraint", f"{where} gains CHECK ({new_check})")
        elif was_relation and is_relation:
            # Another model, or another unique column of the same model (to_field).
            retargeted = (
                _target(old, key),
                _referenced_field(self.state, old, key),
            ) != (_target(new, key), _referenced_field(self.state, new, key))
            if retargeted or (constrained and not getattr(old, "db_constraint", True)):
                self._report(
                    path, "add-constraint", f"{where}: new foreign key constraint"
                )
        elif constrained:
            self._report(path, "add-constraint", f"{where} becomes a ForeignKey")
        if old.unique and not new.unique and not old.primary_key:
            self._report(path, "drop-unique", f"{where} is no longer unique", table)
        if new.unique and not old.unique:
            self._report(path, "add-unique", f"{where} becomes unique")
        elif new.db_index and not old.db_index and not old.unique:
            self._report(path, "blocking-index", f"{where} gains db_index")

    def _remove_field(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.model_name)
        if not self._released_field(key, op.name):
            return
        model_field = model_state.fields[op.name]
        if not model_field.many_to_many:
            table = _table(model_state)
            self._report(
                path,
                "drop-column",
                f"RemoveField drops {table}.{_column(model_field, op.name)}",
                table,
            )
            return
        through = _auto_m2m_table(model_state, model_field, op.name)
        if through:
            self._report(
                path,
                "drop-table",
                f"RemoveField {op.model_name}.{op.name} drops many-to-many table {through}",
                through,
            )

    def _rename_field(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.model_name)
        if not self._released_field(key, op.old_name):
            return
        model_field = model_state.fields[op.old_name]
        if model_field.many_to_many:
            before = _auto_m2m_table(model_state, model_field, op.old_name)
            after = _auto_m2m_table(model_state, model_field, op.new_name)
            if before != after:
                self._report(
                    path,
                    "rename-table",
                    f"RenameField renames many-to-many table {before} to {after}",
                    before,
                )
            return
        table = _table(model_state)
        before = _column(model_field, op.old_name)
        after = _column(model_field, op.new_name)
        if before != after:
            self._report(
                path,
                "rename-column",
                f"RenameField renames {table}.{before} to {after}",
                table,
            )

    def _delete_model(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.name)
        if self._released_model(key):
            table = _table(model_state)
            self._report(path, "drop-table", f"DeleteModel drops {table}", table)

    def _rename_model(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.old_name)
        if not self._released_model(key):
            return
        before = _table(model_state)
        after = _norm(
            model_state.options.get("db_table")
            or truncate_name(f"{app_label}_{op.new_name_lower}", 63)
        )
        if before != after:
            self._report(
                path, "rename-table", f"RenameModel renames {before} to {after}", before
            )
            return
        # The table keeps its name. Auto-created many-to-many tables still carry a
        # <model>_id column named after the model, which RenameModel renames.
        touches_m2m = any(f.many_to_many for f in model_state.fields.values()) or any(
            f.many_to_many
            and f.remote_field.through is None
            and _target(f, other_key) == key
            for other_key, other in self.state.models.items()
            for f in other.fields.values()
        )
        if touches_m2m:
            self._report(
                path,
                "rename-table",
                f"RenameModel {op.old_name}: renames the {op.old_name_lower}_id column "
                "of its many-to-many tables",
                before,
            )

    def _alter_model_table(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.name)
        if not self._released_model(key):
            return
        before = _table(model_state)
        after = _norm(op.table or truncate_name(f"{app_label}_{op.name_lower}", 63))
        if before != after:
            self._report(
                path,
                "rename-table",
                f"AlterModelTable renames {before} to {after}",
                before,
            )

    def _add_index(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.model_name)
        if self._released_model(key):
            self._report(
                path,
                "blocking-index",
                f"AddIndex {op.index.name} on existing table {_table(model_state)}",
            )

    def _add_constraint(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.model_name)
        if self._released_model(key):
            unique = isinstance(op.constraint, models.UniqueConstraint)
            self._report(
                path,
                "add-unique" if unique else "add-constraint",
                f"AddConstraint {op.constraint.name} on existing table {_table(model_state)}",
            )

    def _remove_constraint(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.model_name)
        if not self._released_model(key):
            return
        for constraint in model_state.options.get("constraints", ()):
            if constraint.name == op.name and isinstance(
                constraint, models.UniqueConstraint
            ):
                table = _table(model_state)
                self._report(
                    path,
                    "drop-unique",
                    f"RemoveConstraint {op.name} on existing table {table}",
                    table,
                )

    def _alter_together(self, app_label: str, op, path: str) -> None:
        key, model_state = self._model(app_label, op.name)
        if not self._released_model(key):
            return
        table = _table(model_state)
        unique = isinstance(op, migrations.AlterUniqueTogether)
        before = {tuple(t) for t in model_state.options.get(op.option_name) or ()}
        after = {tuple(t) for t in op.option_value or ()}
        where = f"{type(op).__name__} on existing table {table}"
        if unique and before - after:
            self._report(
                path, "drop-unique", f"{where} removes {sorted(before - after)}", table
            )
        if after - before:
            self._report(
                path,
                "add-unique" if unique else "blocking-index",
                f"{where} adds {sorted(after - before)}",
            )

    # -- RunSQL --
    def _run_sql(self, app_label: str, op, path: str) -> None:
        for statement in _statements(op.sql):
            self._statement(statement, path)

    def _statement(self, statement: str, path: str) -> None:
        shown = statement if len(statement) <= 90 else statement[:87] + "..."
        detail = f"RunSQL: {shown}"
        bare = _without_literals(statement)
        if "\\" in statement:
            self._report(
                path,
                "raw-sql",
                f"{detail} (a backslash escape: the guard cannot tell where the string ends)",
            )
        elif ";" in bare:
            self._report(
                path,
                "raw-sql",
                f"{detail} (more than one statement: give RunSQL a list with one "
                "statement in each item)",
            )
        elif alter := _ALTER_TABLE.fullmatch(bare):
            for action in _split_actions(alter.group(2)):
                self._alter_table_action(_norm(alter.group(1)), action, detail, path)
        elif index := _CREATE_INDEX.match(bare):
            unique, concurrently = index.group(1), index.group(2)
            table = _norm(index.group(4))
            if table not in self.schema:
                if not self._born_new(table):
                    self._report(path, "raw-sql", _unknown_table(detail, table))
            elif unique:
                self._report(path, "add-unique", detail)
            elif not concurrently:
                self._report(path, "blocking-index", detail)
        elif drop := _DROP_TABLE.fullmatch(bare):
            for item in drop.group(1).split(","):
                self._drop_table(re.fullmatch(_NAME, item.strip()), detail, path)
        elif drop := _DROP_INDEX.fullmatch(bare):
            for item in drop.group(1).split(","):
                self._drop_index(re.fullmatch(_NAME, item.strip()), detail, path)
        elif _DATA.match(bare):
            target = _DATA_TARGET.match(bare)
            # Rows of a table created in this release: the previous release has none.
            if not (target and self._born_new(_norm(target.group(1)))):
                self._report(path, "data-migration", detail)
        elif created := _CREATE_TABLE.match(bare):
            if _norm(created.group(1)) not in self.schema:
                self.new_sql_tables.add(_norm(created.group(1)))
        elif not _HARMLESS.match(bare) and not _read_only_block(statement):
            self._report(path, "raw-sql", detail)

    def _drop_table(self, name: re.Match | None, detail: str, path: str) -> None:
        if name is None:
            self._report(path, "raw-sql", detail)
            return
        table = _norm(name.group(1))
        if not self._born_new(table):
            rule = "drop-table" if table in self.schema else "contract-drop"
            self._report(path, rule, detail, table)

    def _drop_index(self, name: re.Match | None, detail: str, path: str) -> None:
        """DROP INDEX names no table and does not say whether the index is unique. It
        is harmless for an index that this release builds: one it built earlier, or
        one that the same migration builds after the drop (DROP INDEX IF EXISTS
        before CREATE INDEX CONCURRENTLY clears a build that was interrupted).
        """
        if name is None:
            self._report(path, "raw-sql", detail)
            return
        index = _norm(name.group(1))
        if index not in self.new_indexes and index not in self.released_plain_indexes:
            self._report(
                path,
                "drop-unique",
                f"{detail} (the guard cannot tell whether the index is unique)",
            )

    def _alter_table_action(
        self, table: str, action: str, detail: str, path: str
    ) -> None:
        released = self.schema.get(table)  # column -> field; None for any other table
        if drop := _DROP_COLUMN.fullmatch(action):
            column = _norm(drop.group(1))
            if not self._born_new(table, column):
                known = released is not None and column in released
                self._report(
                    path, "drop-column" if known else "contract-drop", detail, table
                )
        elif released is None and not self._born_new(table):
            self._report(path, "raw-sql", _unknown_table(detail, table))
        elif re.match(r"DROP\s+CONSTRAINT\b", action, re.I):
            if released is not None:
                self._report(
                    path,
                    "drop-unique",
                    f"{detail} (the guard cannot tell whether the constraint is unique)",
                    table,
                )
        elif re.match(r"(RENAME|VALIDATE)\s+CONSTRAINT\b", action, re.I):
            pass
        elif _ADD_TABLE_CONSTRAINT.match(action):
            if released is not None:
                unique = re.search(r"\b(UNIQUE|PRIMARY\s+KEY)\b", action, re.I)
                self._report(path, "add-unique" if unique else "add-constraint", detail)
        elif re.match(r"RENAME\s+TO\b", action, re.I):
            if released is not None:
                self._report(path, "rename-table", detail, table)
        elif re.match(r"RENAME\b", action, re.I):
            if released is not None:
                self._report(path, "rename-column", detail, table)
        elif column := _ALTER_COLUMN.fullmatch(action):
            self._alter_column(
                table, _norm(column.group(1)), column.group(2), detail, path
            )
        elif add := _ADD_COLUMN.fullmatch(action):
            # Without quoted names: COLLATE pg_catalog."default" is not a DEFAULT.
            definition = re.sub(r'"[^"]*"', " ", add.group(2))
            not_null = re.search(r"\bNOT\s+NULL\b", definition, re.I)
            default = re.search(r"\bDEFAULT\b", definition, re.I)
            kept = (table, _norm(add.group(1))) in self._kept
            if released is None:
                return  # a table of this release
            if not_null and not default and not kept:
                self._report(path, "add-not-null", detail)
            # A column constraint in the definition, as AddField and AddConstraint.
            if not_null and re.search(r"\b(UNIQUE|PRIMARY\s+KEY)\b", definition, re.I):
                self._report(path, "add-unique", detail)
            if re.search(r"\bCHECK\b", definition, re.I):
                self._report(path, "add-constraint", detail)
        else:
            self._report(path, "raw-sql", detail)

    def _alter_column(
        self, table: str, column: str, change: str, detail: str, path: str
    ) -> None:
        released = self.schema.get(table)
        # The field the previous release declares; None for a column it does not have.
        model_field = (released or {}).get(column)
        if re.match(r"SET\s+NOT\s+NULL\b", change, re.I):
            if model_field is None:
                # A column added in this release: the same hazard as add-not-null.
                if released is not None and (table, column) not in self._kept_so_far:
                    self._report(path, "add-not-null", detail)
            elif model_field.null:
                self._report(path, "set-not-null", detail, table)
            else:
                # The released model already says NOT NULL: the second step of the
                # two-release recipe. Only another writer can still send NULL.
                self._report_if_shared(path, table, detail)
        elif re.match(r"(SET\s+DATA\s+)?TYPE\b", change, re.I):
            if model_field is not None:
                self._report(path, "alter-column-type", detail, table)
        elif not re.match(r"(SET\s+DEFAULT|DROP\s+NOT\s+NULL)\b", change, re.I):
            self._report(path, "raw-sql", detail)
        if _REMOVES_DEFAULT.match(change):
            # Another writer's INSERT may leave the column out and rely on the default.
            self._report_if_shared(path, table, detail)

    # Operation class -> rule, first match wins. A subclass that Django ships gets the
    # rule of its base (AddConstraintNotValid is an AddConstraint).
    _RULES = (
        (migrations.RunPython, _run_python),
        (migrations.RunSQL, _run_sql),
        (migrations.AddField, _add_field),
        (migrations.AlterField, _alter_field),
        (migrations.RemoveField, _remove_field),
        (migrations.RenameField, _rename_field),
        (migrations.DeleteModel, _delete_model),
        (migrations.RenameModel, _rename_model),
        (migrations.AlterModelTable, _alter_model_table),
        (migrations.AddIndex, _add_index),
        (migrations.AddConstraint, _add_constraint),
        (migrations.RemoveConstraint, _remove_constraint),
        (migrations.AlterUniqueTogether, _alter_together),
        (migrations.AlterIndexTogether, _alter_together),
    )


def _target(relation_field, model_key: Key) -> Key:
    """The model a ForeignKey or ManyToManyField points at."""
    return resolve_relation(relation_field.remote_field.model, *model_key)


def _unknown_table(detail: str, table: str) -> str:
    return f"{detail} (no model declares the table {table}, so the guard cannot tell who uses it)"


# ── Public API ─────────────────────────────────────────────────────────────────────


def lint(
    plan: Sequence,
    released: Collection[Key],
    real_apps: Collection[str] = (),
    skip: Collection[Key] = (),
) -> list[Finding]:
    """Check every migration of ``plan`` that is not ``released``.

    ``plan`` is the whole graph in dependency order. ``skip`` names migrations that
    are applied to the state but not checked (third-party ones).
    Raises ValueError when a released migration cannot be applied on top of the other
    released ones, which means it depends on a migration that is not released.
    """
    state = ProjectState(real_apps=set(real_apps))
    for migration in plan:
        if (migration.app_label, migration.name) in released:
            try:
                migration.mutate_state(state, preserve=False)
            except Exception as error:  # noqa: BLE001 - reported as one clear message
                raise ValueError(
                    f"{migration.app_label}.{migration.name} is in a baseline but does "
                    f"not apply on top of the other released migrations ({error!r}). "
                    "A baseline has to list everything its migrations depend on."
                ) from error
    linter = _Linter(state)
    for migration in plan:
        key = (migration.app_label, migration.name)
        if key in released:
            continue
        if key in skip:
            migration.mutate_state(linter.state, preserve=False)
        else:
            linter.migration(migration)
    return linter.findings


def apply_waivers(migration, findings: list[Finding]) -> tuple[list[Finding], list[str]]:
    """Drop waived findings. Returns (remaining findings, problems with the waivers)."""
    waivers = getattr(migration, WAIVER_ATTRIBUTE, None) or []
    label = f"{migration.app_label}.{migration.name}"
    if not isinstance(waivers, (list, tuple)):
        return findings, [f"{label}: {WAIVER_ATTRIBUTE} must be a list of dicts"]
    problems: list[str] = []
    waived: set[tuple[str, str]] = set()
    for waiver in waivers:
        if not isinstance(waiver, dict) or set(waiver) != {"op", "rule", "reason"}:
            problems.append(
                f"{label}: a waiver needs exactly the keys op, rule, reason: {waiver!r}"
            )
            continue
        target = (str(waiver["op"]), waiver["rule"])
        where = f"operations[{target[0]}] {target[1]}"
        reason = waiver["reason"]
        matches = sum((f.op, f.rule) == target for f in findings)
        if waiver["rule"] not in RULES:
            problems.append(f"{label}: unknown rule {waiver['rule']!r} in a waiver")
        elif not isinstance(reason, str) or len(reason.strip()) < MIN_REASON_LENGTH:
            problems.append(
                f"{label}: the waiver for {where} needs a reason of at least "
                f"{MIN_REASON_LENGTH} characters"
            )
        elif reason.strip() == REASON_PLACEHOLDER:
            problems.append(
                f"{label}: the waiver for {where} still has the placeholder; replace "
                "it with the reason"
            )
        elif target in waived:
            problems.append(f"{label}: duplicate waiver for {where}")
        elif matches > 1:
            # One reason cannot answer for two changes, and a statement added to the
            # operation later would be waived without anyone restating it.
            problems.append(
                f"{label}: {where} has {matches} findings and one waiver clears one "
                "finding. Split the operation into one operation per statement"
            )
        elif not matches:
            problems.append(
                f"{label}: the waiver for {where} matches no finding; remove it"
            )
        else:
            waived.add(target)
    return [f for f in findings if (f.op, f.rule) not in waived], problems


# ── The real project: graph, files, baselines ─────────────────────────────────────


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Project:
    """The migrations on disk, split into released and new by the committed baselines."""

    root: Path  # backend/
    plan: list  # every migration, in dependency order
    files: dict[Key, str]  # first-party migration -> path relative to root
    third_party: set[Key]  # migrations of installed packages
    real_apps: set[str] = field(default_factory=set)
    baseline: dict[str, str] = field(default_factory=dict)  # relative path -> sha256
    listed_third_party: dict[Key, str] = field(default_factory=dict)  # -> its baseline
    baseline_files: list[str] = field(default_factory=list)
    problems: list[str] = field(
        default_factory=list
    )  # what is wrong with a baseline file

    @property
    def released(self) -> set[Key]:
        first_party = {key for key, path in self.files.items() if path in self.baseline}
        return first_party | (self.third_party & set(self.listed_third_party))

    @property
    def new(self) -> list:
        """First-party migrations that are not in a baseline, in dependency order."""
        released = self.released
        return [
            m
            for m in self.plan
            if (m.app_label, m.name) in self.files
            and (m.app_label, m.name) not in released
        ]

    def baseline_line(self, path: str) -> str:
        return f"{sha256(self.root / path)}  {path}"

    def add_baseline(self, name: str, text: str) -> None:
        """Read one baseline file. ``name`` is its path relative to root."""
        self.baseline_files.append(name)
        if not RELEASED_THROUGH.search(text):
            self.problems.append(
                f"{name}: no '# released-through: origin/release/X.Y @ <commit>' line. "
                "The file has to be generated from a release branch by "
                "update_migration_baseline.py, not written by hand."
            )
        for number, line in enumerate(text.splitlines(), 1):
            parts = line.split()
            if not parts or parts[0].startswith("#"):
                continue
            if len(parts) != 2:
                self.problems.append(f"{name}:{number}: expected '<sha256>  <path>'")
            elif parts[0] == THIRD_PARTY:
                self.listed_third_party[tuple(parts[1].split(".", 1))] = name
            elif parts[1] in self.baseline:
                self.problems.append(f"{name}:{number}: {parts[1]} is listed twice")
            else:
                self.baseline[parts[1]] = parts[0]


def unreleased_dependencies(
    graph: MigrationGraph, released: Collection[Key]
) -> list[str]:
    """Released migrations that depend on a migration that is not released.

    The previous release's state is built from the released migrations alone, so they
    have to be closed under dependencies. It breaks when a baseline is advanced before
    the baseline of the repository it builds on.
    """
    return [
        f"{key[0]}.{key[1]} is in a baseline but its dependency "
        f"{parent.key[0]}.{parent.key[1]} is not. Advance the baseline that should "
        "list the dependency first."
        for key in sorted(released)
        for parent in sorted(graph.node_map[key].parents)
        if parent.key not in released
    ]


def load_project(backend_root: Path) -> Project:
    # --no-migrations points MIGRATION_MODULES at a mapping that hides every app, so a
    # loader built under it is empty and every check would pass (see
    # dashboard_metrics/tests/test_migration_graph.py).
    with override_settings(MIGRATION_MODULES={}):
        loader = MigrationLoader(None, ignore_no_migrations=True)
    graph = loader.graph
    plan, seen = [], set()
    for leaf in sorted(graph.leaf_nodes()):
        for node in graph.forwards_plan(leaf):
            if node not in seen:
                seen.add(node)
                plan.append(graph.nodes[node])
    files, third_party = {}, set()
    for migration in plan:
        key = (migration.app_label, migration.name)
        path = Path(sys.modules[type(migration).__module__].__file__).resolve()
        if backend_root in path.parents and "site-packages" not in path.parts:
            files[key] = path.relative_to(backend_root).as_posix()
        else:
            third_party.add(key)
    project = Project(backend_root, plan, files, third_party, set(loader.unmigrated_apps))
    for baseline_file in sorted(backend_root.glob(BASELINE_GLOB)):
        name = baseline_file.relative_to(backend_root).as_posix()
        project.add_baseline(name, baseline_file.read_text())
    project.problems += unreleased_dependencies(graph, project.released)
    return project


def migrations_not_loaded(project: Project) -> list[str]:
    """Migration files under the root that are in neither the graph nor a baseline.

    Django loads the migrations of installed apps only. A migration in an app that the
    test settings do not install is neither released nor new, so no rule would see it.
    """
    known = set(project.files.values()) | set(project.baseline)
    found = []
    for directory, subdirectories, names in os.walk(project.root):
        subdirectories[:] = [
            d
            for d in subdirectories
            if not d.startswith(".") and d not in ("site-packages", "node_modules")
        ]
        if Path(directory).name != "migrations":
            continue
        for name in names:
            path = (Path(directory) / name).relative_to(project.root).as_posix()
            if re.fullmatch(r"\d.*\.py", name) and path not in known:
                found.append(path)
    return sorted(found)


def new_migration_problems(project: Project) -> list[str]:
    """Everything that fails the new migrations: findings left after waivers, waivers
    that are wrong, and squashes. Each item is ready to print.
    """
    findings = lint(
        project.plan, project.released, project.real_apps, skip=project.third_party
    )
    problems: list[str] = []
    for migration in project.new:
        key = (migration.app_label, migration.name)
        label, path = f"{key[0]}.{key[1]}", project.files[key]
        if migration.replaces:
            # Django runs a squash in place of the migrations it replaces, and the
            # loader drops those from the graph, so their operations are checked by
            # nothing. That is only sound when they are released already.
            directory = path.rsplit("/", 1)[0]
            unreleased = [
                f"{app}.{name}"
                for app, name in migration.replaces
                if f"{directory}/{name}.py" not in project.baseline
            ]
            if unreleased:
                problems.append(
                    f"{label} replaces migrations that are not released: "
                    f"{', '.join(unreleased)}. Django runs this file in their place and "
                    "nothing has checked them. Remove `replaces` (no database outside "
                    "development has applied them) so it is checked like any new migration."
                )
            else:
                problems.append(
                    f"{label} is a squash of released migrations. It restates released "
                    "history, so list it in the baseline (and remove the lines of the "
                    f"files it deletes):\n    {project.baseline_line(path)}"
                )
            continue
        mine = [f for f in findings if (f.app_label, f.migration) == key]
        remaining, waiver_problems = apply_waivers(migration, mine)
        problems += waiver_problems
        problems += [f"{path}\n{finding.render()}" for finding in remaining]
    return problems
