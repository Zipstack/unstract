"""Guard: new migrations keep the previous release working.

During an upgrade the schema changes while pods of the previous release are still
serving, and rolling back the image puts that release back on the new schema. A
migration that drops or renames something that release uses, or adds a NOT NULL
column with no database default, breaks it. Nothing else catches that: the suite
runs with ``--no-migrations``, and no test runs old code on a new schema.

How it decides what to check
----------------------------
``migration_baseline.txt`` lists the migrations on the newest release branch. Those
are *released*: not checked, and pinned by content hash. Every other first-party
migration is *new*, and ``migration_compat.py`` checks every operation in it.

A finding is cleared by fixing the migration, or by a waiver in the migration
itself (plain data, no import)::

    class Migration(migrations.Migration):
        backward_compat_waivers = [
            {
                "op": "1",
                "rule": "data-migration",
                "reason": "Backfills a table created in this release; older code never reads it.",
            },
        ]

The rules, the recipes and the waiver syntax are in backend/README.md under "Writing
migrations".

DB-free: reads migration files and builds the project state; no connection is opened.
The first two classes run on the real migrations. The rest pin the rules themselves on
migrations built in memory.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from functools import cache
from pathlib import Path
from unittest import mock, skipUnless

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.contrib.postgres.operations import (  # noqa: E402
    AddConstraintNotValid,
    AddIndexConcurrently,
)
from django.db import migrations, models  # noqa: E402
from django.db.migrations.graph import MigrationGraph  # noqa: E402
from django.test import SimpleTestCase  # noqa: E402

from backend.tests import migration_compat as compat  # noqa: E402
from backend.tests import update_migration_baseline as baseline_script  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPDATE = (
    "python backend/backend/tests/update_migration_baseline.py --ref origin/release/X.Y"
)
# The largest release so far carried 18 new migrations. Far more than that means a
# baseline is missing, not that a release is large.
LARGEST_RELEASE = 18
MAX_NEW_MIGRATIONS = 40


@cache
def _project() -> compat.Project:
    return compat.load_project(BACKEND_ROOT)


def baseline_problems(project: compat.Project) -> list[str]:
    """What is wrong with the baselines themselves. No waiver clears any of it."""
    problems = list(project.problems)
    unloaded = compat.migrations_not_loaded(project)
    if unloaded:
        problems.append(
            "These migration files are in neither the migration graph nor a baseline, "
            "so no rule sees them. Their app is not installed in the test settings, or "
            "a squash replaces them. Install the app, or delete the files:\n"
            + "\n".join(f"    {path}" for path in unloaded)
        )
    # A table created by a new migration is exempt from every rule. Without a
    # baseline that exemption covers tables the previous release does use.
    if len(project.new) > MAX_NEW_MIGRATIONS:
        where = Counter(
            project.files[(m.app_label, m.name)].split("/", 1)[0] for m in project.new
        )
        problems.append(
            f"{len(project.new)} migrations are not in a baseline: "
            + ", ".join(f"{count} under {top}/" for top, count in sorted(where.items()))
            + f". Baseline files read: {', '.join(project.baseline_files) or 'none'}. "
            "A baseline is missing or was never generated. The repository that owns "
            f"those directories writes its own: `{UPDATE}` here, and with --repo and "
            "--out for a baseline that another repository keeps (see that script)."
        )
    return problems


def new_migrations_failure(project: compat.Project) -> str | None:
    """The failure text for the new migrations, or None when they are all fine."""
    try:
        problems = compat.new_migration_problems(project)
    except ValueError as error:
        # A released migration does not apply on top of the released ones alone, so
        # there is no released state to check against. The baseline problems say why.
        return (
            "\nThe released migrations do not apply on their own, so new migrations "
            "cannot be checked. Fix the baseline first (test_the_guard_is_not_inert "
            "reports the same):\n" + "\n".join(project.problems or [str(error)])
        )
    if not problems:
        return None
    text = (
        f"\n{len(problems)} problem(s) in new migrations (new = not listed in a "
        "migration_baseline.txt, so not on the newest release branch)."
    )
    if len(project.new) > LARGEST_RELEASE:
        # Only then: for one finding the way out is in the finding, not here.
        text += (
            f"\n{len(project.new)} migrations count as new, more than any release has "
            "carried. If a release branch was cut since the baselines were written, "
            "advance them first; the command is in the header of each "
            f"({', '.join(project.baseline_files)})."
        )
    return text + "\n\n" + "\n\n".join(problems)


class ReleasedMigrationTests(SimpleTestCase):
    """The baseline is intact, so 'new' means what it should. No waiver clears these."""

    def test_the_guard_is_not_inert(self) -> None:
        project = _project()
        self.assertTrue(project.files, "no first-party migrations loaded")
        self.assertTrue(project.baseline, "no migration_baseline.txt found")
        problems = baseline_problems(project)
        if problems:
            self.fail("\n" + "\n".join(problems))

    def test_released_migrations_are_unchanged(self) -> None:
        """A released migration has already run everywhere; an edit never reaches
        those databases, and a fresh install would then differ from an upgraded one.
        """
        project = _project()
        problems = []
        for path, digest in sorted(project.baseline.items()):
            file = BACKEND_ROOT / path
            if not file.is_file():
                problems.append(f"{path}: listed in the baseline but missing")
            elif compat.sha256(file) != digest:
                problems.append(
                    f"{path}: changed after release. Revert it and add a new "
                    "migration. If the edit is deliberate (it only matters to fresh "
                    "installs, and no rule has looked at it), replace its baseline "
                    f"line with:\n    {project.baseline_line(path)}"
                )
        if problems:
            self.fail("\n" + "\n".join(problems))

    def test_third_party_migrations_are_reviewed(self) -> None:
        """A dependency bump can bring a migration that breaks the previous release.
        Nothing can waive it in the package, so it is listed after a human read it.
        """
        project = _project()
        unlisted = sorted(project.third_party - set(project.listed_third_party))
        stale = sorted(set(project.listed_third_party) - project.third_party)
        if unlisted:
            lines = "\n".join(f"    {compat.THIRD_PARTY}  {a}.{n}" for a, n in unlisted)
            self.fail(
                f"\n{len(unlisted)} migration(s) in installed packages are not listed. "
                "Read each one for changes the previous release cannot live with, then "
                "add these lines to the baseline of the repository whose dependencies "
                f"bring the package ({', '.join(project.baseline_files)}):\n{lines}"
            )
        if stale:
            lines = "\n".join(
                f"    {project.listed_third_party[key]}: {compat.THIRD_PARTY}  {key[0]}.{key[1]}"
                for key in stale
            )
            self.fail(
                f"\nthird-party lines for migrations that are gone; remove them:\n{lines}"
            )


class NewMigrationTests(SimpleTestCase):
    def test_new_migrations_keep_the_previous_release_working(self) -> None:
        failure = new_migrations_failure(_project())
        if failure:
            self.fail(failure)


# ── The rules themselves, on migrations built in memory ───────────────────────────


def _migration(name: str, operations: list, app_label: str = "probe", **attrs):
    cls = type("Migration", (migrations.Migration,), {"operations": operations, **attrs})
    return cls(name, app_label)


def _released(*more_operations) -> migrations.Migration:
    """The released migration: tables owner, probe_tag, widget and widget_tags."""
    return _migration(
        "0001_initial",
        [
            migrations.CreateModel(
                "Owner",
                [
                    ("id", models.BigAutoField(primary_key=True)),
                    ("label", models.CharField(max_length=32, default="o")),
                ],
                options={"db_table": "owner"},
            ),
            migrations.CreateModel(
                "Tag", [("id", models.BigAutoField(primary_key=True))]
            ),
            migrations.CreateModel(
                "Widget",
                [
                    ("id", models.BigAutoField(primary_key=True)),
                    ("name", models.CharField(max_length=64)),
                    ("code", models.CharField(max_length=32)),
                    ("note", models.TextField(null=True)),
                    ("weight", models.IntegerField(default=0)),
                    (
                        "owner",
                        models.ForeignKey("probe.Owner", models.CASCADE, null=True),
                    ),
                    ("tags", models.ManyToManyField("probe.Tag")),
                ],
                options={"db_table": "widget"},
            ),
            *more_operations,
        ],
    )


RELEASED = {("probe", "0001_initial")}


def _lint(*operations, released=None, **attrs) -> list[tuple[str, str]]:
    """(op, rule) pairs left after waivers for one new migration on the released one."""
    new = _migration("0002_new", list(operations), **attrs)
    findings = compat.lint([released or _released(), new], RELEASED)
    remaining, problems = compat.apply_waivers(new, findings)
    assert not problems, problems
    return [(f.op, f.rule) for f in remaining]


def _sql(statement: str) -> list[tuple[str, str]]:
    return _lint(migrations.RunSQL(statement))


SET_DEFAULT = 'alter table "widget" alter column "active" set default true'
REASON = "The previous release never reads or writes this."
ADD_ACTIVE = migrations.AddField("widget", "active", models.BooleanField(default=True))
GADGET = migrations.CreateModel(
    "Gadget",
    [
        ("id", models.BigAutoField(primary_key=True)),
        ("label", models.CharField(max_length=8)),
    ],
)


class RuleTests(SimpleTestCase):
    # -- add-not-null and the kept default --
    def test_not_null_column_without_a_database_default(self) -> None:
        self.assertEqual(_lint(ADD_ACTIVE), [("0", "add-not-null")])

    def test_not_null_column_that_keeps_a_database_default(self) -> None:
        """The house pattern (account_v2 0010), lower case and quoted."""
        self.assertEqual(_lint(ADD_ACTIVE, migrations.RunSQL(SET_DEFAULT)), [])
        with_database_default = migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE widget ADD COLUMN active boolean NOT NULL DEFAULT true"
                )
            ],
            state_operations=[ADD_ACTIVE],
        )
        self.assertEqual(_lint(with_database_default), [])
        without = migrations.RunSQL(
            "ALTER TABLE widget ADD COLUMN active boolean NOT NULL"
        )
        self.assertEqual(_lint(without), [("0", "add-not-null")])

    def test_a_default_on_another_column_does_not_count(self) -> None:
        other = migrations.AddField("widget", "size", models.IntegerField(default=1))
        self.assertEqual(
            _lint(ADD_ACTIVE, other, migrations.RunSQL(SET_DEFAULT)),
            [("1", "add-not-null")],
        )
        other_table = migrations.RunSQL(
            "ALTER TABLE owner ALTER COLUMN active SET DEFAULT true"
        )
        self.assertEqual(_lint(ADD_ACTIVE, other_table), [("0", "add-not-null")])

    def test_set_default_null_is_not_a_kept_default(self) -> None:
        null = migrations.RunSQL(
            "ALTER TABLE widget ALTER COLUMN active SET DEFAULT NULL"
        )
        self.assertEqual(_lint(ADD_ACTIVE, null), [("0", "add-not-null")])

    def test_a_comma_inside_a_default_is_not_an_action_separator(self) -> None:
        meta = migrations.AddField("widget", "meta", models.JSONField(default=dict))
        json_default = """ALTER TABLE widget ALTER COLUMN meta SET DEFAULT '{"a": 1, "b": 2}'::jsonb"""
        self.assertEqual(_lint(meta, migrations.RunSQL(json_default)), [])
        zone = migrations.AddField(
            "widget", "tz", models.CharField(max_length=64, default="x")
        )
        text_default = (
            "ALTER TABLE widget ALTER COLUMN tz SET DEFAULT 'Asia/Kolkata, IST'"
        )
        self.assertEqual(_lint(zone, migrations.RunSQL(text_default)), [])

    def test_a_new_column_made_not_null_later_in_the_release(self) -> None:
        add = migrations.AddField("widget", "size", models.IntegerField(null=True))
        tighten = migrations.AlterField("widget", "size", models.IntegerField(default=1))
        self.assertEqual(_lint(add, tighten), [("1", "add-not-null")])
        raw = migrations.RunSQL("ALTER TABLE widget ALTER COLUMN size SET NOT NULL")
        self.assertEqual(_lint(add, raw), [("1", "add-not-null")])
        keep = migrations.RunSQL("ALTER TABLE widget ALTER COLUMN size SET DEFAULT 1")
        self.assertEqual(_lint(add, tighten, keep), [])
        self.assertEqual(_lint(add, keep, raw), [])

    def test_a_default_set_before_the_alterfield_is_dropped_by_it(self) -> None:
        """Django ends an AlterField to NOT NULL with DROP DEFAULT."""
        add = migrations.AddField("widget", "size", models.IntegerField(null=True))
        keep = migrations.RunSQL("ALTER TABLE widget ALTER COLUMN size SET DEFAULT 1")
        tighten = migrations.AlterField("widget", "size", models.IntegerField(default=1))
        self.assertEqual(_lint(add, keep, tighten), [("2", "add-not-null")])
        split = migrations.SeparateDatabaseAndState(database_operations=[tighten, keep])
        self.assertEqual(_lint(add, split), [])

    def test_a_default_kept_by_an_earlier_new_migration_counts_for_set_not_null(
        self,
    ) -> None:
        """Unlike AlterField, a raw SET NOT NULL leaves the default in place."""
        add = _migration(
            "0002_size",
            [
                migrations.AddField("widget", "size", models.IntegerField(null=True)),
                migrations.RunSQL("ALTER TABLE widget ALTER COLUMN size SET DEFAULT 1"),
            ],
        )
        tighten = _migration(
            "0003_size_not_null",
            [migrations.RunSQL("ALTER TABLE widget ALTER COLUMN size SET NOT NULL")],
        )
        self.assertEqual(compat.lint([_released(), add, tighten], RELEASED), [])

    def test_a_django_5_db_default_is_a_kept_default(self) -> None:
        field = models.BooleanField(default=True)
        field.db_default = True  # the attribute Django 5.0 adds; absent on 4.2
        self.assertEqual(_lint(migrations.AddField("widget", "active", field)), [])

    def test_runsql_add_column(self) -> None:
        add = "ALTER TABLE widget ADD COLUMN active boolean"
        self.assertEqual(_sql(add), [])
        self.assertEqual(_sql(f"{add} NOT NULL"), [("0", "add-not-null")])
        self.assertEqual(_sql(f"{add} NOT NULL DEFAULT true"), [])
        self.assertEqual(_sql(f"{add} DEFAULT 'NOT NULL'"), [])
        self.assertEqual(
            _lint(migrations.RunSQL(f"{add} NOT NULL"), migrations.RunSQL(SET_DEFAULT)),
            [],
        )

    def test_nullable_column_is_fine(self) -> None:
        add = migrations.AddField("widget", "seen_at", models.DateTimeField(null=True))
        self.assertEqual(_lint(add), [])

    def test_a_new_many_to_many_adds_a_table_not_a_column(self) -> None:
        owners = migrations.AddField(
            "widget", "owners", models.ManyToManyField("probe.Owner")
        )
        self.assertEqual(_lint(owners), [])

    # -- what a new migration created is exempt --
    def test_a_table_created_by_a_new_migration_is_exempt(self) -> None:
        add = migrations.AddField("gadget", "active", models.BooleanField(default=True))
        index = migrations.AddIndex(
            "gadget", models.Index(fields=["active"], name="g_idx")
        )
        unique = migrations.AddConstraint(
            "gadget", models.UniqueConstraint(fields=["label"], name="g_uq")
        )
        raw = migrations.RunSQL("CREATE INDEX g_label ON probe_gadget (label)")
        drop = migrations.RemoveField("gadget", "active")
        self.assertEqual(_lint(GADGET, add, index, unique, raw, drop), [])
        for statement in (
            "ALTER TABLE probe_gadget ADD CONSTRAINT g_ck CHECK (label <> '')",
            "ALTER TABLE probe_gadget DROP CONSTRAINT g_ck",
            "ALTER TABLE probe_gadget RENAME COLUMN label TO title",
            "ALTER TABLE probe_gadget ALTER COLUMN label TYPE text",
            "ALTER TABLE probe_gadget ALTER COLUMN label SET NOT NULL",
            "ALTER TABLE probe_gadget RENAME TO probe_gizmo",
        ):
            with self.subTest(statement):
                self.assertEqual(_lint(GADGET, migrations.RunSQL(statement)), [])

    def test_a_column_added_by_a_new_migration_may_be_dropped_again(self) -> None:
        add = migrations.AddField("widget", "seen_at", models.DateTimeField(null=True))
        for drop in (
            migrations.RemoveField("widget", "seen_at"),
            migrations.RunSQL("ALTER TABLE widget DROP COLUMN seen_at"),
        ):
            self.assertEqual(_lint(add, drop), [])
        other = migrations.RunSQL("ALTER TABLE widget DROP COLUMN note")
        self.assertEqual(_lint(add, other), [("1", "drop-column")])

    def test_unmanaged_and_proxy_models_have_no_table_to_break(self) -> None:
        released = _released(
            migrations.CreateModel(
                "Report",
                [
                    ("id", models.BigAutoField(primary_key=True)),
                    ("total", models.IntegerField()),
                ],
                options={"managed": False, "db_table": "report_view"},
            ),
            migrations.CreateModel(
                "WidgetProxy", [], options={"proxy": True}, bases=("probe.widget",)
            ),
        )
        operations = [
            migrations.RemoveField("report", "total"),
            migrations.DeleteModel("Report"),
            migrations.DeleteModel("WidgetProxy"),
        ]
        self.assertEqual(_lint(*operations, released=released), [])
        self.assertEqual(
            _lint(migrations.RunSQL("DROP TABLE report_view"), released=released),
            [("0", "contract-drop")],
        )

    def test_a_table_created_by_runsql_is_exempt(self) -> None:
        create = migrations.RunSQL(
            "CREATE TABLE scratch (id bigint PRIMARY KEY, n integer)"
        )
        fill = migrations.RunSQL(
            "INSERT INTO scratch (id, n) SELECT id, weight FROM widget"
        )
        index = migrations.RunSQL("CREATE INDEX scratch_n ON scratch (n)")
        drop = migrations.RunSQL("ALTER TABLE scratch DROP COLUMN n")
        self.assertEqual(_lint(create, fill, index, drop), [])
        # IF NOT EXISTS does not prove the table is new, and neither does naming a
        # table the previous release has.
        maybe = migrations.RunSQL(
            "CREATE TABLE IF NOT EXISTS scratch (id bigint PRIMARY KEY)"
        )
        self.assertEqual(_lint(maybe, index), [("1", "raw-sql")])
        existing = migrations.RunSQL("CREATE TABLE widget (id bigint PRIMARY KEY)")
        self.assertEqual(
            _lint(existing, migrations.RunSQL("ALTER TABLE widget DROP COLUMN code")),
            [("1", "drop-column")],
        )

    def test_a_model_created_through_runsql_state_operations_is_exempt(self) -> None:
        create = migrations.RunSQL(
            "CREATE TABLE probe_gadget (id bigint PRIMARY KEY, label varchar(8) NOT NULL)",
            state_operations=[GADGET],
        )
        add = migrations.AddField("gadget", "active", models.BooleanField(default=True))
        self.assertEqual(_lint(create, add), [])

    def test_a_model_moved_between_apps_keeps_its_released_table(self) -> None:
        """A state-only CreateModel that adopts a released table does not make it new."""
        owner = [
            ("id", models.BigAutoField(primary_key=True)),
            ("label", models.CharField(max_length=32, default="o")),
        ]
        adopt = _migration(
            "0001_adopt_owner",
            [
                migrations.SeparateDatabaseAndState(
                    state_operations=[
                        migrations.CreateModel(
                            "Owner", owner, options={"db_table": "owner"}
                        )
                    ]
                )
            ],
            app_label="probe2",
        )
        moved_out = _migration(
            "0002_owner_moved_out",
            [
                migrations.SeparateDatabaseAndState(
                    state_operations=[
                        migrations.AlterField(
                            "widget",
                            "owner",
                            models.ForeignKey("probe2.Owner", models.CASCADE, null=True),
                        ),
                        migrations.DeleteModel("Owner"),
                    ]
                )
            ],
        )
        change = _migration(
            "0002_owner_region",
            [
                migrations.AddField(
                    "owner", "region", models.CharField(max_length=8, default="in")
                ),
                migrations.RemoveField("owner", "label"),
                migrations.RunSQL("ALTER TABLE owner DROP COLUMN label"),
                migrations.RunSQL("UPDATE owner SET label = 'x'"),
                migrations.RunSQL("DROP TABLE owner"),
            ],
            app_label="probe2",
        )
        findings = compat.lint([_released(), adopt, moved_out, change], RELEASED)
        self.assertEqual(
            [(f.migration, f.op, f.rule) for f in findings],
            [
                ("0002_owner_region", "0", "add-not-null"),
                ("0002_owner_region", "1", "drop-column"),
                ("0002_owner_region", "2", "drop-column"),
                ("0002_owner_region", "3", "data-migration"),
                ("0002_owner_region", "4", "drop-table"),
            ],
        )

    def test_a_through_model_that_adopts_the_many_to_many_table_is_released(self) -> None:
        through = [
            ("id", models.BigAutoField(primary_key=True)),
            ("widget", models.ForeignKey("probe.Widget", models.CASCADE)),
            ("tag", models.ForeignKey("probe.Tag", models.CASCADE)),
        ]
        to_through = migrations.AlterField(
            "widget",
            "tags",
            models.ManyToManyField("probe.Tag", through="probe.WidgetTag"),
        )
        adopt = migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    "WidgetTag", through, options={"db_table": "widget_tags"}
                ),
                to_through,
            ]
        )
        add = migrations.AddField(
            "widgettag", "added_by", models.CharField(max_length=32, default="system")
        )
        self.assertEqual(_lint(adopt, add), [("1", "add-not-null")])
        # The table now belongs to the through model, not to the field.
        self.assertEqual(_lint(adopt, migrations.RemoveField("widget", "tags")), [])
        # Django's own how-to renames the table instead. Old pods lose it at once;
        # the column added afterwards is on a table they never see.
        rename = migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL("ALTER TABLE widget_tags RENAME TO probe_widgettag")
            ],
            state_operations=[migrations.CreateModel("WidgetTag", through), to_through],
        )
        self.assertEqual(_lint(rename, add), [("0.db.0", "rename-table")])

    # -- set-not-null --
    def test_set_not_null(self) -> None:
        alter = migrations.AlterField("widget", "note", models.TextField())
        self.assertEqual(_lint(alter), [("0", "set-not-null")])
        self.assertEqual(
            _sql("ALTER TABLE widget ALTER COLUMN note SET NOT NULL"),
            [("0", "set-not-null")],
        )
        self.assertEqual(_sql("ALTER TABLE widget ALTER COLUMN note DROP NOT NULL"), [])

    def test_the_two_release_not_null(self) -> None:
        """Release 1 changes the model and keeps a default; release 2 sets NOT NULL."""
        release_1 = _migration(
            "0002_note_required",
            [
                migrations.SeparateDatabaseAndState(
                    state_operations=[
                        migrations.AlterField(
                            "widget", "note", models.TextField(default="")
                        )
                    ],
                    database_operations=[
                        migrations.RunSQL(
                            "ALTER TABLE widget ALTER COLUMN note SET DEFAULT ''"
                        )
                    ],
                )
            ],
        )
        release_2 = _migration(
            "0003_note_not_null",
            [migrations.RunSQL("ALTER TABLE widget ALTER COLUMN note SET NOT NULL")],
        )
        plan = [_released(), release_1, release_2]
        same_release = compat.lint(plan, RELEASED)
        self.assertEqual(
            [(f.migration, f.rule) for f in same_release],
            [("0003_note_not_null", "set-not-null")],
        )
        next_release = compat.lint(plan, RELEASED | {("probe", "0002_note_required")})
        self.assertEqual(next_release, [])

    # -- drops --
    def test_drop_column_and_drop_table(self) -> None:
        self.assertEqual(
            _lint(migrations.RemoveField("widget", "code")), [("0", "drop-column")]
        )
        self.assertEqual(
            _lint(migrations.RemoveField("widget", "tags")), [("0", "drop-table")]
        )
        self.assertEqual(_lint(migrations.DeleteModel("Owner")), [("0", "drop-table")])
        self.assertEqual(
            _sql("alter table widget drop column code"), [("0", "drop-column")]
        )
        self.assertEqual(
            _sql('ALTER TABLE IF EXISTS ONLY public."widget" DROP "code" RESTRICT'),
            [("0", "drop-column")],
        )
        self.assertEqual(_sql("drop table if exists widget_tags"), [("0", "drop-table")])

    def test_the_two_release_drop(self) -> None:
        """Release 1 removes the field from the state; release 2 may drop the column."""
        state_only = migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveField("widget", "code")],
            database_operations=[
                migrations.RunSQL("ALTER TABLE widget ALTER COLUMN code DROP NOT NULL")
            ],
        )
        self.assertEqual(_lint(state_only), [])
        forgot = migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveField("widget", "code")]
        )
        self.assertEqual(_lint(forgot), [("0", "state-drop-not-null")])
        nullable = migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveField("widget", "note")]
        )
        self.assertEqual(_lint(nullable), [])
        # Same release: the released models still have the column.
        drop = migrations.RunSQL("ALTER TABLE widget DROP COLUMN code")
        self.assertEqual(_lint(state_only, drop), [("1", "drop-column")])
        # Next release: the state-only migration is released too.
        release_1 = _migration("0002_forget_code", [state_only])
        release_2 = _migration("0003_drop_code", [drop])
        findings = compat.lint(
            [_released(), release_1, release_2],
            RELEASED | {("probe", "0002_forget_code")},
        )
        self.assertEqual([(f.op, f.rule) for f in findings], [("0", "contract-drop")])

    def test_state_only_removal_through_runsql_state_operations(self) -> None:
        forgot = migrations.RunSQL(
            migrations.RunSQL.noop,
            state_operations=[migrations.RemoveField("widget", "code")],
        )
        self.assertEqual(_lint(forgot), [("0", "state-drop-not-null")])
        relaxed = migrations.RunSQL(
            "ALTER TABLE widget ALTER COLUMN code DROP NOT NULL",
            state_operations=[migrations.RemoveField("widget", "code")],
        )
        self.assertEqual(_lint(relaxed), [])

    def test_a_database_removefield_after_a_state_only_one_is_a_finding(self) -> None:
        """Django raises KeyError on that migration; the guard reports it and goes on."""
        state_only = migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveField("widget", "note")]
        )
        database_only = migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RemoveField("widget", "note")]
        )
        later = migrations.RemoveField("widget", "code")
        self.assertEqual(
            _lint(state_only, database_only, later),
            [("1.db.0", "drop-column"), ("2", "drop-column")],
        )
        plain = migrations.RemoveField("widget", "note")
        self.assertEqual(_lint(state_only, plain), [("1", "drop-column")])

    def test_runsql_drop_table_checks_every_name_in_the_list(self) -> None:
        scratch = migrations.CreateModel(
            "Scratch", [("id", models.BigAutoField(primary_key=True))]
        )
        drop = migrations.RunSQL(
            "DROP TABLE IF EXISTS probe_scratch, widget_tags CASCADE"
        )
        forget = migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel("Scratch")]
        )
        self.assertEqual(_lint(scratch, drop, forget), [("1", "drop-table")])
        self.assertEqual(
            _sql("DROP TABLE left_behind, widget"),
            [("0", "contract-drop"), ("0", "drop-table")],
        )
        self.assertEqual(_sql("DROP TABLE (widget)"), [("0", "raw-sql")])

    # -- renames --
    def test_renames(self) -> None:
        self.assertEqual(
            _lint(migrations.RenameField("widget", "code", "sku")),
            [("0", "rename-column")],
        )
        self.assertEqual(
            _lint(migrations.RenameField("widget", "tags", "labels")),
            [("0", "rename-table")],
        )
        self.assertEqual(
            _lint(migrations.AlterModelTable("widget", "gizmo")), [("0", "rename-table")]
        )
        self.assertEqual(_lint(migrations.AlterModelTable("widget", "widget")), [])
        self.assertEqual(
            _lint(migrations.RenameModel("Tag", "Label")), [("0", "rename-table")]
        )
        # Renamed in Python only: Meta.db_table pins the table name.
        self.assertEqual(_lint(migrations.RenameModel("Owner", "Holder")), [])
        # The table keeps its name, but widget_tags.widget_id would be renamed.
        self.assertEqual(
            _lint(migrations.RenameModel("Widget", "Gizmo")), [("0", "rename-table")]
        )
        # Renamed in Python only: the column keeps its name.
        keep = migrations.AlterField(
            "widget", "code", models.CharField(max_length=32, db_column="code")
        )
        self.assertEqual(_lint(keep, migrations.RenameField("widget", "code", "sku")), [])
        move = migrations.AlterField(
            "widget", "code", models.CharField(max_length=32, db_column="sku")
        )
        self.assertEqual(_lint(move), [("0", "rename-column")])
        self.assertEqual(
            _sql("alter table widget rename code to sku"), [("0", "rename-column")]
        )
        self.assertEqual(
            _sql("ALTER TABLE widget RENAME TO gizmo"), [("0", "rename-table")]
        )
        self.assertEqual(_sql("ALTER TABLE widget RENAME CONSTRAINT a TO b"), [])

    def test_a_state_only_rename_does_not_hide_a_released_table(self) -> None:
        rename = migrations.SeparateDatabaseAndState(
            state_operations=[migrations.AlterModelTable("widget", "gizmo")]
        )
        self.assertEqual(_lint(rename, ADD_ACTIVE), [("1", "add-not-null")])

    def test_alterfield_that_retargets_a_many_to_many(self) -> None:
        """The auto table keeps its name; its tag_id column becomes owner_id."""
        retarget = migrations.AlterField(
            "widget", "tags", models.ManyToManyField("probe.Owner")
        )
        self.assertEqual(_lint(retarget), [("0", "rename-column")])
        renamed = migrations.AlterField(
            "widget",
            "tags",
            models.ManyToManyField("probe.Tag", db_table="widget_labels"),
        )
        self.assertEqual(_lint(renamed), [("0", "rename-table")])
        same = migrations.AlterField(
            "widget", "tags", models.ManyToManyField("probe.Tag", blank=True)
        )
        self.assertEqual(_lint(same), [])

    # -- types --
    def test_type_changes(self) -> None:
        narrow = migrations.AlterField("widget", "name", models.CharField(max_length=16))
        self.assertEqual(_lint(narrow), [("0", "alter-column-type")])
        retype = migrations.AlterField("widget", "weight", models.CharField(max_length=8))
        self.assertEqual(_lint(retype), [("0", "alter-column-type")])
        for wider in (models.CharField(max_length=255), models.TextField()):
            self.assertEqual(_lint(migrations.AlterField("widget", "name", wider)), [])
        cosmetic = migrations.AlterField(
            "widget", "name", models.CharField(max_length=64, help_text="shown in lists")
        )
        self.assertEqual(_lint(cosmetic), [])
        self.assertEqual(
            _sql(
                "ALTER TABLE widget ALTER weight SET DATA TYPE bigint USING weight::bigint"
            ),
            [("0", "alter-column-type")],
        )

    def test_alterfield_that_drops_the_identity_default(self) -> None:
        """BigAutoField to BigIntegerField keeps bigint and drops the identity."""
        plain_key = migrations.AlterField(
            "widget", "id", models.BigIntegerField(primary_key=True)
        )
        self.assertEqual(_lint(plain_key), [("0", "alter-column-type")])

    # -- constraints --
    def test_unique_and_constraints(self) -> None:
        unique = migrations.AlterField(
            "widget", "code", models.CharField(max_length=32, unique=True)
        )
        self.assertEqual(_lint(unique), [("0", "add-unique")])
        constraint = migrations.AddConstraint(
            "widget", models.UniqueConstraint(fields=["name", "code"], name="w_uq")
        )
        self.assertEqual(_lint(constraint), [("0", "add-unique")])
        together = migrations.AlterUniqueTogether("widget", {("name", "code")})
        self.assertEqual(_lint(together), [("0", "add-unique")])
        check = migrations.AddConstraint(
            "widget", models.CheckConstraint(check=models.Q(weight__gte=0), name="w_ck")
        )
        self.assertEqual(_lint(check), [("0", "add-constraint")])
        to_foreign_key = migrations.AlterField(
            "widget",
            "weight",
            models.ForeignKey(
                "probe.Owner", models.CASCADE, db_column="weight", db_index=False
            ),
        )
        self.assertEqual(
            _lint(to_foreign_key), [("0", "alter-column-type"), ("0", "add-constraint")]
        )
        serial = migrations.AddField(
            "widget", "serial", models.CharField(default="", max_length=8, unique=True)
        )
        self.assertEqual(_lint(serial), [("0", "add-not-null"), ("0", "add-unique")])

    def test_alterfield_that_adds_a_check_constraint(self) -> None:
        """IntegerField to PositiveIntegerField keeps integer and adds CHECK (>= 0)."""
        positive = migrations.AlterField(
            "widget", "weight", models.PositiveIntegerField(default=0)
        )
        self.assertEqual(_lint(positive), [("0", "add-constraint")])

    def test_alterfield_that_points_a_foreign_key_at_another_table(self) -> None:
        retarget = migrations.AlterField(
            "widget", "owner", models.ForeignKey("probe.Tag", models.CASCADE, null=True)
        )
        self.assertEqual(_lint(retarget), [("0", "add-constraint")])
        loose = migrations.AlterField(
            "widget",
            "owner",
            models.ForeignKey(
                "probe.Owner", models.CASCADE, null=True, db_constraint=False
            ),
        )
        tight = migrations.AlterField(
            "widget", "owner", models.ForeignKey("probe.Owner", models.CASCADE, null=True)
        )
        self.assertEqual(_lint(loose, tight), [("1", "add-constraint")])

    def test_runsql_table_constraint_without_the_constraint_keyword(self) -> None:
        self.assertEqual(
            _sql("ALTER TABLE widget ADD UNIQUE (code)"), [("0", "add-unique")]
        )
        self.assertEqual(
            _sql("ALTER TABLE widget ADD PRIMARY KEY (code)"), [("0", "add-unique")]
        )
        for constraint in (
            "CHECK (weight >= 0)",
            "FOREIGN KEY (weight) REFERENCES owner (id)",
            "EXCLUDE USING gist (name WITH =)",
            "CONSTRAINT w_ck CHECK (code <> 'UNIQUE')",
        ):
            with self.subTest(constraint):
                self.assertEqual(
                    _sql(f"ALTER TABLE widget ADD {constraint}"),
                    [("0", "add-constraint")],
                )
        self.assertEqual(
            _sql("ALTER TABLE widget ADD CONSTRAINT w_uq UNIQUE (name, code)"),
            [("0", "add-unique")],
        )
        self.assertEqual(_sql("ALTER TABLE widget VALIDATE CONSTRAINT w_ck"), [])
        self.assertEqual(
            _sql("ALTER TABLE widget DROP CONSTRAINT w_uq CASCADE"),
            [("0", "drop-unique")],
        )
        # Not a column called "constraint" dropped with RESTRICT.
        self.assertEqual(
            _sql("ALTER TABLE widget DROP CONSTRAINT restrict"), [("0", "drop-unique")]
        )

    def test_dropping_a_unique_constraint(self) -> None:
        """Previous-release code that names it in ON CONFLICT then fails."""
        released = _released(
            migrations.AlterUniqueTogether("widget", {("name", "code")}),
            migrations.AddConstraint(
                "widget", models.UniqueConstraint(fields=["code"], name="w_code_uq")
            ),
            migrations.AddConstraint(
                "widget",
                models.CheckConstraint(check=models.Q(weight__gte=0), name="w_ck"),
            ),
            migrations.AlterField(
                "widget", "name", models.CharField(max_length=64, unique=True)
            ),
        )
        for label, operation in (
            (
                "unique_together set removed",
                migrations.AlterUniqueTogether("widget", set()),
            ),
            ("RemoveConstraint", migrations.RemoveConstraint("widget", "w_code_uq")),
            (
                "unique=True dropped",
                migrations.AlterField("widget", "name", models.CharField(max_length=64)),
            ),
            (
                "DROP CONSTRAINT",
                migrations.RunSQL("ALTER TABLE widget DROP CONSTRAINT w_code_uq"),
            ),
        ):
            with self.subTest(label):
                self.assertEqual(
                    _lint(operation, released=released), [("0", "drop-unique")]
                )
        not_unique = migrations.RemoveConstraint("widget", "w_ck")
        self.assertEqual(_lint(not_unique, released=released), [])
        indexed = _released(migrations.AlterIndexTogether("widget", {("name", "code")}))
        unindex = migrations.AlterIndexTogether("widget", set())
        self.assertEqual(_lint(unindex, released=indexed), [])
        swap = migrations.AlterUniqueTogether("widget", {("name", "note")})
        self.assertEqual(
            _lint(swap, released=released), [("0", "drop-unique"), ("0", "add-unique")]
        )

    # -- indexes --
    def test_indexes(self) -> None:
        index = models.Index(fields=["name"], name="w_name_idx")
        self.assertEqual(
            _lint(migrations.AddIndex("widget", index)), [("0", "blocking-index")]
        )
        self.assertEqual(_lint(AddIndexConcurrently("widget", index), atomic=False), [])
        self.assertEqual(
            _lint(migrations.AlterIndexTogether("widget", {("name", "code")})),
            [("0", "blocking-index")],
        )
        indexed = migrations.AlterField(
            "widget", "code", models.CharField(max_length=32, db_index=True)
        )
        self.assertEqual(_lint(indexed), [("0", "blocking-index")])
        self.assertEqual(
            _sql("create index w_name_idx on widget (name)"), [("0", "blocking-index")]
        )
        self.assertEqual(
            _sql("CREATE INDEX CONCURRENTLY IF NOT EXISTS w_name_idx ON widget (name)"),
            [],
        )
        self.assertEqual(
            _sql("CREATE UNIQUE INDEX CONCURRENTLY w_name_uq ON widget (name)"),
            [("0", "add-unique")],
        )
        foreign_key = migrations.AddField(
            "widget",
            "keeper",
            models.ForeignKey("probe.Owner", models.CASCADE, null=True),
        )
        self.assertEqual(_lint(foreign_key), [("0", "implicit-index")])
        unconstrained = migrations.AddField(
            "widget",
            "keeper",
            models.ForeignKey(
                "probe.Owner",
                models.CASCADE,
                null=True,
                db_constraint=False,
                db_index=False,
            ),
        )
        self.assertEqual(_lint(unconstrained), [])
        unindexed = migrations.AddField(
            "widget",
            "keeper",
            models.ForeignKey("probe.Owner", models.CASCADE, null=True, db_index=False),
        )
        self.assertEqual(_lint(unindexed), [("0", "implicit-index")])
        unique = migrations.AddField(
            "widget", "token", models.CharField(max_length=8, null=True, unique=True)
        )
        self.assertEqual(_lint(unique), [("0", "implicit-index")])
        indexed_column = migrations.AddField(
            "widget", "batch", models.IntegerField(null=True, db_index=True)
        )
        self.assertEqual(_lint(indexed_column), [("0", "implicit-index")])

    def test_an_index_gained_by_a_column_of_this_release(self) -> None:
        """The column is new, but the build still blocks writes to the released table."""
        sku = migrations.AddField(
            "widget", "sku", models.CharField(max_length=8, null=True)
        )
        unique = migrations.AlterField(
            "widget", "sku", models.CharField(max_length=8, null=True, unique=True)
        )
        batch = migrations.AddField("widget", "batch", models.IntegerField(null=True))
        indexed = migrations.AlterField(
            "widget", "batch", models.IntegerField(null=True, db_index=True)
        )
        self.assertEqual(
            _lint(sku, unique, batch, indexed),
            [("1", "blocking-index"), ("3", "blocking-index")],
        )
        wider = migrations.AlterField(
            "widget", "sku", models.CharField(max_length=16, null=True)
        )
        self.assertEqual(_lint(sku, wider), [])

    # -- data and raw SQL --
    def test_data_migrations_and_raw_sql(self) -> None:
        def backfill(apps, schema_editor):  # pragma: no cover - never run
            pass

        self.assertEqual(
            _lint(migrations.RunPython(backfill, migrations.RunPython.noop)),
            [("0", "data-migration")],
        )
        self.assertEqual(_lint(migrations.RunPython(migrations.RunPython.noop)), [])
        self.assertEqual(
            _sql("update widget set weight = 0 where weight is null"),
            [("0", "data-migration")],
        )
        self.assertEqual(
            _sql("CREATE RULE r AS ON UPDATE TO widget DO INSTEAD NOTHING"),
            [("0", "raw-sql")],
        )
        self.assertEqual(
            _sql("ALTER TABLE widget ALTER COLUMN code DROP DEFAULT"), [("0", "raw-sql")]
        )
        self.assertEqual(
            _sql("ALTER TABLE widget ENABLE ROW LEVEL SECURITY"), [("0", "raw-sql")]
        )
        for harmless in (
            "CREATE EXTENSION IF NOT EXISTS pg_trgm",
            "COMMENT ON TABLE widget IS 'things; and more'",
            "SET LOCAL lock_timeout = '5s'",
            "SET statement_timeout = 0",
        ):
            with self.subTest(harmless):
                self.assertEqual(_sql(harmless), [])

    def test_runsql_is_read_in_every_form_django_accepts(self) -> None:
        drop = [("0", "drop-column")]
        for sql in (
            '  alter   TABLE \n\t"widget"  /* why */ drop  -- soon\n column "code" ;',
            ["ALTER TABLE widget DROP COLUMN code"],
            [("ALTER TABLE widget DROP COLUMN code", None)],
            ("ALTER TABLE widget DROP COLUMN code",),
            ("COMMENT ON TABLE widget IS 'x'", "ALTER TABLE widget DROP COLUMN code"),
        ):
            with self.subTest(sql=sql):
                self.assertEqual(_lint(migrations.RunSQL(sql)), drop)
        both = migrations.RunSQL(["ALTER TABLE widget DROP COLUMN code", "SELECT 1"])
        self.assertEqual(_lint(both), [("0", "drop-column"), ("0", "raw-sql")])
        self.assertEqual(_lint(migrations.RunSQL(migrations.RunSQL.noop)), [])

    def test_a_long_statement_is_shortened_in_the_message(self) -> None:
        statement = f"UPDATE widget SET note = '{'x' * 200}'"
        new = _migration("0002_new", [migrations.RunSQL(statement)])
        [finding] = compat.lint([_released(), new], RELEASED)
        self.assertEqual(finding.detail, f"RunSQL: {statement[:87]}...")
        short = "UPDATE widget SET note = 'x'"
        new = _migration("0002_new", [migrations.RunSQL(short)])
        self.assertEqual(
            compat.lint([_released(), new], RELEASED)[0].detail, f"RunSQL: {short}"
        )

    def test_a_do_block_may_only_read_and_raise(self) -> None:
        check = (
            "DO $$ BEGIN IF %s THEN RAISE EXCEPTION 'run DROP INDEX x'; END IF; END $$;"
        )
        self.assertEqual(_sql(check % "false"), [])
        self.assertEqual(
            _sql("DO $$ BEGIN EXECUTE 'DROP TABLE widget'; END $$"), [("0", "raw-sql")]
        )
        self.assertEqual(
            _sql("DO $$ BEGIN ALTER TABLE widget DROP COLUMN note; END $$"),
            [("0", "raw-sql")],
        )
        for write in (
            "ALTER TABLE widget RENAME TO gizmo",
            "CREATE INDEX w_name_idx ON widget (name)",
            "DROP TABLE widget",
            "UPDATE widget SET weight = 0",
            "INSERT INTO widget (name) VALUES (1)",
            "DELETE FROM widget",
            "TRUNCATE widget",
            "EXECUTE format(%L, 1)",
            "PERFORM tidy()",
            "CALL tidy()",
            "GRANT SELECT ON widget TO PUBLIC",
            "REVOKE SELECT ON widget FROM PUBLIC",
        ):
            with self.subTest(write):
                self.assertEqual(_sql(f"DO $$ BEGIN {write}; END $$"), [("0", "raw-sql")])
        # The body is code even when it is written as a quoted string.
        self.assertEqual(
            _sql("DO 'BEGIN ALTER TABLE widget DROP COLUMN note; END'"),
            [("0", "raw-sql")],
        )

    def test_runsql_data_change_on_a_table_of_this_release(self) -> None:
        """The previous release has no rows there to read."""
        for statement in (
            "INSERT INTO probe_gadget (label) VALUES ('a')",
            'insert into public."probe_gadget" (label) select name from widget',
            "UPDATE ONLY probe_gadget SET label = 'b'",
            "DELETE FROM probe_gadget WHERE label = 'b'",
        ):
            with self.subTest(statement):
                self.assertEqual(_lint(GADGET, migrations.RunSQL(statement)), [])
        for statement in (
            "INSERT INTO widget (name) SELECT label FROM probe_gadget",
            "TRUNCATE probe_gadget, widget",
            "WITH gone AS (DELETE FROM widget RETURNING *) INSERT INTO probe_gadget SELECT 1",
        ):
            with self.subTest(statement):
                self.assertEqual(
                    _lint(GADGET, migrations.RunSQL(statement)), [("1", "data-migration")]
                )

    def test_runsql_on_a_table_no_model_declares(self) -> None:
        """Another service's table, or one left behind by a state-only DeleteModel."""
        for statement in (
            "ALTER TABLE stranger ADD COLUMN tier integer NOT NULL",
            "ALTER TABLE stranger RENAME COLUMN name TO title",
            "ALTER TABLE stranger RENAME TO outsider",
            "ALTER TABLE stranger ALTER COLUMN name TYPE integer USING 0",
            "ALTER TABLE stranger ALTER COLUMN name SET NOT NULL",
            "ALTER TABLE stranger ADD CONSTRAINT u UNIQUE (name)",
            "ALTER TABLE stranger DROP CONSTRAINT u",
            "CREATE UNIQUE INDEX u ON stranger (name)",
            "CREATE INDEX CONCURRENTLY i ON stranger (name)",
        ):
            with self.subTest(statement):
                self.assertEqual(_sql(statement), [("0", "raw-sql")])
        self.assertEqual(
            _sql("ALTER TABLE stranger DROP COLUMN name"), [("0", "contract-drop")]
        )

    def test_runsql_bracket_inside_a_string_does_not_hide_the_next_action(self) -> None:
        statement = "ALTER TABLE widget ALTER COLUMN code SET DEFAULT 'n/a (unset', DROP COLUMN note"
        self.assertEqual(_sql(statement), [("0", "drop-column")])
        dollars = "ALTER TABLE widget ALTER COLUMN code SET DEFAULT '$$', DROP COLUMN note, ALTER COLUMN name SET DEFAULT '$$'"
        self.assertEqual(_sql(dollars), [("0", "drop-column")])

    def test_runsql_with_a_backslash_escape_is_not_trusted(self) -> None:
        """E'it\\'s' ends where the guard does not expect, hiding the ALTER TABLE."""
        block = r"""
            DO $$
            BEGIN
                RAISE NOTICE E'widget: it\'s being tidied';
                ALTER TABLE widget DROP COLUMN note;
                RAISE NOTICE 'done';
            END $$
        """
        self.assertEqual(_sql(block), [("0", "raw-sql")])

    def test_runsql_that_the_splitter_left_joined_is_not_trusted(self) -> None:
        """sqlparse does not split after a CREATE TABLE with a column named begin."""
        joined = """
            CREATE TABLE probe_window (id bigint PRIMARY KEY, begin timestamptz, finish timestamptz);
            ALTER TABLE widget DROP COLUMN note;
        """
        self.assertEqual(_sql(joined), [("0", "raw-sql")])
        separate = "COMMENT ON TABLE widget IS 'x'; ALTER TABLE widget DROP COLUMN note"
        self.assertEqual(_sql(separate), [("0", "drop-column")])

    def test_database_operations_are_checked(self) -> None:
        split = migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL("ALTER TABLE widget DROP COLUMN code")
            ],
            state_operations=[migrations.RemoveField("widget", "code")],
        )
        self.assertEqual(_lint(split), [("0.db.0", "drop-column")])
        # The same split with Django operations on both sides: the database side
        # works on its own copy of the state, so the state side still finds the field.
        both = migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RemoveField("widget", "note")],
            state_operations=[migrations.RemoveField("widget", "note")],
        )
        self.assertEqual(_lint(both), [("0.db.0", "drop-column")])

    # -- found by the independent verification --
    def test_a_state_only_addfield_does_not_make_a_released_column_new(self) -> None:
        """A foreign key detached state-only keeps its column; the column is released."""
        detach = migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField("widget", "owner"),
                migrations.AddField(
                    "widget", "owner_id", models.BigIntegerField(null=True)
                ),
            ]
        )
        for label, operation, finding in (
            ("RemoveField", migrations.RemoveField("widget", "owner_id"), "drop-column"),
            (
                "AlterField",
                migrations.AlterField(
                    "widget", "owner_id", models.CharField(max_length=8, null=True)
                ),
                "alter-column-type",
            ),
            (
                "RenameField",
                migrations.RenameField("widget", "owner_id", "keeper_id"),
                "rename-column",
            ),
            (
                "RunSQL",
                migrations.RunSQL("ALTER TABLE widget DROP COLUMN owner_id"),
                "drop-column",
            ),
        ):
            with self.subTest(label):
                self.assertEqual(_lint(detach, operation), [("1", finding)])
        # A state-only RemoveField taken back later in the release.
        forget = migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveField("widget", "note")]
        )
        recall = migrations.RunSQL(
            migrations.RunSQL.noop,
            state_operations=[
                migrations.AddField("widget", "note", models.TextField(null=True))
            ],
        )
        self.assertEqual(
            _lint(forget, recall, migrations.RemoveField("widget", "note")),
            [("2", "drop-column")],
        )
        labels = migrations.AddField(
            "widget", "labels", models.ManyToManyField("probe.Tag", related_name="+")
        )
        self.assertEqual(_lint(labels, migrations.RemoveField("widget", "labels")), [])
        # A many-to-many is its own new table, even under the name of an old column.
        note = migrations.AddField("widget", "note", models.ManyToManyField("probe.Tag"))
        self.assertEqual(
            _lint(forget, note, migrations.RemoveField("widget", "note")), []
        )
        # A column that a new migration did create stays exempt, by either name.
        size = migrations.AddField("widget", "size", models.IntegerField(null=True))
        for drop in (
            migrations.RemoveField("widget", "size"),
            migrations.RunSQL("ALTER TABLE widget DROP COLUMN size"),
        ):
            self.assertEqual(_lint(size, drop), [])

    def test_new_fields_are_followed_through_renames(self) -> None:
        size = migrations.AddField("owner", "size", models.IntegerField(null=True))
        self.assertEqual(
            _lint(
                size,
                migrations.RenameModel("Owner", "Holder"),
                migrations.RemoveField("holder", "size"),
            ),
            [],
        )
        self.assertEqual(
            _lint(
                size,
                migrations.RenameField("owner", "size", "bulk"),
                migrations.RemoveField("owner", "bulk"),
            ),
            [],
        )

    def test_runsql_drop_index(self) -> None:
        """It names no table and does not say whether the index is unique."""
        drop = "DROP INDEX CONCURRENTLY IF EXISTS w_idx"
        self.assertEqual(_sql(drop), [("0", "drop-unique")])
        self.assertEqual(_sql("DROP INDEX public.w_idx CASCADE"), [("0", "drop-unique")])
        self.assertEqual(
            _sql("DROP INDEX w_idx, w_other"),
            [("0", "drop-unique"), ("0", "drop-unique")],
        )
        self.assertEqual(_sql("DROP INDEX (w_idx)"), [("0", "raw-sql")])
        new = _migration("0002_new", [migrations.RunSQL(drop)])
        [finding] = compat.lint([_released(), new], RELEASED)
        self.assertEqual(
            finding.detail,
            f"RunSQL: {drop} (the guard cannot tell whether the index is unique)",
        )
        # The house pattern: clear an interrupted build, then build it again.
        build = "CREATE INDEX CONCURRENTLY IF NOT EXISTS w_idx ON widget (name)"
        self.assertEqual(_lint(migrations.RunSQL([drop, build]), atomic=False), [])
        self.assertEqual(
            _lint(migrations.RunSQL(drop), migrations.RunSQL(build), atomic=False), []
        )
        index = models.Index(fields=["name"], name="w_idx")
        again = migrations.SeparateDatabaseAndState(
            database_operations=[AddIndexConcurrently("widget", index)],
            state_operations=[migrations.AddIndex("widget", index)],
        )
        self.assertEqual(_lint(migrations.RunSQL(drop), again, atomic=False), [])
        self.assertEqual(_sql("CREATE INDEX CONCURRENTLY ON widget (name)"), [])
        # Built under another name: not that pattern.
        other = "CREATE INDEX CONCURRENTLY w_other ON widget (name)"
        self.assertEqual(
            _lint(migrations.RunSQL([other, drop]), atomic=False), [("0", "drop-unique")]
        )
        # An index this release built is the release's own to drop.
        self.assertEqual(_lint(migrations.RunSQL([build, drop]), atomic=False), [])
        self.assertEqual(
            _lint(AddIndexConcurrently("widget", index), migrations.RunSQL(drop)), []
        )
        # A state-only AddIndex builds nothing: the name may be a released unique index.
        adopt = migrations.SeparateDatabaseAndState(
            state_operations=[migrations.AddIndex("widget", index)]
        )
        self.assertEqual(_lint(adopt, migrations.RunSQL(drop)), [("1", "drop-unique")])
        # Meta.indexes of the previous release's models are never unique.
        released = _released(migrations.AddIndex("widget", index))
        self.assertEqual(_lint(migrations.RunSQL(drop), released=released), [])

    def test_alterfield_that_points_a_foreign_key_at_another_column(self) -> None:
        """to_field: Django drops the constraint and adds one on the other column."""
        released = _released(
            migrations.AddField(
                "owner", "alt", models.BigIntegerField(null=True, unique=True)
            )
        )

        def owner(**options):
            key = models.ForeignKey("probe.Owner", models.CASCADE, null=True, **options)
            return migrations.AlterField("widget", "owner", key)

        self.assertEqual(
            _lint(owner(to_field="alt"), released=released), [("0", "add-constraint")]
        )
        # The primary key, named or not, is the column it points at already.
        self.assertEqual(_lint(owner(to_field="id"), released=released), [])
        depot = migrations.CreateModel(
            "Depot", [("code", models.CharField(max_length=8, primary_key=True))]
        )

        def depot_key(**options):
            return models.ForeignKey("probe.Depot", models.CASCADE, null=True, **options)

        with_depot = _released(depot, migrations.AddField("widget", "depot", depot_key()))
        named = migrations.AlterField("widget", "depot", depot_key(to_field="code"))
        self.assertEqual(_lint(named, released=with_depot), [])
        self.assertEqual(_lint(owner(related_name="widgets"), released=released), [])

    def test_runsql_add_column_definition(self) -> None:
        add = "ALTER TABLE widget ADD COLUMN"
        # pgAdmin spelling: the quoted name "default" is not a DEFAULT.
        self.assertEqual(
            _sql(
                f'{add} region character varying(50) COLLATE pg_catalog."default" NOT NULL'
            ),
            [("0", "add-not-null")],
        )
        self.assertEqual(_sql(f'{add} "default" integer'), [])
        self.assertEqual(_sql(f'{add} "not null" integer'), [])
        # A column constraint can name a column the previous release writes.
        self.assertEqual(
            _sql(f"{add} discount integer CHECK (weight > 0)"), [("0", "add-constraint")]
        )
        self.assertEqual(
            _sql(f"{add} size integer NOT NULL DEFAULT 0 CHECK (size >= 0)"),
            [("0", "add-constraint")],
        )
        self.assertEqual(_sql(f"{add} kind text DEFAULT 'CHECK (x)'"), [])
        # Every INSERT of the previous release gets the same default.
        for unique in ("UNIQUE", "PRIMARY KEY"):
            with self.subTest(unique):
                self.assertEqual(
                    _sql(f"{add} serial integer NOT NULL DEFAULT 0 {unique}"),
                    [("0", "add-unique")],
                )
        self.assertEqual(_sql(f"{add} token text UNIQUE"), [])
        # A table of this release is exempt.
        on_new = "ALTER TABLE probe_gadget ADD COLUMN size integer NOT NULL UNIQUE CHECK (size > 0)"
        self.assertEqual(_lint(GADGET, migrations.RunSQL(on_new)), [])

    def test_an_apostrophe_in_a_quoted_name_does_not_start_a_string(self) -> None:
        statement = """ALTER TABLE widget ADD COLUMN "it's" integer, DROP COLUMN note, ADD COLUMN "x'y" integer"""
        self.assertEqual(_sql(statement), [("0", "drop-column")])
        # A quote inside a string is still part of the string.
        self.assertEqual(
            _sql(
                """ALTER TABLE widget ALTER COLUMN code SET DEFAULT 'a "b', ALTER COLUMN name SET DEFAULT 'c" d'"""
            ),
            [],
        )

    def test_a_do_block_that_writes_without_a_statement_keyword(self) -> None:
        for body in (
            "v := setval(pg_get_serial_sequence('widget', 'id'), 1, false)",
            "SELECT setval('widget_id_seq', 1) INTO v",
            "SELECT nextval('widget_id_seq') INTO v",
            "v := tidy()",
            "LOCK TABLE widget IN ACCESS EXCLUSIVE MODE",
            "COPY widget FROM '/tmp/rows'",
        ):
            with self.subTest(body):
                self.assertEqual(
                    _sql(f"DO $$ DECLARE v bigint; BEGIN {body}; END $$"),
                    [("0", "raw-sql")],
                )
        # The index check that follows CREATE INDEX CONCURRENTLY (workflow_v2 0029)
        # reads the catalog into variables. That stays read-only.
        house = """
            DO $$
            DECLARE idx_def text; idx_valid boolean;
            BEGIN
                SELECT pg_get_indexdef(i.indexrelid), i.indisvalid INTO idx_def, idx_valid
                FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
                WHERE c.relname = 'w_idx';
                IF idx_def IS NULL THEN RAISE EXCEPTION 'w_idx is missing'; END IF;
                IF NOT idx_valid THEN
                    RAISE EXCEPTION 'w_idx is INVALID: DROP INDEX w_idx; v := 1';
                END IF;
            END $$;
        """
        self.assertEqual(_sql(house), [])

    def test_a_default_that_is_removed_again_is_not_kept(self) -> None:
        def then(*changes: str) -> list:
            statements = [
                migrations.RunSQL(f"ALTER TABLE widget ALTER COLUMN active {change}")
                for change in changes
            ]
            return _lint(ADD_ACTIVE, *statements)

        self.assertEqual(
            then("SET DEFAULT true", "SET DEFAULT NULL"), [("0", "add-not-null")]
        )
        self.assertEqual(
            then("SET DEFAULT true", "DROP DEFAULT"),
            [("0", "add-not-null"), ("2", "raw-sql")],
        )
        self.assertEqual(
            then("SET DEFAULT true", "SET DEFAULT NULL", "SET DEFAULT false"), []
        )
        # A nullable column needs no default.
        self.assertEqual(then("DROP NOT NULL", "SET DEFAULT NULL"), [])
        self.assertEqual(
            then("SET DEFAULT true", "DROP NOT NULL", "SET DEFAULT NULL"), []
        )
        one_statement = migrations.RunSQL(
            "ALTER TABLE widget ALTER COLUMN active SET DEFAULT true, "
            "ALTER COLUMN active SET DEFAULT NULL"
        )
        self.assertEqual(_lint(ADD_ACTIVE, one_statement), [("0", "add-not-null")])

    def test_one_alterfield_gives_one_type_finding(self) -> None:
        """Type and identity both change; one waiver has to be able to clear it."""
        plain_key = migrations.AlterField(
            "tag", "id", models.IntegerField(primary_key=True)
        )
        new = _migration("0002_new", [plain_key])
        [finding] = compat.lint([_released(), new], RELEASED)
        self.assertEqual(
            (finding.rule, finding.detail),
            (
                "alter-column-type",
                "AlterField probe_tag.id: bigint -> integer; "
                "GENERATED BY DEFAULT AS IDENTITY -> no identity",
            ),
        )
        waiver = {"op": "0", "rule": "alter-column-type", "reason": REASON}
        self.assertEqual(_lint(plain_key, backward_compat_waivers=[waiver]), [])

    def test_exemptions_that_keep_safe_changes_quiet(self) -> None:
        unbounded = migrations.AlterField("widget", "name", models.CharField())
        self.assertEqual(_lint(unbounded), [])
        # Still NOT NULL, as it was: Django sets and drops no default here.
        size = migrations.AddField("widget", "size", models.IntegerField(default=1))
        keep = migrations.RunSQL("ALTER TABLE widget ALTER COLUMN size SET DEFAULT 1")
        same = migrations.AlterField("widget", "size", models.IntegerField(default=2))
        self.assertEqual(_lint(size, keep, same), [])
        # A check that goes away constrains nobody.
        positive = _released(
            migrations.AlterField(
                "widget", "weight", models.PositiveIntegerField(default=0)
            )
        )
        relax = migrations.AlterField("widget", "weight", models.IntegerField(default=0))
        self.assertEqual(_lint(relax, released=positive), [])
        # A foreign key without a database constraint adds none.
        loose = migrations.AlterField(
            "widget",
            "weight",
            models.ForeignKey(
                "probe.Owner",
                models.CASCADE,
                db_column="weight",
                db_index=False,
                db_constraint=False,
            ),
        )
        self.assertEqual(_lint(loose), [("0", "alter-column-type")])
        # A primary key that stops being one: the identity is the finding.
        self.assertEqual(
            _lint(migrations.AlterField("widget", "id", models.BigIntegerField())),
            [("0", "alter-column-type")],
        )
        # A unique column has its index already.
        unique = _released(
            migrations.AlterField(
                "widget", "name", models.CharField(max_length=64, unique=True)
            )
        )
        indexed = migrations.AlterField(
            "widget", "name", models.CharField(max_length=64, unique=True, db_index=True)
        )
        self.assertEqual(_lint(indexed, released=unique), [])

    def test_renamemodel_and_the_many_to_many_tables_that_point_at_it(self) -> None:
        """Owner keeps its table (db_table), but tag_owners.owner_id is renamed."""
        pointed_at = _released(
            migrations.AddField("tag", "owners", models.ManyToManyField("probe.Owner"))
        )
        rename = migrations.RenameModel("Owner", "Holder")
        self.assertEqual(_lint(rename, released=pointed_at), [("0", "rename-table")])
        # A through model names its own columns; RenameModel leaves them alone.
        link = migrations.CreateModel(
            "Link",
            [
                ("id", models.BigAutoField(primary_key=True)),
                ("tag", models.ForeignKey("probe.Tag", models.CASCADE)),
                ("owner", models.ForeignKey("probe.Owner", models.CASCADE)),
            ],
        )
        through = migrations.AddField(
            "tag", "owners", models.ManyToManyField("probe.Owner", through="probe.Link")
        )
        explicit = _released(link, through)
        self.assertEqual(_lint(rename, released=explicit), [])
        retarget = migrations.AlterField(
            "tag", "owners", models.ManyToManyField("probe.Widget", through="probe.Link")
        )
        self.assertEqual(_lint(retarget, released=explicit), [])

    def test_altermodeltable_back_to_the_default_name(self) -> None:
        self.assertEqual(
            _lint(migrations.AlterModelTable("owner", None)), [("0", "rename-table")]
        )
        self.assertEqual(_lint(migrations.AlterModelTable("tag", None)), [])

    def test_only_the_listed_settings_may_be_set(self) -> None:
        for statement in (
            "SET search_path TO elsewhere",
            "SET session_replication_role = replica",
            "SET LOCAL row_security = off",
        ):
            with self.subTest(statement):
                self.assertEqual(_sql(statement), [("0", "raw-sql")])

    # -- operations without a rule --
    def test_a_project_subclass_of_an_operation_with_a_rule_is_not_trusted(self) -> None:
        """Its database_forwards can run anything, whatever the base class does."""

        class QuietSQL(migrations.RunSQL):
            def database_forwards(self, app_label, schema_editor, from_state, to_state):
                schema_editor.execute("ALTER TABLE widget DROP COLUMN note")

        class QuietAddField(migrations.AddField):
            pass

        class QuietSplit(migrations.SeparateDatabaseAndState):
            pass

        unclassified = [("0", "unclassified-operation")]
        self.assertEqual(_lint(QuietSQL(migrations.RunSQL.noop)), unclassified)
        nullable = models.IntegerField(null=True)
        self.assertEqual(_lint(QuietAddField("widget", "size", nullable)), unclassified)
        self.assertEqual(_lint(QuietSplit()), unclassified)
        self.assertEqual(
            _lint(
                QuietSplit(database_operations=[migrations.RemoveField("widget", "note")])
            ),
            [("0", "unclassified-operation"), ("0.db.0", "drop-column")],
        )
        self.assertEqual(
            _lint(
                migrations.SeparateDatabaseAndState(database_operations=[QuietSQL("")])
            ),
            [("0.db.0", "unclassified-operation")],
        )
        new = _migration("0002_new", [QuietSQL(migrations.RunSQL.noop)])
        [finding] = compat.lint([_released(), new], RELEASED)
        self.assertIn("QuietSQL is defined outside Django", finding.detail)
        # The subclasses Django ships keep the rule of their base.
        check = models.CheckConstraint(check=models.Q(weight__gte=0), name="w_ck")
        self.assertEqual(
            _lint(AddConstraintNotValid("widget", check)), [("0", "add-constraint")]
        )

    def test_an_unknown_operation_is_not_waved_through(self) -> None:
        class Custom(migrations.operations.base.Operation):
            def state_forwards(self, app_label, state):
                pass

        self.assertEqual(_lint(Custom()), [("0", "unclassified-operation")])
        self.assertEqual(
            _lint(migrations.AlterOrderWithRespectTo("widget", "owner")),
            [("0", "unclassified-operation")],
        )

    def test_a_subclass_of_a_safe_operation_is_not_safe(self) -> None:
        """It can run any SQL from database_forwards."""

        class TidyOptions(migrations.AlterModelOptions):
            def database_forwards(self, app_label, schema_editor, from_state, to_state):
                schema_editor.execute("ALTER TABLE widget DROP COLUMN note")

        class QuietRemoveConstraint(migrations.RemoveConstraint):
            pass

        options = {"ordering": ["id"]}
        self.assertEqual(
            _lint(TidyOptions("widget", options)), [("0", "unclassified-operation")]
        )
        self.assertEqual(_lint(migrations.AlterModelOptions("widget", options)), [])
        released = _released(
            migrations.AddConstraint(
                "widget",
                models.CheckConstraint(check=models.Q(weight__gte=0), name="w_ck"),
            )
        )
        self.assertEqual(
            _lint(QuietRemoveConstraint("widget", "w_ck"), released=released),
            [("0", "unclassified-operation")],
        )

    # -- tables another service shares --
    def test_a_shared_table_is_never_free_to_change(self) -> None:
        """Waiting a release helps the previous release, not a service outside the
        repository. Every break of a shared table carries a second finding for it.
        """
        released = _released(
            migrations.AlterUniqueTogether("widget", {("name", "code")}),
            migrations.AddConstraint(
                "widget", models.UniqueConstraint(fields=["code"], name="w_code_uq")
            ),
            migrations.AlterField(
                "widget", "name", models.CharField(max_length=64, unique=True)
            ),
        )
        operations = {
            "drop-column": [
                migrations.RemoveField("widget", "code"),
                "ALTER TABLE widget DROP COLUMN code",
            ],
            "contract-drop": [
                "ALTER TABLE widget DROP COLUMN gone",
                "DROP TABLE gone",
            ],
            "drop-table": [
                migrations.DeleteModel("Widget"),
                migrations.RemoveField("widget", "tags"),
                "DROP TABLE widget",
            ],
            "rename-column": [
                migrations.RenameField("widget", "code", "sku"),
                migrations.AlterField(
                    "widget", "code", models.CharField(max_length=32, db_column="sku")
                ),
                migrations.AlterField(
                    "widget", "tags", models.ManyToManyField("probe.Owner")
                ),
                "ALTER TABLE widget RENAME code TO sku",
            ],
            "rename-table": [
                migrations.AlterModelTable("widget", "gizmo"),
                migrations.RenameModel("Widget", "Gizmo"),
                migrations.RenameModel("Tag", "Label"),
                migrations.RenameField("widget", "tags", "labels"),
                migrations.AlterField(
                    "widget", "tags", models.ManyToManyField("probe.Tag", db_table="x")
                ),
                "ALTER TABLE widget RENAME TO gizmo",
            ],
            "set-not-null": [
                migrations.AlterField("widget", "note", models.TextField()),
                "ALTER TABLE widget ALTER COLUMN note SET NOT NULL",
            ],
            "alter-column-type": [
                migrations.AlterField("widget", "code", models.CharField(max_length=16)),
                migrations.AlterField(
                    "widget", "id", models.BigIntegerField(primary_key=True)
                ),
                "ALTER TABLE widget ALTER COLUMN code TYPE text",
            ],
            "drop-unique": [
                migrations.AlterUniqueTogether("widget", set()),
                migrations.RemoveConstraint("widget", "w_code_uq"),
                migrations.AlterField("widget", "name", models.CharField(max_length=64)),
                "ALTER TABLE widget DROP CONSTRAINT w_code_uq",
            ],
            "raw-sql": ["ALTER TABLE widget ALTER COLUMN code DROP DEFAULT"],
        }
        everything = dict.fromkeys(
            ("widget", "widget_tags", "probe_tag", "gone"),
            "another service inserts rows",
        )
        with mock.patch.dict(compat.SHARED_TABLES, everything):
            for rule, breaking in operations.items():
                for operation in breaking:
                    if isinstance(operation, str):
                        operation = migrations.RunSQL(operation)
                    with self.subTest(str(operation.deconstruct()[1:])):
                        self.assertEqual(
                            _lint(operation, released=released),
                            [("0", rule), ("0", "shared-table")],
                        )
            # These two pass for the previous release (the second step of the
            # two-release NOT NULL recipe, a default removed with SET DEFAULT NULL).
            # Another writer is still hurt by them.
            for statement in (
                "ALTER TABLE widget ALTER COLUMN code SET NOT NULL",
                "ALTER TABLE widget ALTER COLUMN code SET DEFAULT NULL",
            ):
                self.assertEqual(_sql(statement), [("0", "shared-table")])
            state_only = migrations.SeparateDatabaseAndState(
                state_operations=[migrations.RemoveField("widget", "note")]
            )
            self.assertEqual(
                _lint(state_only, migrations.RemoveField("widget", "note")),
                [("1", "drop-column"), ("1", "shared-table")],
            )
            # What stays free: the house pattern and a nullable column.
            self.assertEqual(_lint(ADD_ACTIVE, migrations.RunSQL(SET_DEFAULT)), [])
            seen_at = migrations.AddField(
                "widget", "seen_at", models.DateTimeField(null=True)
            )
            self.assertEqual(_lint(seen_at), [])
            self.assertEqual(
                _lint(seen_at, migrations.RemoveField("widget", "seen_at")), []
            )

    def test_only_tables_in_shared_tables_are_shared(self) -> None:
        self.assertEqual(
            compat.SHARED_TABLES, {"user": "Unstract ID inserts and reads this table"}
        )
        with mock.patch.dict(compat.SHARED_TABLES, {"widget": "another service"}):
            self.assertEqual(
                _lint(migrations.RemoveField("owner", "label")), [("0", "drop-column")]
            )
            self.assertEqual(
                _sql("ALTER TABLE owner ALTER COLUMN label SET NOT NULL"), []
            )
            finding = compat.lint(
                [_released(), _migration("0002", [migrations.DeleteModel("Widget")])],
                RELEASED,
            )[1]
        self.assertEqual(
            finding.detail, "DeleteModel drops widget [widget: another service]"
        )
        self.assertEqual(
            _lint(migrations.RemoveField("widget", "code")), [("0", "drop-column")]
        )


