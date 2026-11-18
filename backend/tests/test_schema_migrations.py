import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text

from app import schema_migrations
from app.schema_migrations import (
    apply_schema_migrations,
    backup_before_pending_migrations,
)


class SchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "legacy.sqlite"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        with self.engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            )
            connection.execute(
                text("CREATE TABLE articles (ref VARCHAR(50) PRIMARY KEY)")
            )
            connection.execute(
                text("CREATE TABLE voitures (id INTEGER PRIMARY KEY)")
            )
            connection.execute(
                text(
                    "CREATE TABLE foires ("
                    "id INTEGER PRIMARY KEY, "
                    "nom VARCHAR(160) NOT NULL, "
                    "ville VARCHAR(120) NOT NULL, "
                    "adresse VARCHAR(255) NOT NULL, "
                    "contact VARCHAR(120) NOT NULL, "
                    "d_limite VARCHAR(10) NOT NULL, "
                    "type VARCHAR(30))"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE pos_sales ("
                    "transaction_id INTEGER PRIMARY KEY, "
                    "invoice_number VARCHAR(32) NOT NULL, "
                    "date DATE NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE pos_products ("
                    "product_id INTEGER PRIMARY KEY, "
                    "product_code VARCHAR(120) NOT NULL, "
                    "price NUMERIC(12, 2) NOT NULL, "
                    "o_price NUMERIC(12, 2) NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO foires "
                    "(id, nom, ville, adresse, contact, d_limite, type) "
                    "VALUES (1, 'Foire historique', 'Tunis', 'Centre', 'Contact', "
                    "'2026-12-01', 'Salon')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO pos_sales (transaction_id, invoice_number, date) "
                    "VALUES (1, 'LEGACY-1', '2025-01-01')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO pos_products "
                    "(product_id, product_code, price, o_price) "
                    "VALUES (1, 'LEGACY-POS', 10, 5)"
                )
            )
        with self.database_path.open("rb") as database_file:
            self.original_bytes = database_file.read()

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_migration_backs_up_legacy_data_and_is_idempotent(self):
        backup_path = backup_before_pending_migrations(self.engine)
        self.assertIsNotNone(backup_path)
        self.assertTrue(backup_path.is_file())

        backup = sqlite3.connect(str(backup_path))
        try:
            self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                backup.execute("SELECT nom, d_limite FROM foires WHERE id = 1").fetchone(),
                ("Foire historique", "2026-12-01"),
            )
        finally:
            backup.close()

        apply_schema_migrations(self.engine)
        self.assertTrue(inspect(self.engine).has_table("fair_assignments"))
        self.assertTrue(inspect(self.engine).has_table("fair_inventory"))
        self.assertTrue(inspect(self.engine).has_table("fair_inventory_movements"))
        sale_columns = {
            column["name"] for column in inspect(self.engine).get_columns("pos_sales")
        }
        self.assertTrue({"fair_id", "seller_id", "cashier_user_id"}.issubset(sale_columns))
        product_columns = {
            column["name"] for column in inspect(self.engine).get_columns("pos_products")
        }
        self.assertIn("pricing_configured", product_columns)
        with self.engine.connect() as connection:
            trigger_names = set(
                connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
                ).scalars()
            )
        self.assertTrue(
            {
                "trg_fair_inventory_movements_no_update",
                "trg_fair_inventory_movements_no_delete",
            }.issubset(trigger_names)
        )
        columns = {
            column["name"] for column in inspect(self.engine).get_columns("foires")
        }
        self.assertTrue(
            {
                "organizer",
                "start_date",
                "end_date",
                "product_send_deadline",
                "status",
                "allow_late_send",
                "late_send_reason",
                "manager_notes",
                "assigned_vehicle_id",
            }.issubset(columns)
        )
        self.assertEqual(
            backup_before_pending_migrations(self.engine),
            None,
        )

        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text("SELECT nom, d_limite, status FROM foires WHERE id = 1")
                ).one(),
                ("Foire historique", "2026-12-01", None),
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT COUNT(*) FROM schema_migrations")
                ).scalar_one(),
                6,
            )
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT fair_id, seller_id, cashier_user_id "
                        "FROM pos_sales WHERE transaction_id = 1"
                    )
                ).one(),
                (None, None, None),
            )
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT pricing_configured FROM pos_products "
                        "WHERE product_id = 1"
                    )
                ).scalar_one(),
                1,
            )

        apply_schema_migrations(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text("SELECT COUNT(*) FROM schema_migrations")
                ).scalar_one(),
                6,
            )
        with self.database_path.open("rb") as database_file:
            self.assertNotEqual(database_file.read(), self.original_bytes)

    def test_migration_does_not_recreate_existing_fair_columns(self):
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE foires ADD COLUMN start_date DATE"))
        apply_schema_migrations(self.engine)
        self.assertEqual(
            sum(
                column["name"] == "start_date"
                for column in inspect(self.engine).get_columns("foires")
            ),
            1,
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text("SELECT COUNT(*) FROM foires")
                ).scalar_one(),
                1,
            )

    def test_failed_migration_rolls_back_schema_and_version_record(self):
        def fail_after_ddl(connection):
            connection.execute(
                text('ALTER TABLE foires ADD COLUMN "temporary_column" TEXT')
            )
            raise RuntimeError("migration failed")

        with patch.dict(
            schema_migrations._MIGRATION_FUNCTIONS,
            {"_add_fair_metadata_and_system_settings": fail_after_ddl},
        ):
            with self.assertRaisesRegex(RuntimeError, "migration failed"):
                apply_schema_migrations(self.engine)

        self.assertFalse(inspect(self.engine).has_table("schema_migrations"))
        columns = {
            column["name"] for column in inspect(self.engine).get_columns("foires")
        }
        self.assertNotIn("temporary_column", columns)


if __name__ == "__main__":
    unittest.main()
