from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
import uuid

from sqlalchemy import inspect, text


MIGRATIONS = (
    (
        "20261020_01_fair_metadata_and_system_settings",
        "_add_fair_metadata_and_system_settings",
    ),
    (
        "20261020_02_fair_assignments",
        "_add_fair_assignments",
    ),
    (
        "20261020_03_fair_inventory",
        "_add_fair_inventory",
    ),
    (
        "20261020_04_pos_fair_context",
        "_add_pos_fair_context",
    ),
    (
        "20261020_05_pos_product_pricing_setup",
        "_add_pos_product_pricing_setup",
    ),
    (
        "20261020_06_fair_vehicle_assignment",
        "_add_fair_vehicle_assignment",
    ),
)


def _sqlite_database_path(engine):
    if engine.dialect.name != "sqlite":
        raise RuntimeError(
            "Schema upgrades currently require SQLite so a verified backup can be created."
        )

    database = engine.url.database
    if not database or database == ":memory:":
        return None
    return Path(database).expanduser().resolve()


def _has_pending_migrations(engine):
    inspector = inspect(engine)
    if not inspector.has_table("schema_migrations"):
        return bool(MIGRATIONS)

    with engine.connect() as connection:
        applied = set(
            connection.execute(
                text("SELECT version FROM schema_migrations")
            ).scalars()
        )
    return any(version not in applied for version, _ in MIGRATIONS)


def _create_verified_backup(database_path):
    if not database_path.exists():
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = database_path.with_name(
        f"{database_path.stem}.before-schema-{timestamp}-{uuid.uuid4().hex[:8]}.bak"
    )
    temporary_path = Path(f"{backup_path}.tmp")

    source = sqlite3.connect(str(database_path))
    target = sqlite3.connect(str(temporary_path))
    try:
        source.backup(target)
        target.close()
        target = None

        verification = sqlite3.connect(str(temporary_path))
        try:
            if verification.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("The pre-migration backup failed SQLite integrity_check.")
            if verification.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("The pre-migration backup contains foreign-key violations.")
        finally:
            verification.close()
    except Exception:
        if target is not None:
            target.close()
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    finally:
        source.close()

    os.rename(temporary_path, backup_path)
    return backup_path


def backup_before_pending_migrations(engine):
    if not _has_pending_migrations(engine):
        return None

    database_path = _sqlite_database_path(engine)
    if database_path is None:
        return None
    return _create_verified_backup(database_path)


def _add_fair_metadata_and_system_settings(connection):
    fair_columns = {
        column["name"]
        for column in inspect(connection).get_columns("foires")
    }
    column_definitions = {
        "organizer": "VARCHAR(160)",
        "start_date": "DATE",
        "end_date": "DATE",
        "product_send_deadline": "DATE",
        "status": "VARCHAR(24)",
        "allow_late_send": "BOOLEAN NOT NULL DEFAULT 0",
        "late_send_reason": "VARCHAR(500)",
        "manager_notes": "TEXT",
    }
    for column, definition in column_definitions.items():
        if column not in fair_columns:
            connection.execute(
                text(f'ALTER TABLE "foires" ADD COLUMN "{column}" {definition}')
            )

    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS system_settings ("
            "key VARCHAR(100) PRIMARY KEY, "
            "value TEXT NOT NULL, "
            "updated_at DATETIME NOT NULL)"
        )
    )


def _add_fair_assignments(connection):
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS fair_assignments ("
            "id INTEGER PRIMARY KEY, "
            "fair_id INTEGER NOT NULL REFERENCES foires(id) ON DELETE CASCADE, "
            "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
            "role VARCHAR(24) NOT NULL, "
            "start_date DATE NOT NULL, "
            "end_date DATE NOT NULL, "
            "status VARCHAR(20) NOT NULL DEFAULT 'confirmed', "
            "source VARCHAR(20) NOT NULL DEFAULT 'manual', "
            "created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, "
            "notes VARCHAR(500))"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_fair_assignments_user_dates "
            "ON fair_assignments (user_id, start_date, end_date)"
        )
    )