class LintTests(SimpleTestCase):
    def test_a_skipped_migration_changes_the_state_and_is_not_checked(self) -> None:
        """Third-party migrations cannot carry a waiver; they are listed, not linted."""

        def backfill(apps, schema_editor):  # pragma: no cover - never run
            pass

        vendor = _migration(
            "0001_initial",
            [
                migrations.CreateModel(
                    "Ext", [("id", models.BigAutoField(primary_key=True))]
                ),
                migrations.RunPython(backfill),
                migrations.RunSQL("DROP TABLE widget"),
            ],
            app_label="vendor",
        )
        retarget = migrations.AlterField(
            "widget", "owner", models.ForeignKey("vendor.Ext", models.CASCADE, null=True)
        )
        plan = [_released(), vendor, _migration("0002_new", [retarget])]
        findings = compat.lint(plan, RELEASED, skip={("vendor", "0001_initial")})
        self.assertEqual(
            [(f.app_label, f.migration, f.rule) for f in findings],
            [("probe", "0002_new", "add-constraint")],
        )

    def test_a_released_migration_that_needs_an_unreleased_one_is_an_error(self) -> None:
        middle = _migration("0002_gadget", [GADGET])
        last = _migration(
            "0003_gadget_size",
            [migrations.AddField("gadget", "size", models.IntegerField(default=1))],
        )
        plan = [_released(), middle, last]
        with self.assertRaisesRegex(
            ValueError, "probe.0003_gadget_size is in a baseline but does not apply"
        ):
            compat.lint(plan, RELEASED | {("probe", "0003_gadget_size")})
        self.assertEqual(
            compat.lint(
                plan, RELEASED | {("probe", "0002_gadget"), ("probe", "0003_gadget_size")}
            ),
            [],
        )


