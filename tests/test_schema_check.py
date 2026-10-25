"""The shared schema check (testing/schema_check.py, FL-088): what it passes
and what it refuses, on small made-up repositories."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.testing import schema_check as sc  # noqa: E402

SCHEMA = """CREATE TABLE `admins` (
  `id` int NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `nickname` varchar(80) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_admins_email` (`email`)
) ENGINE=InnoDB;

CREATE TABLE `notes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `admin_id` int NOT NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `notes_ibfk_1` FOREIGN KEY (`admin_id`) REFERENCES `admins` (`id`)
) ENGINE=InnoDB;

CREATE TABLE `schema_migrations` (
  `filename` varchar(255) NOT NULL
) ENGINE=InnoDB;
"""
MIGRATIONS = {
    "001_admins.sql": "CREATE TABLE admins (id INT, email VARCHAR(255));\n"
                      "ALTER TABLE admins ADD UNIQUE KEY uq_admins_email (email);",
    "002_notes.sql": "CREATE TABLE notes (id INT, admin_id INT);",
}


def _repo(tmp_path, schema=SCHEMA, migrations=MIGRATIONS) -> Path:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "schema.sql").write_text(schema, encoding="utf-8")
    for name, sql in migrations.items():
        (tmp_path / "migrations" / name).write_text(sql, encoding="utf-8")
    return tmp_path


def _check(root, exceptions=frozenset()):
    class Check(sc.SchemaSqlMatchesTheMigrations):
        ROOT = root
        NOT_FROM_A_MIGRATION = exceptions
    return Check()


def test_the_reader_finds_every_name_and_table(tmp_path):
    names = sc.schema_names(_repo(tmp_path))
    assert names["admins"] == {"id", "email", "nickname", "uq_admins_email"}
    assert names["notes"] == {"id", "admin_id", "notes_ibfk_1"}
    assert set(names) == {"admins", "notes", "schema_migrations"}


def test_an_invented_name_is_refused_and_an_exception_lets_it_pass(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(AssertionError, match="admins.nickname"):
        _check(root).test_every_name_in_schema_sql_comes_from_a_migration()
    ok = _check(root, frozenset({"admins.nickname"}))
    ok.test_every_name_in_schema_sql_comes_from_a_migration()
    ok.test_the_exceptions_are_still_exceptions()
    ok.test_every_table_in_schema_sql_was_read()


def test_an_exception_a_migration_now_names_must_come_off_the_list(tmp_path):
    root = _repo(tmp_path, migrations={**MIGRATIONS,
                                       "003_nick.sql": "ALTER TABLE admins ADD COLUMN nickname VARCHAR(80);"})
    with pytest.raises(AssertionError, match="remove from NOT_FROM_A_MIGRATION: admins.nickname"):
        _check(root, frozenset({"admins.nickname"})).test_the_exceptions_are_still_exceptions()
    with pytest.raises(AssertionError, match="admins.gone"):
        _check(root, frozenset({"admins.gone"})).test_the_exceptions_are_still_exceptions()


def test_a_table_the_pattern_cannot_read_is_reported(tmp_path):
    root = _repo(tmp_path, schema=SCHEMA + "CREATE TABLE odd (\n  id int\n);\n")
    with pytest.raises(AssertionError):
        _check(root, frozenset({"admins.nickname"})).test_every_table_in_schema_sql_was_read()


def test_a_wrapper_without_its_root_says_so():
    with pytest.raises(AssertionError, match="set ROOT"):
        sc.SchemaSqlMatchesTheMigrations().test_every_table_in_schema_sql_was_read()
