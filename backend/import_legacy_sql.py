import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = BACKEND_DIR / "database" / "app.db"
LEGACY_TABLES = {
    "utilisateurs",
    "clients",
    "articles",
    "fournisseurs",
    "voitures",
    "stores",
    "liste_stands",
    "stands",
    "reservations",
    "works",
    "confirmations",
    "droits",
    "receptions",
    "specialites",
    "villes",
    "domaines",
}
VALID_ROLES = {
    "admin",
    "chauffeur",
    "chef",
    "vendeur",
    "deco",
    "reservation",
    "laga",
    "compta",
}
PERMISSION_FIELDS = (
    "foire",
    "stand",
    "liste_stand",
    "article",
    "work",
    "fournisseur",
    "client",
    "reservation",
    "empl",
    "voiture",
    "mouvement",
    "livraison",
    "reception",
    "vente",
    "achat",
)


def _decode_mysql_string(value):
    escapes = {
        "0": "\0",
        "b": "\b",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "Z": "\x1a",
        "\\": "\\",
        "'": "'",
        '"': '"',
    }
    result = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            index += 1
            result.append(escapes.get(value[index], value[index]))
        else:
            result.append(value[index])
        index += 1
    return "".join(result).replace("''", "'")


def _parse_value(token):
    token = token.strip()
    if token.upper() == "NULL":
        return None
    if token.startswith("'") and token.endswith("'"):
        return _decode_mysql_string(token[1:-1])
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token)
    raise ValueError("Unsupported SQL value in legacy INSERT statement.")


def _parse_value_tuples(values):
    rows = []
    index = 0
    while index < len(values):
        while index < len(values) and (values[index].isspace() or values[index] == ","):
            index += 1
        if index == len(values):
            break
        if values[index] != "(":
            raise ValueError("Unsupported syntax in legacy INSERT statement.")

        index += 1
        row = []
        token = []
        quoted = False
        escaped = False
        while index < len(values):
            character = values[index]
            if quoted:
                token.append(character)
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == "'":
                    if index + 1 < len(values) and values[index + 1] == "'":
                        index += 1
                        token.append(values[index])
                    else:
                        quoted = False
            elif character == "'":
                quoted = True
                token.append(character)
            elif character == ",":
                row.append(_parse_value("".join(token)))
                token = []
            elif character == ")":
                row.append(_parse_value("".join(token)))
                rows.append(row)
                break
            else:
                token.append(character)
            index += 1
        else:
            raise ValueError("Unterminated values in legacy INSERT statement.")
        index += 1
    return rows


def _insert_statements(sql_text):
    start_pattern = re.compile(
        r"(?is)INSERT\s+INTO\s+`([^`]+)`\s*\((.*?)\)\s*VALUES\s*"
    )
    for match in start_pattern.finditer(sql_text):
        index = match.end()
        quoted = False
        escaped = False
        while index < len(sql_text):
            character = sql_text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == "'":
                    if index + 1 < len(sql_text) and sql_text[index + 1] == "'":
                        index += 1
                    else:
                        quoted = False
            elif character == "'":
                quoted = True
            elif character == ";":
                break
            index += 1
        if index == len(sql_text):
            raise ValueError("Unterminated INSERT statement in legacy SQL file.")
        columns = re.findall(r"`([^`]+)`", match.group(2))
        yield match.group(1), columns, _parse_value_tuples(
            sql_text[match.end() : index]
        )


def parse_legacy_sql(sql_text):
    tables = {}
    for table, columns, rows in _insert_statements(sql_text):
        if table not in LEGACY_TABLES:
            continue
        for values in rows:
            if len(values) != len(columns):
                raise ValueError(f"Column count mismatch in legacy table {table}.")
            tables.setdefault(table, []).append(dict(zip(columns, values)))
    return tables


def _text(value):
    return "" if value is None else str(value)


def _integer(value, field, table):
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid integer in {table}.{field}.") from error


def _archive(extras, table, key, data, note=""):
    if data or note:
        extras.append(
            {
                "source_table": table,
                "source_key": _text(key),
                "extra_json": json.dumps(data, ensure_ascii=False, sort_keys=True),
                "note": note,
            }
        )