class WaiverTests(SimpleTestCase):
    def _problems(self, operations: list, waivers) -> tuple[list[str], list[str]]:
        """(rules still failing, waiver problems) for one new migration."""
        new = _migration("0002_new", operations, backward_compat_waivers=waivers)
        findings = compat.lint([_released(), new], RELEASED)
        remaining, problems = compat.apply_waivers(new, findings)
        return [f.rule for f in remaining], problems

    def test_a_waiver_clears_exactly_its_operation_and_rule(self) -> None:
        operations = [
            migrations.RemoveField("widget", "code"),
            migrations.RemoveField("widget", "weight"),
        ]
        waiver = [{"op": "0", "rule": "drop-column", "reason": REASON}]
        self.assertEqual(
            _lint(*operations, backward_compat_waivers=waiver), [("1", "drop-column")]
        )

    def test_a_waiver_clears_one_rule_of_an_operation_with_two_findings(self) -> None:
        add = migrations.AddField(
            "widget", "serial", models.CharField(default="", max_length=8, unique=True)
        )
        waiver = [{"op": "0", "rule": "add-unique", "reason": REASON}]
        self.assertEqual(
            _lint(add, backward_compat_waivers=waiver), [("0", "add-not-null")]
        )

    def test_a_waiver_names_a_database_operation_by_its_path(self) -> None:
        split = migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL("ALTER TABLE widget DROP COLUMN note")
            ],
            state_operations=[migrations.RemoveField("widget", "note")],
        )
        waiver = [{"op": "0.db.0", "rule": "drop-column", "reason": REASON}]
        self.assertEqual(_lint(split, backward_compat_waivers=waiver), [])

    def test_a_waiver_for_another_rule_does_not_clear_it(self) -> None:
        remaining, problems = self._problems(
            [migrations.RemoveField("widget", "code")],
            [{"op": "0", "rule": "rename-column", "reason": REASON}],
        )
        self.assertEqual(remaining, ["drop-column"])
        self.assertEqual(len(problems), 1)
        self.assertIn("operations[0] rename-column matches no finding", problems[0])

    def test_a_waiver_needs_a_real_reason(self) -> None:
        for reason in ("", "ok", None, "19 characters long!", " " * 30):
            with self.subTest(reason=reason):
                remaining, problems = self._problems(
                    [migrations.RemoveField("widget", "code")],
                    [{"op": "0", "rule": "drop-column", "reason": reason}],
                )
                self.assertEqual(remaining, ["drop-column"])
                self.assertIn("needs a reason of at least 20 characters", problems[0])
        remaining, problems = self._problems(
            [migrations.RemoveField("widget", "code")],
            [{"op": "0", "rule": "drop-column", "reason": "20 characters long!!"}],
        )
        self.assertEqual((remaining, problems), ([], []))

    def test_a_malformed_waiver_is_reported(self) -> None:
        drop = [migrations.RemoveField("widget", "code")]
        for waivers, problem in (
            ([{"op": "0", "rule": "drop-column"}], "exactly the keys op, rule, reason"),
            (
                [{"op": "0", "rule": "drop-column", "reason": REASON, "by": "me"}],
                "exactly the keys op, rule, reason",
            ),
            (["0 drop-column"], "exactly the keys op, rule, reason"),
            ([None], "exactly the keys op, rule, reason"),
            (
                {"op": "0", "rule": "drop-column", "reason": REASON},
                "must be a list of dicts",
            ),
            (
                [{"op": "0", "rule": "drop-colum", "reason": REASON}],
                "unknown rule 'drop-colum'",
            ),
        ):
            with self.subTest(waivers=waivers):
                remaining, problems = self._problems(drop, waivers)
                self.assertEqual(remaining, ["drop-column"])
                self.assertEqual(len(problems), 1)
                self.assertIn(problem, problems[0])

    def test_a_duplicate_waiver_is_reported(self) -> None:
        waiver = {"op": "0", "rule": "drop-column", "reason": REASON}
        remaining, problems = self._problems(
            [migrations.RemoveField("widget", "code")], [waiver, dict(waiver)]
        )
        self.assertEqual(remaining, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("duplicate waiver for operations[0] drop-column", problems[0])

    def test_one_waiver_does_not_clear_two_findings_of_a_rule(self) -> None:
        """Written for `note`; `code` was added to the statement later."""
        remaining, problems = self._problems(
            [migrations.RunSQL("ALTER TABLE widget DROP COLUMN note, DROP COLUMN code")],
            [
                {
                    "op": "0",
                    "rule": "drop-column",
                    "reason": "widget.note has had no reader since 0.150.",
                }
            ],
        )
        self.assertEqual(remaining, ["drop-column", "drop-column"])
        self.assertEqual(len(problems), 1)
        self.assertIn("operations[0] drop-column has 2 findings", problems[0])
        self.assertIn("one operation per statement", problems[0])


def _in_memory_project(
    *plan, released=RELEASED, root: Path = BACKEND_ROOT
) -> compat.Project:
    files = {(m.app_label, m.name): f"{m.app_label}/migrations/{m.name}.py" for m in plan}
    baseline = {files[key]: "0" * 64 for key in released}
    return compat.Project(root, list(plan), files, third_party=set(), baseline=baseline)


class NewMigrationReportTests(SimpleTestCase):
    """What the real-graph test prints, and what it refuses outright."""

    def test_a_finding_is_printed_with_its_file_and_a_waiver_that_clears_it(self) -> None:
        bad = _migration("0002_bad", [migrations.RemoveField("widget", "code")])
        [problem] = compat.new_migration_problems(_in_memory_project(_released(), bad))
        waiver = (
            'backward_compat_waivers = [{"op": "0", "rule": "drop-column", '
            '"reason": "<why the previous release keeps working>"}]'
        )
        self.assertEqual(
            problem.splitlines()[:3],
            [
                "probe/migrations/0002_bad.py",
                "probe.0002_bad operations[0]  [drop-column]",
                "    RemoveField drops widget.code",
            ],
        )
        self.assertIn(
            "    Why: The previous release's model still declares the column.", problem
        )
        self.assertIn(
            "    Do instead: Release 1: remove the field from the model", problem
        )
        self.assertTrue(problem.endswith(waiver), problem)
        # Pasted into the migration with the reason filled in, it clears the finding.
        # Pasted as printed it does not: the placeholder is not a reason.
        namespace: dict = {}
        exec(waiver, namespace)  # noqa: S102 - the literal above
        [pasted] = namespace["backward_compat_waivers"]
        for reason, problems in (
            (REASON, []),
            (
                pasted["reason"],
                [
                    "probe.0002_bad: the waiver for operations[0] drop-column still has "
                    "the placeholder; replace it with the reason",
                    problem,
                ],
            ),
        ):
            waived = _migration(
                "0002_bad",
                [migrations.RemoveField("widget", "code")],
                backward_compat_waivers=[{**pasted, "reason": reason}],
            )
            project = _in_memory_project(_released(), waived)
            self.assertEqual(compat.new_migration_problems(project), problems)

    def test_waiver_problems_and_findings_of_every_new_migration_are_reported(
        self,
    ) -> None:
        stale = [{"op": "3", "rule": "drop-table", "reason": REASON}]
        first = _migration("0002_first", [ADD_ACTIVE], backward_compat_waivers=stale)
        second = _migration("0003_second", [migrations.RemoveField("widget", "code")])
        problems = compat.new_migration_problems(
            _in_memory_project(_released(), first, second)
        )
        self.assertEqual(
            [problem.splitlines()[0] for problem in problems],
            [
                "probe.0002_first: the waiver for operations[3] drop-table matches no finding; remove it",
                "probe/migrations/0002_first.py",
                "probe/migrations/0003_second.py",
            ],
        )

    def _empty(self) -> Path:
        """A root with no migration files, for projects that exist only in memory."""
        return Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_baseline_problems_are_printed_one_per_line(self) -> None:
        project = _in_memory_project(_released(), root=self._empty())
        self.assertEqual(baseline_problems(project), [])
        self.assertIsNone(new_migrations_failure(project))
        project.problems.append("probe/tests/migration_baseline.txt:4: x is listed twice")
        self.assertEqual(baseline_problems(project), project.problems)
        # A wrong line does not stop the new migrations from being checked.
        self.assertIsNone(new_migrations_failure(project))

    def test_released_migrations_that_do_not_apply_are_reported_without_a_traceback(
        self,
    ) -> None:
        """A released migration whose dependency is not released: lint cannot start."""
        orphan = _migration(
            "0001_orphan", [migrations.RemoveField("widget", "code")], app_label="extra"
        )
        project = _in_memory_project(orphan, released={("extra", "0001_orphan")})
        failure = new_migrations_failure(project)
        self.assertIn("The released migrations do not apply on their own", failure)
        self.assertIn("extra.0001_orphan is in a baseline but does not apply", failure)
        dependency = (
            "extra.0001_orphan is in a baseline but its dependency probe.0001_initial "
            "is not. Advance the baseline that should list the dependency first."
        )
        project.problems.append(dependency)
        self.assertEqual(new_migrations_failure(project).splitlines()[-1], dependency)
        self.assertNotIn("KeyError", new_migrations_failure(project))

    def test_a_missing_baseline_names_the_directories_and_the_files_read(self) -> None:
        many = [
            _migration(f"{n:04}_more", [], app_label="extra" if n % 2 else "probe")
            for n in range(2, MAX_NEW_MIGRATIONS + 3)
        ]
        project = _in_memory_project(_released(), *many, root=self._empty())
        project.baseline_files.append("probe/tests/migration_baseline.txt")
        [problem] = baseline_problems(project)
        self.assertEqual(
            problem,
            "41 migrations are not in a baseline: 20 under extra/, 21 under probe/. "
            "Baseline files read: probe/tests/migration_baseline.txt. A baseline is "
            "missing or was never generated. The repository that owns those "
            "directories writes its own: `python backend/backend/tests/"
            "update_migration_baseline.py --ref origin/release/X.Y` here, and with "
            "--repo and --out for a baseline that another repository keeps (see that "
            "script).",
        )
        fewer = _in_memory_project(_released(), *many[:-1], root=self._empty())
        self.assertEqual(baseline_problems(fewer), [])

    def test_the_advance_hint_is_printed_only_when_many_migrations_are_new(self) -> None:
        bad = _migration("0002_bad", [migrations.RemoveField("widget", "code")])
        failure = new_migrations_failure(_in_memory_project(_released(), bad))
        self.assertTrue(
            failure.startswith(
                "\n1 problem(s) in new migrations (new = not listed in a "
                "migration_baseline.txt, so not on the newest release branch).\n\n"
                "probe/migrations/0002_bad.py\n"
            ),
            failure,
        )
        self.assertNotIn("advance", failure)
        more = [_migration(f"{n:04}_more", []) for n in range(3, 21)]
        project = _in_memory_project(_released(), bad, *more[:-1])
        self.assertNotIn("advance", new_migrations_failure(project))
        project = _in_memory_project(_released(), bad, *more)
        project.baseline_files += [
            "a/tests/migration_baseline.txt",
            "b/tests/migration_baseline.txt",
        ]
        self.assertIn(
            "\n19 migrations count as new, more than any release has carried. If a "
            "release branch was cut since the baselines were written, advance them "
            "first; the command is in the header of each "
            "(a/tests/migration_baseline.txt, b/tests/migration_baseline.txt).\n\n",
            new_migrations_failure(project),
        )

    def test_a_migration_that_django_does_not_load_is_reported(self) -> None:
        """An app missing from the test settings, or a file that a squash replaces."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in (
                "probe/migrations/0001_initial.py",
                "probe/migrations/__init__.py",
                "legacy/migrations/0001_initial.py",
                "nested/app/migrations/0002_more.py",
                "nested/app/migrations/_helper.py",
                "nested/app/migrations/data/0001_rows.py",
                "nested/app/models.py",
                "probe/migrations/0002_new.py",
                ".scratch/app/migrations/0001_initial.py",
                ".venv/lib/site-packages/pkg/migrations/0001_initial.py",
                "node_modules/pkg/migrations/0001_initial.py",
            ):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text("")
            new = _migration("0002_new", [])
            project = _in_memory_project(_released(), new, root=root)
            project.baseline["legacy/migrations/0001_initial.py"] = "0" * 64
            self.assertEqual(
                compat.migrations_not_loaded(project),
                ["nested/app/migrations/0002_more.py"],
            )
            [problem] = baseline_problems(project)
            self.assertIn("in neither the migration graph nor a baseline", problem)
            self.assertTrue(problem.endswith("\n    nested/app/migrations/0002_more.py"))

    def test_every_rule_has_a_message(self) -> None:
        self.assertEqual(len(compat.RULES), 18)
        for rule, texts in compat.RULES.items():
            with self.subTest(rule):
                rendered = compat.Finding("app", "0002_x", "0", rule, "detail").render()
                self.assertIn(f"[{rule}]", rendered)
                self.assertTrue(all(len(text) > 20 for text in texts))

    def test_a_squash_of_unreleased_migrations_is_refused(self) -> None:
        """Django runs the squash instead of them, so nothing has checked what it does.
        Listing it in the baseline would exempt it: the message must not offer that.
        """
        squash = _migration(
            "0003_squashed_0002_widget_region",
            [
                migrations.AddField(
                    "widget", "region", models.CharField(max_length=8, default="in")
                )
            ],
            replaces=[("probe", "0002_widget_region")],
        )
        [problem] = compat.new_migration_problems(_in_memory_project(_released(), squash))
        self.assertIn(
            "probe.0003_squashed_0002_widget_region replaces migrations that are not "
            "released: probe.0002_widget_region.",
            problem,
        )
        self.assertIn("Remove `replaces`", problem)
        self.assertNotIn("baseline", problem)
        # Without `replaces` it is an ordinary new migration, and its operation is checked.
        squash.replaces = []
        [problem] = compat.new_migration_problems(_in_memory_project(_released(), squash))
        self.assertIn("[add-not-null]", problem)

    def test_a_squash_that_also_replaces_released_migrations_is_still_refused(
        self,
    ) -> None:
        squash = _migration(
            "0003_squashed",
            [],
            replaces=[("probe", "0001_initial"), ("probe", "0002_wip")],
        )
        [problem] = compat.new_migration_problems(_in_memory_project(_released(), squash))
        self.assertIn("not released: probe.0002_wip.", problem)

    def test_a_squash_of_released_migrations_is_listed_not_checked(self) -> None:
        squash = _migration(
            "0002_squashed_0001_initial",
            list(_released().operations),
            replaces=[("probe", "0001_initial")],
        )
        with tempfile.TemporaryDirectory() as root:
            file = Path(root, "probe/migrations/0002_squashed_0001_initial.py")
            file.parent.mkdir(parents=True)
            file.write_text("# the squash\n")
            project = _in_memory_project(_released(), squash, root=Path(root))
            [problem] = compat.new_migration_problems(project)
            line = (
                f"{compat.sha256(file)}  probe/migrations/0002_squashed_0001_initial.py"
            )
            self.assertIn("is a squash of released migrations", problem)
            self.assertTrue(problem.endswith(f"\n    {line}"), problem)
            # With that line in the baseline the squash is released like any other.
            project.add_baseline("probe/tests/migration_baseline.txt", line)
            self.assertEqual(compat.new_migration_problems(project), [])


BASELINE = """\
# released-through: origin/release/0.187 @ 3a76b8544
{digest}  probe/migrations/0001_initial.py
third-party  auth.0001_initial
"""


class BaselineTests(SimpleTestCase):
    def _read(self, text: str) -> compat.Project:
        project = compat.Project(BACKEND_ROOT, [], {}, set())
        project.add_baseline("probe/tests/migration_baseline.txt", text)
        return project

    def test_a_baseline_lists_hashes_and_reviewed_third_party_migrations(self) -> None:
        text = BASELINE.format(digest="ab" * 32) + "\n  # an indented comment\n"
        project = self._read(text)
        self.assertEqual(project.problems, [])
        self.assertEqual(
            project.baseline, {"probe/migrations/0001_initial.py": "ab" * 32}
        )
        self.assertEqual(
            project.listed_third_party,
            {("auth", "0001_initial"): "probe/tests/migration_baseline.txt"},
        )
        self.assertEqual(project.baseline_files, ["probe/tests/migration_baseline.txt"])

    def test_a_baseline_must_come_from_a_release_branch(self) -> None:
        """`--ref HEAD` would list every migration on main and switch the guard off."""
        body = "ab  probe/migrations/0001_initial.py\n"
        for header in (
            "# released-through: origin/release/0.187 @ 3a76b8544",
            "# released-through: release/0.187 @ 3a76b8544",
        ):
            with self.subTest(header):
                self.assertEqual(
                    self._read(f"# a comment\n{header}\n{body}").problems, []
                )
        for header in (
            "",
            "# released-through: HEAD @ 3a76b8544",
            "# released-through: origin/main @ 3a76b8544",
            "# released-through: origin/release/v0.90 @ 3a76b8544",
            "# released-through: origin/release/0.187",
            "#  released-through: origin/release/0.187 @ 3a76b8544 and more",
            "## released-through: origin/release/0.187 @ 3a76b8544",
        ):
            with self.subTest(header):
                [problem] = self._read(f"{header}\n{body}").problems
                self.assertIn(
                    "probe/tests/migration_baseline.txt: no '# released-through:", problem
                )

    def test_only_a_baseline_one_directory_down_is_read(self) -> None:
        """Deeper files are not baselines: an app's tests directory cannot add one."""
        header = "# released-through: origin/release/0.187 @ 3a76b8544\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for path in (
                "probe/tests/migration_baseline.txt",
                "other/tests/migration_baseline.txt",
                "probe/app/tests/migration_baseline.txt",
                "tests/migration_baseline.txt",
            ):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(header)
            project = compat.load_project(root)
        self.assertEqual(
            project.baseline_files,
            ["other/tests/migration_baseline.txt", "probe/tests/migration_baseline.txt"],
        )
        self.assertEqual(project.files, {})  # nothing of the real tree is under tmp

    def test_malformed_and_duplicate_lines_are_reported(self) -> None:
        text = BASELINE.format(digest="ab" * 32) + (
            "cd  probe/migrations/0001_initial.py\n"
            "just-one-field\n"
            "three fields here\n"
        )
        self.assertEqual(
            self._read(text).problems,
            [
                "probe/tests/migration_baseline.txt:4: probe/migrations/0001_initial.py is listed twice",
                "probe/tests/migration_baseline.txt:5: expected '<sha256>  <path>'",
                "probe/tests/migration_baseline.txt:6: expected '<sha256>  <path>'",
            ],
        )

    def test_baselines_of_two_repositories_are_merged(self) -> None:
        project = self._read(BASELINE.format(digest="ab" * 32))
        project.add_baseline(
            "other/tests/migration_baseline.txt",
            "# released-through: origin/release/0.187 @ 1476784f8\n"
            "cd  other/migrations/0001_initial.py\n"
            "ef  probe/migrations/0001_initial.py\n",
        )
        self.assertEqual(
            sorted(project.baseline),
            [
                "other/migrations/0001_initial.py",
                "probe/migrations/0001_initial.py",
            ],
        )
        self.assertEqual(
            project.problems,
            [
                "other/tests/migration_baseline.txt:3: probe/migrations/0001_initial.py is listed twice"
            ],
        )

    def test_a_released_migration_cannot_depend_on_an_unreleased_one(self) -> None:
        """The previous release's state is built from the released migrations alone."""
        first = _released()
        second = _migration("0002_second", [], dependencies=[("probe", "0001_initial")])
        third = _migration("0003_third", [], dependencies=[("probe", "0002_second")])
        graph = MigrationGraph()
        for migration in (first, second, third):
            key = (migration.app_label, migration.name)
            graph.add_node(key, migration)
            for parent in migration.dependencies:
                graph.add_dependency(migration, key, parent)
        skipped = {("probe", "0001_initial"), ("probe", "0003_third")}
        self.assertEqual(
            compat.unreleased_dependencies(graph, skipped),
            [
                "probe.0003_third is in a baseline but its dependency probe.0002_second "
                "is not. Advance the baseline that should list the dependency first."
            ],
        )
        self.assertEqual(
            compat.unreleased_dependencies(graph, skipped | {("probe", "0002_second")}),
            [],
        )

    def test_released_and_new_are_split_by_the_baseline(self) -> None:
        first, second = _released(), _migration("0002_second", [])
        listed = _migration("0001_initial", [], app_label="auth")
        unlisted = _migration("0002_more", [], app_label="auth")
        project = compat.Project(
            BACKEND_ROOT,
            plan=[listed, unlisted, first, second],
            files={
                ("probe", "0001_initial"): "probe/migrations/0001_initial.py",
                ("probe", "0002_second"): "probe/migrations/0002_second.py",
            },
            third_party={("auth", "0001_initial"), ("auth", "0002_more")},
        )
        # A third-party line for a migration that is not installed releases nothing.
        project.add_baseline(
            "probe/tests/migration_baseline.txt",
            BASELINE.format(digest="ab" * 32) + "third-party  gone.0001_initial\n",
        )
        self.assertEqual(
            project.released, {("probe", "0001_initial"), ("auth", "0001_initial")}
        )
        self.assertEqual(project.new, [second])


