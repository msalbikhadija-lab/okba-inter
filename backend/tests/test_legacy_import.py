import json
import unittest

from sqlalchemy import create_engine, text
from werkzeug.security import check_password_hash

from app import _add_legacy_columns, _restore_archived_legacy_fields
from import_legacy_sql import build_migration_plan, parse_legacy_sql


class LegacyImportTests(unittest.TestCase):
    def test_parser_handles_escaped_quotes_and_semicolons(self):
        source = """
        INSERT INTO `clients` (`id`, `nom`, `prenom`, `tel`, `email`, `specialite`, `ville`) VALUES
        (1, 'O\\'Brien; fils', 'Jean', 1234, 'j@example.com', 'Bois', 'Paris');
        """
        tables = parse_legacy_sql(source)
        self.assertEqual(tables["clients"][0]["nom"], "O'Brien; fils")

    def test_plan_hashes_legacy_password_and_preserves_extra_fields(self):
        source = """
        INSERT INTO `utilisateurs` (`id`, `nom`, `prenom`, `login`, `pw`, `type`, `lpp`, `ville`) VALUES
        (1, 'Admin', 'Test', 'admin-test', 'test-password', 'admin', 8, 'Paris');
        INSERT INTO `clients` (`id`, `nom`, `prenom`, `tel`, `email`, `specialite`, `ville`) VALUES
        (1, 'Client', 'Test', 1234, 'client@example.test', 'Bois', 'Paris');
        INSERT INTO `articles` (`famille`, `description`, `categorie`, `ref`, `nom`, `v_entrees`, `v_retour`, `v_stocks`) VALUES
        ('Bois', 'Planche', 'A', 'REF-1', 'Article; test', 4, 1, 3);
        INSERT INTO `droits` (`type_user`, `foire`, `stand`, `liste_stand`, `article`, `work`, `fournisseur`, `client`, `reservation`, `empl`, `voiture`, `mouvement`, `livraison`, `reception`, `vente`, `achat`) VALUES
        ('admin', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        """
        plan, extras, skipped, warnings = build_migration_plan(
            parse_legacy_sql(source)
        )
        user = plan["users"][0]
        self.assertTrue(check_password_hash(user["pw"], "test-password"))
        self.assertNotEqual(user["pw"], "test-password")
        self.assertEqual(user["ville"], "Paris")
        self.assertEqual(plan["clients"][0]["specialite"], "Bois")
        self.assertEqual(plan["clients"][0]["ville"], "Paris")
        self.assertEqual(plan["articles"][0]["nom"], "Article; test")
        self.assertFalse(any(item["source_table"] == "utilisateurs" for item in extras))
        self.assertFalse(skipped)
        self.assertFalse(warnings)

    def test_unresolved_legacy_records_are_archived(self):
        source = """
        INSERT INTO `utilisateurs` (`id`, `nom`, `prenom`, `login`, `pw`, `type`, `lpp`, `ville`) VALUES
        (1, 'Admin', 'Test', 'admin-test', 'test-password', 'admin', 8, 'Paris');
        INSERT INTO `works` (`id`, `date_d`, `date_f`, `id_foire`, `id_stand`, `id_vendeur`, `id_deco`, `id_chauffeur`, `id_voiture`, `flow`) VALUES
        (1, '2022-01-01', '2022-01-02', 27, 101, 1, 1, 1, 1, 'en attente');
        INSERT INTO `confirmations` (`id`, `c_vendeur`, `c_chauffeur`, `c_deco`) VALUES
        (1, 1, 0, 0);
        """
        plan, extras, skipped, warnings = build_migration_plan(
            parse_legacy_sql(source)
        )
        self.assertEqual(skipped["works"], 1)
        self.assertEqual(skipped["confirmations"], 1)
        self.assertEqual(plan["works"], [])
        archived_tables = {item["source_table"] for item in extras}
        self.assertIn("works", archived_tables)
        self.assertIn("confirmations", archived_tables)
        self.assertFalse(warnings)

    def test_schema_upgrade_restores_archived_fields_idempotently(self):
        engine = create_engine("sqlite://")
        base_tables = {
            "users": 'id INTEGER PRIMARY KEY, nom TEXT, prenom TEXT, login TEXT, pw TEXT, type TEXT, lpp INTEGER',
            "clients": 'id INTEGER PRIMARY KEY, nom TEXT, prenom TEXT, tel TEXT, email TEXT',
            "fournisseurs": 'id INTEGER PRIMARY KEY, nom TEXT, prenom TEXT, tel TEXT, email TEXT',
            "voitures": 'id INTEGER PRIMARY KEY, model TEXT, immatricule TEXT, annee INTEGER, puissance INTEGER',
            "foires": 'id INTEGER PRIMARY KEY, nom TEXT, ville TEXT, adresse TEXT, contact TEXT, d_limite TEXT',
            "reservations": 'id INTEGER PRIMARY KEY, id_agent INTEGER, id_foire INTEGER, taille_stand TEXT, logement TEXT, date_d TEXT, date_f TEXT',
        }
        extras = (
            ("utilisateurs", "1", {"ville": "Sousse"}),
            ("clients", "2", {"specialite": "Bois", "ville": "Tunis"}),
            ("fournisseurs", "3", {"specialite": "Aluminium", "ville": "Sfax"}),
            (
                "voitures",
                "4",
                {"location": 0, "date_d_loc": "2021-01-01", "date_f_loc": "2021-01-02"},
            ),
            ("stores", "5", {"type": "boutique"}),
            ("reservations", "6", {"etat": 1, "date_c": "2021-01-03"}),
        )
        try:
            with engine.begin() as connection:
                for table, columns in base_tables.items():
                    connection.execute(text(f'CREATE TABLE "{table}" ({columns})'))
                for table, record_id in (
                    ("users", 1),
                    ("clients", 2),
                    ("fournisseurs", 3),
                    ("voitures", 4),
                    ("foires", 5),
                    ("reservations", 6),
                ):
                    connection.execute(
                        text(f'INSERT INTO "{table}" (id) VALUES (:id)'),
                        {"id": record_id},
                    )
                connection.execute(
                    text(
                        "CREATE TABLE legacy_import_extras "
                        "(source_table TEXT, source_key TEXT, extra_json TEXT)"
                    )
                )
                for source_table, source_key, values in extras:
                    connection.execute(
                        text(
                            "INSERT INTO legacy_import_extras "
                            "(source_table, source_key, extra_json) "
                            "VALUES (:source_table, :source_key, :extra_json)"
                        ),
                        {
                            "source_table": source_table,
                            "source_key": source_key,
                            "extra_json": json.dumps(values),
                        },
                    )
            _add_legacy_columns(engine)
            _restore_archived_legacy_fields(engine)
            with engine.begin() as connection:
                restored = {
                    "user_city": connection.execute(
                        text('SELECT ville FROM users WHERE id = 1')
                    ).scalar_one(),
                    "client": connection.execute(
                        text('SELECT specialite, ville FROM clients WHERE id = 2')
                    ).one(),
                    "supplier": connection.execute(
                        text(
                            'SELECT specialite, ville FROM fournisseurs WHERE id = 3'
                        )
                    ).one(),
                    "vehicle": connection.execute(
                        text(
                            'SELECT location, date_d_loc, date_f_loc '
                            'FROM voitures WHERE id = 4'
                        )
                    ).one(),
                    "fair_type": connection.execute(
                        text('SELECT type FROM foires WHERE id = 5')
                    ).scalar_one(),
                    "reservation": connection.execute(
                        text('SELECT etat, date_c FROM reservations WHERE id = 6')
                    ).one(),
                }
                self.assertEqual(restored["user_city"], "Sousse")
                self.assertEqual(tuple(restored["client"]), ("Bois", "Tunis"))
                self.assertEqual(tuple(restored["supplier"]), ("Aluminium", "Sfax"))
                self.assertEqual(
                    tuple(restored["vehicle"]),
                    (0, "2021-01-01", "2021-01-02"),
                )
                self.assertEqual(restored["fair_type"], "boutique")
                self.assertEqual(tuple(restored["reservation"]), (1, "2021-01-03"))
                connection.execute(
                    text('UPDATE users SET ville = :ville WHERE id = 1'),
                    {"ville": "Updated city"},
                )
            _restore_archived_legacy_fields(engine)
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(
                        text('SELECT ville FROM users WHERE id = 1')
                    ).scalar_one(),
                    "Updated city",
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