def _add_fair_inventory(connection):
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS fair_inventory ("
            "fair_id INTEGER NOT NULL REFERENCES foires(id) ON DELETE RESTRICT, "
            "article_ref VARCHAR(50) NOT NULL REFERENCES articles(ref) ON DELETE RESTRICT, "
            "quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0), "
            "PRIMARY KEY (fair_id, article_ref))"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS fair_inventory_movements ("
            "id INTEGER PRIMARY KEY, "
            "fair_id INTEGER NOT NULL REFERENCES foires(id) ON DELETE RESTRICT, "
            "article_ref VARCHAR(50) NOT NULL REFERENCES articles(ref) ON DELETE RESTRICT, "
            "movement_type VARCHAR(20) NOT NULL, "
            "quantity_delta INTEGER NOT NULL CHECK (quantity_delta != 0), "
            "movement_date DATE NOT NULL, "
            "reference VARCHAR(120), "
            "notes VARCHAR(500), "
            "created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, "
            "created_at DATETIME NOT NULL, "
            "CHECK ("
            "(movement_type IN ('transfer_in', 'receipt', 'return') AND quantity_delta > 0) "
            "OR (movement_type IN ('transfer_out', 'sale', 'damage') AND quantity_delta < 0)"
            "))"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_fair_inventory_movements_fair_date "
            "ON fair_inventory_movements (fair_id, movement_date, id)"
        )
    )
    connection.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS trg_fair_inventory_movements_no_update "
            "BEFORE UPDATE ON fair_inventory_movements "
            "BEGIN SELECT RAISE(ABORT, 'fair inventory movements are append-only'); END"
        )
    )
    connection.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS trg_fair_inventory_movements_no_delete "
            "BEFORE DELETE ON fair_inventory_movements "
            "BEGIN SELECT RAISE(ABORT, 'fair inventory movements are append-only'); END"
        )
    )


def _add_pos_fair_context(connection):
    sale_columns = {
        column["name"]
        for column in inspect(connection).get_columns("pos_sales")
    }
    column_definitions = {
        "fair_id": "INTEGER REFERENCES foires(id) ON DELETE RESTRICT",
        "seller_id": "INTEGER REFERENCES users(id) ON DELETE RESTRICT",
        "cashier_user_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
    }
    for column, definition in column_definitions.items():
        if column not in sale_columns:
            connection.execute(
                text(f'ALTER TABLE "pos_sales" ADD COLUMN "{column}" {definition}')
            )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sales_fair_seller_date "
            "ON pos_sales (fair_id, seller_id, date)"
        )
    )

def _add_pos_product_pricing_setup(connection):
    product_columns = {
        column["name"]
        for column in inspect(connection).get_columns("pos_products")
    }
    if "pricing_configured" not in product_columns:
        connection.execute(
            text(
                'ALTER TABLE "pos_products" ADD COLUMN '
                '"pricing_configured" BOOLEAN NOT NULL DEFAULT 1'
            )
        )


def _add_fair_vehicle_assignment(connection):
    fair_columns = {
        column["name"]
        for column in inspect(connection).get_columns("foires")
    }
    if "assigned_vehicle_id" not in fair_columns:
        connection.execute(
            text(
                'ALTER TABLE "foires" ADD COLUMN "assigned_vehicle_id" '
                'INTEGER REFERENCES "voitures" ("id") ON DELETE SET NULL'
            )
        )


_MIGRATION_FUNCTIONS = {
    "_add_fair_metadata_and_system_settings": _add_fair_metadata_and_system_settings,
    "_add_fair_assignments": _add_fair_assignments,
    "_add_fair_inventory": _add_fair_inventory,
    "_add_pos_fair_context": _add_pos_fair_context,
    "_add_pos_product_pricing_setup": _add_pos_product_pricing_setup,
    "_add_fair_vehicle_assignment": _add_fair_vehicle_assignment,
}


def apply_schema_migrations(engine):
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "version VARCHAR(100) PRIMARY KEY, "
                    "applied_at VARCHAR(40) NOT NULL)"
                )
            )
            applied = set(
                connection.execute(
                    text("SELECT version FROM schema_migrations")
                ).scalars()
            )
            for version, migration_name in MIGRATIONS:
                if version in applied:
                    continue
                _MIGRATION_FUNCTIONS[migration_name](connection)
                connection.execute(
                    text(
                        "INSERT INTO schema_migrations (version, applied_at) "
                        "VALUES (:version, :applied_at)"
                    ),
                    {
                        "version": version,
                        "applied_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