class BaselineScriptTests(SimpleTestCase):
    """update_migration_baseline.py, on a throwaway repository."""

    def _run(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                code = baseline_script.main(list(argv))
            except SystemExit as stopped:
                code = stopped.code
        return code, output.getvalue()

    def test_only_a_release_branch_is_accepted(self) -> None:
        """Any other ref lists migrations no release has, and the guard stops checking them."""
        with tempfile.TemporaryDirectory() as repo:
            for ref in (
                "HEAD",
                "main",
                "origin/main",
                "origin/release/v0.90",
                "origin/release/0.187-rc.1",
                "origin/release/0.187/x",
                "v0.187.0",
                # A local branch can be behind the one on the remote.
                "release/0.187",
                "upstream/release/0.187",
            ):
                with self.subTest(ref):
                    code, output = self._run("--ref", ref, "--repo", repo)
                    self.assertEqual(code, 2)
                    self.assertIn(
                        "--ref must be a release branch on the remote "
                        "(origin/release/X.Y)",
                        output,
                    )
            self.assertEqual(os.listdir(repo), [])

    @skipUnless(shutil.which("git"), "needs git")
    def test_it_lists_the_migration_files_of_the_release_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            quiet = {
                **os.environ,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            }

            def git(*args: str) -> str:
                identity = ["-c", "user.name=Dev", "-c", "user.email=dev@example.com"]
                command = ["git", "-C", tmp, *identity, *args]
                return subprocess.run(
                    command, check=True, capture_output=True, text=True, env=quiet
                ).stdout.strip()

            def commit(files: dict[str, str]) -> None:
                for path, text in files.items():
                    (repo / path).parent.mkdir(parents=True, exist_ok=True)
                    (repo / path).write_text(text)
                git("add", "--", *files)
                git("commit", "-q", "-m", "change")

            git("init", "-q", "-b", "main")
            commit(
                {
                    "backend/app/migrations/__init__.py": "",
                    "backend/app/migrations/0001_initial.py": "one\n",
                    "backend/app/migrations/_helper.py": "helper\n",
                    "backend/app/migrations/data/rows.py": "not a migration module\n",
                    "backend/app/models.py": "models\n",
                    "docs/migrations/0001_initial.py": "outside backend\n",
                }
            )
            code, output = self._run("--ref", "origin/release/0.1", "--repo", tmp)
            self.assertEqual(
                code, "no origin/release/X.Y branch in this clone; run git fetch origin"
            )
            git("update-ref", "refs/remotes/origin/release/0.1", "HEAD")
            git("update-ref", "refs/remotes/origin/release/v0.90", "HEAD")
            commit({"backend/app/migrations/0002_unreleased.py": "two\n"})
            out = repo / baseline_script.DEFAULT_OUT
            out.parent.mkdir(parents=True)
            out.write_text(
                "third-party  auth.0001_initial\nab  gone/migrations/0001_initial.py\n"
            )

            code, output = self._run("--ref", "origin/release/0.1", "--repo", tmp)
            self.assertEqual((code, output.count("\n")), (0, 1), output)
            self.assertIn("2 migrations at origin/release/0.1", output)
            one, helper, edited = (
                hashlib.sha256(text.encode()).hexdigest()
                for text in ("one\n", "helper\n", "one, edited\n")
            )
            header, _, body = out.read_text().partition("# released-through: ")
            self.assertIn(
                "#   python backend/backend/tests/update_migration_baseline.py "
                "--ref origin/release/X.Y\n",
                header,
            )
            self.assertEqual(
                body.splitlines(),
                [
                    f"origin/release/0.1 @ {git('rev-parse', '--short', 'HEAD~1')}",
                    f"{one}  app/migrations/0001_initial.py",
                    f"{helper}  app/migrations/_helper.py",
                    "third-party  auth.0001_initial",
                ],
            )
            # The guard accepts what the script writes.
            project = compat.Project(repo / "backend", [], {}, set())
            project.add_baseline("backend/tests/migration_baseline.txt", out.read_text())
            self.assertEqual(project.problems, [])
            self.assertEqual(
                sorted(project.baseline),
                sorted(line.split()[1] for line in body.splitlines()[1:3]),
            )

            # Hashes follow the working tree, which is what the guard reads.
            (repo / "backend/app/migrations/0001_initial.py").write_text("one, edited\n")
            code, output = self._run("--ref", "origin/release/0.1", "--repo", tmp)
            self.assertEqual(code, 0)
            self.assertIn(
                "note: differs from origin/release/0.1, pinned as it is in the working "
                "tree",
                output,
            )
            self.assertIn(
                f"{edited}  app/migrations/0001_initial.py",
                out.read_text(),
            )
            (repo / "backend/app/migrations/_helper.py").unlink()
            code, output = self._run(
                "--ref",
                "origin/release/0.1",
                "--repo",
                tmp,
                "--out",
                "other/baseline.txt",
            )
            self.assertIn(
                "note: on origin/release/0.1 but not in the working tree, left out",
                output,
            )
            other = (repo / "other/baseline.txt").read_text()
            self.assertNotIn("_helper.py", other)
            self.assertIn(
                "--repo . --ref origin/release/X.Y --out other/baseline.txt\n", other
            )

            # A branch the clone does not have is not the newest one it knows.
            code, output = self._run("--ref", "origin/release/9.9", "--repo", tmp)
            self.assertEqual(code, 2)
            self.assertIn("origin/release/0.1 is", output)
            with tempfile.TemporaryDirectory() as not_a_repository:
                code, output = self._run(
                    "--ref", "origin/release/0.1", "--repo", not_a_repository
                )
            self.assertIn("git for-each-ref", str(code))
            self.assertIn("failed: ", str(code))

            # Only the newest release line says what is released.
            git("update-ref", "refs/remotes/origin/release/0.9", "HEAD")
            git("update-ref", "refs/remotes/origin/release/0.10", "HEAD")
            written = out.read_text()
            for older in ("origin/release/0.1", "origin/release/0.9"):
                with self.subTest(older):
                    code, output = self._run("--ref", older, "--repo", tmp)
                    self.assertEqual(code, 2)
                    self.assertIn(
                        f"--ref {older} is not the newest release branch: "
                        "origin/release/0.10 is",
                        output,
                    )
            self.assertEqual(out.read_text(), written)
            code, output = self._run("--ref", "origin/release/0.10", "--repo", tmp)
            self.assertEqual(code, 0, output)
            self.assertIn("\n# released-through: origin/release/0.10 @ ", out.read_text())