def build_migration_plan(tables):
    plan = {}
    extras = []
    skipped = Counter()
    warnings = Counter()

    source_users = tables.get("utilisateurs", [])
    users = []
    for row in source_users:
        role = _text(row.get("type"))
        if role not in VALID_ROLES:
            raise ValueError("The legacy SQL file contains an unsupported user role.")
        password = _text(row.get("pw"))
        if not password:
            raise ValueError("A legacy user has an empty password.")
        if not password.startswith(("scrypt:", "pbkdf2:")):
            password = generate_password_hash(password)
        users.append(
            {
                "id": _integer(row.get("id"), "id", "utilisateurs"),
                "nom": _text(row.get("nom")),
                "prenom": _text(row.get("prenom")),
                "login": _text(row.get("login")),
                "pw": password,
                "type": role,
                "lpp": _integer(row.get("lpp"), "lpp", "utilisateurs"),
                "ville": _text(row.get("ville")),
            }
        )
    plan["users"] = users

    plan["articles"] = [
        {
            "ref": _text(row.get("ref")),
            "famille": _text(row.get("famille")),
            "description": _text(row.get("description")),
            "categorie": _text(row.get("categorie")),
            "nom": _text(row.get("nom")),
            "v_entrees": _integer(row.get("v_entrees"), "v_entrees", "articles"),
            "v_retour": _integer(row.get("v_retour"), "v_retour", "articles"),
            "v_stocks": _integer(row.get("v_stocks"), "v_stocks", "articles"),
        }
        for row in tables.get("articles", [])
    ]

    plan["clients"] = []
    for row in tables.get("clients", []):
        plan["clients"].append(
            {
                "id": _integer(row.get("id"), "id", "clients"),
                "nom": _text(row.get("nom")),
                "prenom": _text(row.get("prenom")),
                "tel": _text(row.get("tel")),
                "email": _text(row.get("email")),
                "specialite": _text(row.get("specialite")),
                "ville": _text(row.get("ville")),
            }
        )

    plan["fournisseurs"] = []
    for row in tables.get("fournisseurs", []):
        plan["fournisseurs"].append(
            {
                "id": _integer(row.get("id"), "id", "fournisseurs"),
                "nom": _text(row.get("nom")),
                "prenom": _text(row.get("prenom")),
                "tel": _text(row.get("tel")),
                "email": _text(row.get("email")),
                "specialite": _text(row.get("specialite")),
                "ville": _text(row.get("ville")),
            }
        )

    plan["voitures"] = []
    for row in tables.get("voitures", []):
        plan["voitures"].append(
            {
                "id": _integer(row.get("id"), "id", "voitures"),
                "model": _text(row.get("model")),
                "immatricule": _text(row.get("immatricule")),
                "annee": _integer(row.get("annee"), "annee", "voitures"),
                "puissance": _integer(row.get("puissance"), "puissance", "voitures"),
                "location": bool(_integer(row.get("location"), "location", "voitures")),
                "date_d_loc": _text(row.get("date_d_loc")),
                "date_f_loc": _text(row.get("date_f_loc")),
            }
        )

    plan["foires"] = []
    for row in tables.get("stores", []):
        plan["foires"].append(
            {
                "id": _integer(row.get("id"), "id", "stores"),
                "nom": _text(row.get("nom")),
                "ville": _text(row.get("ville")),
                "adresse": _text(row.get("adresse")),
                "contact": _text(row.get("contact")),
                "d_limite": _text(row.get("d_limite")),
                "type": _text(row.get("type")),
            }
        )

    plan["liste_stands"] = [
        {
            "id": _integer(row.get("id"), "id", "liste_stands"),
            "type": _text(row.get("type")),
            "etat": _text(row.get("etat")),
        }
        for row in tables.get("liste_stands", [])
    ]

    plan["droits"] = []
    for row in tables.get("droits", []):
        role = _text(row.get("type_user"))
        if role not in VALID_ROLES:
            raise ValueError("The legacy SQL file contains an unsupported permission role.")
        plan["droits"].append(
            {
                "type_user": role,
                **{
                    field: bool(_integer(row.get(field, 0), field, "droits"))
                    for field in PERMISSION_FIELDS
                },
            }
        )

    article_refs = {row["ref"] for row in plan["articles"]}
    supplier_ids = {row["id"] for row in plan["fournisseurs"]}
    stand_ids = {row["id"] for row in plan["liste_stands"]}
    fair_ids = {row["id"] for row in plan["foires"]}
    user_ids = {row["id"] for row in plan["users"]}
    vehicle_ids = {row["id"] for row in plan["voitures"]}

    plan["stands"] = []
    for row in tables.get("stands", []):
        if _text(row.get("ref_article")) not in article_refs or _integer(
            row.get("id_stand"), "id_stand", "stands"
        ) not in stand_ids:
            skipped["stands"] += 1
            _archive(extras, "stands", row.get("id"), row, "missing article or stand type")
            continue
        plan["stands"].append(
            {
                "id": _integer(row.get("id"), "id", "stands"),
                "id_stand": _integer(row.get("id_stand"), "id_stand", "stands"),
                "ref_article": _text(row.get("ref_article")),
                "quantite": _integer(row.get("quantite"), "quantite", "stands"),
                "date_ch": _text(row.get("date_ch")),
            }
        )

    plan["reservations"] = []
    for row in tables.get("reservations", []):
        agent_id = _integer(row.get("id_agent"), "id_agent", "reservations")
        fair_id = _integer(row.get("id_foire"), "id_foire", "reservations")
        if agent_id not in user_ids or fair_id not in fair_ids:
            skipped["reservations"] += 1
            _archive(
                extras,
                "reservations",
                row.get("id"),
                row,
                "missing agent or fair",
            )
            continue
        plan["reservations"].append(
            {
                "id": _integer(row.get("id"), "id", "reservations"),
                "id_agent": agent_id,
                "id_foire": fair_id,
                "taille_stand": _text(row.get("taille_stand")),
                "logement": _text(row.get("logement")),
                "date_d": _text(row.get("date_d")),
                "date_f": _text(row.get("date_f")),
                "etat": _integer(row.get("etat", 0) or 0, "etat", "reservations"),
                "date_c": row.get("date_c"),
            }
        )

    plan["works"] = []
    valid_work_ids = set()
    for row in tables.get("works", []):
        references = {
            "id_foire": (fair_ids, "id_foire"),
            "id_stand": (stand_ids, "id_stand"),
            "id_vendeur": (user_ids, "id_vendeur"),
            "id_deco": (user_ids, "id_deco"),
            "id_chauffeur": (user_ids, "id_chauffeur"),
            "id_voiture": (vehicle_ids, "id_voiture"),
        }
        values = {
            field: _integer(row.get(field), field, "works")
            for field in references
        }
        if any(values[field] not in available for field, (available, _) in references.items()):
            skipped["works"] += 1
            _archive(extras, "works", row.get("id"), row, "missing linked record")
            continue
        work = {
            "id": _integer(row.get("id"), "id", "works"),
            "date_d": _text(row.get("date_d")),
            "date_f": _text(row.get("date_f")),
            **values,
            "flow": _text(row.get("flow")),
        }
        plan["works"].append(work)
        valid_work_ids.add(work["id"])

    plan["Confirmations"] = []
    for row in tables.get("confirmations", []):
        work_id = _integer(row.get("id"), "id", "confirmations")
        if work_id not in valid_work_ids:
            skipped["confirmations"] += 1
            _archive(extras, "confirmations", work_id, row, "mission not present")
            continue
        plan["Confirmations"].append(
            {
                "id": work_id,
                "c_vendeur": bool(_integer(row.get("c_vendeur"), "c_vendeur", "confirmations")),
                "c_chauffeur": bool(_integer(row.get("c_chauffeur"), "c_chauffeur", "confirmations")),
                "c_deco": bool(_integer(row.get("c_deco"), "c_deco", "confirmations")),
            }
        )

    plan["stock_movements"] = []
    for row in tables.get("receptions", []):
        article_ref = _text(row.get("id_article"))
        if article_ref not in article_refs:
            skipped["receptions"] += 1
            _archive(extras, "receptions", row.get("id"), row, "article not present")
            continue
        source_supplier_id = _integer(
            row.get("id_fournisseur"), "id_fournisseur", "receptions"
        )
        supplier_id = (
            source_supplier_id if source_supplier_id in supplier_ids else None
        )
        plan["stock_movements"].append(
            {
                "id": _integer(row.get("id"), "id", "receptions"),
                "type": "reception",
                "article_ref": article_ref,
                "quantite": _integer(row.get("quantite"), "quantite", "receptions"),
                "date_mouvement": _text(row.get("date_reception")),
                "id_fournisseur": supplier_id,
                "id_client": None,
            }
        )
        if supplier_id is None:
            warnings["receptions_without_supplier_link"] += 1
            _archive(
                extras,
                "receptions",
                row.get("id"),
                {"id_fournisseur": source_supplier_id},
                "supplier not present; movement imported without supplier link",
            )

    for table, key_field in (
        ("specialites", "id"),
        ("villes", "id"),
        ("domaines", "id"),
    ):
        for row in tables.get(table, []):
            _archive(
                extras,
                table,
                row.get(key_field),
                row,
                "legacy lookup retained for reference",
            )

    if len({row["id"] for row in plan["users"]}) != len(plan["users"]):
        raise ValueError("Duplicate user IDs in legacy SQL file.")
    if len({row["login"] for row in plan["users"]}) != len(plan["users"]):
        raise ValueError("Duplicate user logins in legacy SQL file.")
    if len({row["ref"] for row in plan["articles"]}) != len(plan["articles"]):
        raise ValueError("Duplicate article references in legacy SQL file.")
    if len({row["type_user"] for row in plan["droits"]}) != len(plan["droits"]):
        raise ValueError("Duplicate permission roles in legacy SQL file.")
    if len({row["id"] for row in plan["liste_stands"]}) != len(plan["liste_stands"]):
        raise ValueError("Duplicate stand IDs in legacy SQL file.")

    return plan, extras, skipped, warnings


