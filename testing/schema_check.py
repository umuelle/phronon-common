"""schema.sql must describe the database the migrations build.

Every tool runs this against its own schema.sql and migrations/. Until
25 October 2026 it was a copy in each of the nine tools
(`tests/test_schema_sql_matches_the_migrations.py`, identical outside one
PER TOOL block, which server-ops/fleet_testkit_check.py rule 5 enforced),
because the FL-076 freeze kept it out of this package (TO DO FL-088). A
tool's file is now a wrapper:

    from phronon_common.testing.schema_check import SchemaSqlMatchesTheMigrations

    class TestSchemaSqlMatchesTheMigrations(SchemaSqlMatchesTheMigrations):
        ROOT = Path(__file__).resolve().parents[1]
        # Names production has that no migration creates, each checked
        # against production; the list only shrinks.
        NOT_FROM_A_MIGRATION = frozenset()

A tool's own extra checks may call `schema_names(ROOT)`, `migrations_text(ROOT)`
and `named_in(name, text)`.

WHY. Production is built by applying migrations/ in order. schema.sql builds
the rest: the preview database, a rebuild from nothing, and in four tools CI
and the test schema. When the two files disagree, whatever is built from one
breaks while everything built from the other stays green. Before this check
it happened three times: Layoff's schema.sql lacked classes.is_sample and
OrgDesignSim's carried an over-applied rename (both August 2026), then
OrgDesignSim's passkeys table said educator_id where migration 016 and the
code say admin_id, and its preview answered 500 (4 October). The first run
found two more: Layoff's admins.display_name in no migration (now migration
017) and a Whiteout index name that production never had.

WHAT IT CHECKS, from source, so it runs everywhere: every column, key and
constraint name in schema.sql appears somewhere in migrations/, unless the
tool lists it as checked against production. A name passes if it appears
anywhere, so this cannot prove the files agree; it catches a name schema.sql
invented, which is how each break began. Not counted: the runner's own
schema_migrations table, and MySQL's automatic foreign-key names
(`<table>_ibfk_<n>`), which an unnamed FOREIGN KEY clause receives and no
migration spells.

Not chosen (5 October 2026): building each tool twice in scratch databases
and diffing information_schema. Done by hand that day it found nothing this
misses apart from column order; take it up if a drift this cannot see (a
type, a default, nullability) ever reaches a database.

NOTHING HERE SKIPS: it reads two things in the tool's repository.
"""
from __future__ import annotations

import re
from pathlib import Path

# Created by the deploy runner itself, never by a migration file.
RUNNER_TABLES = {"schema_migrations"}

_CREATE = re.compile(
    r"CREATE TABLE (?:IF NOT EXISTS )?`(\w+)` \((.*?)\n\) ENGINE", re.S)


def schema_sql(root: Path) -> str:
    return (Path(root) / "schema.sql").read_text(encoding="utf-8")


def schema_names(root: Path) -> dict[str, set[str]]:
    """{table: every column, key and constraint name schema.sql declares}."""
    tables: dict[str, set[str]] = {}
    for block in _CREATE.finditer(schema_sql(root)):
        name, body = block.group(1), block.group(2)
        tables[name] = (
            set(re.findall(r"^\s*`(\w+)`\s+\w", body, re.M))
            | set(re.findall(r"^\s*(?:UNIQUE |FULLTEXT )?KEY `(\w+)`", body, re.M))
            | set(re.findall(r"^\s*CONSTRAINT `(\w+)`", body, re.M)))
    return tables


def migrations_text(root: Path) -> str:
    """Every migration file, in order, as one text."""
    return "\n".join(p.read_text(encoding="utf-8")
                     for p in sorted((Path(root) / "migrations").glob("*.sql")))


def named_in(name: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\b", text) is not None


class SchemaSqlMatchesTheMigrations:
    """Subclass as `Test…`, set ROOT and NOT_FROM_A_MIGRATION."""

    #: The tool's repository root (the folder holding schema.sql and migrations/).
    ROOT: Path = Path()
    #: "table.name" entries production has that no migration creates.
    NOT_FROM_A_MIGRATION: frozenset = frozenset()

    def test_every_table_in_schema_sql_was_read(self):
        """A CREATE TABLE the pattern misses is a table nothing below checks.
        Layoff's resume-token table, pasted from its migration as CREATE TABLE IF
        NOT EXISTS with comments, was the first one the pattern missed."""
        assert self.ROOT != Path(), "set ROOT to the tool's repository root"
        created = re.findall(r"^\s*CREATE TABLE", schema_sql(self.ROOT), re.M | re.I)
        assert len(schema_names(self.ROOT)) == len(created) > 0

    def test_every_name_in_schema_sql_comes_from_a_migration(self):
        migrations = migrations_text(self.ROOT)
        invented = sorted(
            f"{table}.{name}"
            for table, names in schema_names(self.ROOT).items() if table not in RUNNER_TABLES
            for name in names
            if not re.fullmatch(rf"{table}_ibfk_\d+", name)
            and f"{table}.{name}" not in self.NOT_FROM_A_MIGRATION
            and not named_in(name, migrations))
        assert not invented, (
            "schema.sql names these and no migration does, so a database built from "
            "one file differs from a database built from the other: "
            + ", ".join(invented) + ". If production has the name (added by hand), "
            "write an idempotent migration for it (Layoff 017, Whiteout 032). If "
            "production does not, schema.sql is wrong: regenerate it with mysqldump "
            '(README "Database bootstrap").')

    def test_the_exceptions_are_still_exceptions(self):
        """NOT_FROM_A_MIGRATION only shrinks. An entry that schema.sql no longer
        names, or that a migration now names, comes off the list."""
        names, migrations = schema_names(self.ROOT), migrations_text(self.ROOT)
        stale = sorted(e for e in self.NOT_FROM_A_MIGRATION
                       if e.split(".", 1)[1] not in names.get(e.split(".", 1)[0], set())
                       or named_in(e.split(".", 1)[1], migrations))
        assert not stale, f"remove from NOT_FROM_A_MIGRATION: {', '.join(stale)}"
