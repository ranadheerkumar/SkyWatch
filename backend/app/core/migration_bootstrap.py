from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.database import Base, engine
import app.models


def _alembic_config() -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
    return config


def _legacy_schema_is_compatible() -> None:
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
    expected_tables = set(Base.metadata.tables)
    missing_tables = expected_tables - actual_tables
    if missing_tables:
        raise RuntimeError(
            "Legacy database is missing required tables: "
            + ", ".join(sorted(missing_tables))
            + ". Back up the database and run a reviewed migration plan."
        )

    missing_columns: dict[str, list[str]] = {}
    nullable_columns: dict[str, list[str]] = {}
    for table_name in sorted(expected_tables):
        actual_column_info = {column["name"]: column for column in inspector.get_columns(table_name)}
        actual_columns = set(actual_column_info)
        expected_columns = set(Base.metadata.tables[table_name].columns.keys())
        if expected_columns - actual_columns:
            missing_columns[table_name] = sorted(expected_columns - actual_columns)
        expected_non_nullable = {
            column.name
            for column in Base.metadata.tables[table_name].columns
            if not column.nullable
        }
        incompatible_nullable = {
            column_name
            for column_name in expected_non_nullable
            if column_name in actual_column_info and actual_column_info[column_name]["nullable"]
        }
        if incompatible_nullable:
            nullable_columns[table_name] = sorted(incompatible_nullable)
    if missing_columns:
        details = "; ".join(f"{table}: {', '.join(columns)}" for table, columns in missing_columns.items())
        raise RuntimeError(
            f"Legacy database is missing required columns ({details}). "
            "Back up the database and run a reviewed migration plan."
        )
    if nullable_columns:
        details = "; ".join(f"{table}: {', '.join(columns)}" for table, columns in nullable_columns.items())
        raise RuntimeError(
            f"Legacy database has nullable required columns ({details}). "
            "Back up the database and run the required-column migration before stamping."
        )


def _create_missing_indexes() -> None:
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)


def migrate_database() -> str:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    config = _alembic_config()
    has_migration_version = False
    if "alembic_version" in tables:
        with engine.connect() as connection:
            has_migration_version = connection.execute(text("SELECT 1 FROM alembic_version LIMIT 1")).first() is not None

    if not has_migration_version:
        application_tables = tables - {"alembic_version"}
        if not application_tables:
            command.upgrade(config, "head")
            return "created"
        _legacy_schema_is_compatible()
        _create_missing_indexes()
        command.stamp(config, "head")
        return "adopted"

    command.upgrade(config, "head")
    return "upgraded"


if __name__ == "__main__":
    print(f"Database migration mode: {migrate_database()}")