def _print_plan(plan, extras, skipped, warnings):
    print("Legacy import preview (row values and credentials are not displayed):")
    for table, rows in sorted(plan.items()):
        print(f"  {table}: {len(rows)} rows")
    print(f"  archived legacy details: {len(extras)}")
    if skipped:
        print("  unresolved legacy records archived: " + ", ".join(
            f"{table}={count}" for table, count in sorted(skipped.items())
        ))
    if warnings:
        print("  imported records with unresolved links: " + ", ".join(
            f"{name}={count}" for name, count in sorted(warnings.items())
        ))


def _make_backup(database_path):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(
        f"{database_path.stem}.before-okba6-{stamp}.bak"
    )
    with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    return backup_path


def _prepare_database(database_path):
    os.environ["DATABASE_URL"] = "sqlite:///" + database_path.resolve().as_posix()
    sys.path.insert(0, str(BACKEND_DIR))
    from app import create_app, db

    app = create_app()
    with app.app_context():
        db.engine.dispose()


def _apply_plan(database_path, plan, extras):
    backup_path = _make_backup(database_path)
    _prepare_database(database_path)

    table_names = (
        "Confirmations",
        "clients",
        "articles",
        "droits",
        "fournisseurs",
        "foires",
        "liste_stands",
        "reservations",
        "stands",
        "stock_movements",
        "users",
        "voitures",
        "works",
    )
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        for table in table_names:
            count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if table == "users":
                rows = connection.execute('SELECT type FROM "users"').fetchall()
                if count > 1 or any(row[0] != "admin" for row in rows):
                    raise RuntimeError(
                        "Import refused: destination has user data beyond its initial administrator."
                    )
            elif count:
                raise RuntimeError(
                    f"Import refused: destination table {table} is not empty."
                )

        connection.execute("BEGIN")
        connection.execute("DELETE FROM users")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_import_extras (
                source_table TEXT NOT NULL,
                source_key TEXT NOT NULL,
                extra_json TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (source_table, source_key)
            )
            """
        )
        for table, rows in plan.items():
            if not rows:
                continue
            columns = tuple(rows[0])
            quoted_columns = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})',
                [tuple(row[column] for column in columns) for row in rows],
            )
        connection.executemany(
            """
            INSERT INTO legacy_import_extras
                (source_table, source_key, extra_json, note)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    item["source_table"],
                    item["source_key"],
                    item["extra_json"],
                    item["note"],
                )
                for item in extras
            ],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        raise
    connection.close()
    return backup_path


def main():
    parser = argparse.ArgumentParser(
        description="Preview or import the old OKBA MySQL SQL dump into SQLite."
    )
    parser.add_argument("sql_file", type=Path, help="Path to the legacy .sql export")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="Destination SQLite database (defaults to backend/database/app.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the import after creating a timestamped database backup",
    )
    args = parser.parse_args()

    sql_file = args.sql_file.resolve()
    database_path = args.database.resolve()
    if not sql_file.is_file():
        parser.error("The legacy SQL file does not exist.")
    if not database_path.is_file():
        parser.error("The destination database does not exist.")
    if sql_file == database_path:
        parser.error("The SQL source and SQLite destination must be different files.")

    sql_text = sql_file.read_text(encoding="utf-8", errors="strict")
    plan, extras, skipped, warnings = build_migration_plan(
        parse_legacy_sql(sql_text)
    )
    _print_plan(plan, extras, skipped, warnings)
    if not args.apply:
        print("Preview only. Add --apply to import; the destination is backed up first.")
        return

    backup = _apply_plan(database_path, plan, extras)
    print(f"Import completed. Previous database backup: {backup}")


if __name__ == "__main__":
    main()
