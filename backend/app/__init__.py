import json
import html
import os
from pathlib import Path

from flask import Flask, make_response, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

from .config import Config
from .schema_migrations import (
    apply_schema_migrations,
    backup_before_pending_migrations,
)


db = SQLAlchemy()


def _add_legacy_columns(engine):
    column_definitions = {
        "users": {"ville": "VARCHAR(100)"},
        "clients": {"specialite": "VARCHAR(100)", "ville": "VARCHAR(100)"},
        "fournisseurs": {"specialite": "VARCHAR(100)", "ville": "VARCHAR(100)"},
        "voitures": {
            "location": "BOOLEAN",
            "date_d_loc": "VARCHAR(10)",
            "date_f_loc": "VARCHAR(10)",
        },
        "foires": {"type": "VARCHAR(30)"},
        "reservations": {"etat": "INTEGER", "date_c": "VARCHAR(10)"},
    }
    with engine.begin() as connection:
        for table, columns in column_definitions.items():
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')
                    )


def _restore_archived_legacy_fields(engine):
    targets = {
        "utilisateurs": ("users", "id", {"ville": ("ville", str)}),
        "clients": (
            "clients",
            "id",
            {"specialite": ("specialite", str), "ville": ("ville", str)},
        ),
        "fournisseurs": (
            "fournisseurs",
            "id",
            {"specialite": ("specialite", str), "ville": ("ville", str)},
        ),
        "voitures": (
            "voitures",
            "id",
            {
                "location": ("location", bool),
                "date_d_loc": ("date_d_loc", str),
                "date_f_loc": ("date_f_loc", str),
            },
        ),
        "stores": ("foires", "id", {"type": ("type", str)}),
        "reservations": (
            "reservations",
            "id",
            {"etat": ("etat", int), "date_c": ("date_c", str)},
        ),
    }
    if "legacy_import_extras" not in inspect(engine).get_table_names():
        return

    with engine.begin() as connection:
        extras = connection.execute(
            text(
                "SELECT source_table, source_key, extra_json "
                "FROM legacy_import_extras"
            )
        )
        for source_table, source_key, extra_json in extras:
            target = targets.get(source_table)
            if target is None:
                continue
            table, key_column, field_map = target
            legacy_values = json.loads(extra_json)
            updates = {}
            for column, (legacy_field, convert) in field_map.items():
                value = legacy_values.get(legacy_field)
                if value is not None:
                    updates[column] = convert(value)
            if not updates:
                continue
            assignments = ", ".join(f'"{column}" = :{column}' for column in updates)
            connection.execute(
                text(
                    f'UPDATE "{table}" SET {assignments} '
                    f'WHERE "{key_column}" = :source_key AND '
                    + " AND ".join(f'"{column}" IS NULL' for column in updates)
                ),
                {**updates, "source_key": source_key},
            )


def _add_pos_columns(engine):
    column_definitions = {
        "pos_products": {
            "article_ref": "VARCHAR(50) REFERENCES articles(ref) ON DELETE RESTRICT",
            "barcode": "VARCHAR(120)",
        },
        "articles": {
            "barcode": "VARCHAR(120)",
        },
        "pos_sales": {
            "customer_id": "INTEGER REFERENCES pos_customers(customer_id)",
            "register_code": "VARCHAR(64)",
        },
        "pos_purchases": {
            "supplier_id": "INTEGER REFERENCES pos_suppliers(supplier_id)",
        },
    }
    with engine.begin() as connection:
        for table, columns in column_definitions.items():
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')
                    )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ux_pos_products_article_ref ON pos_products (article_ref)"
            )
        )


def _backfill_pos_opening_movements(app):
    from .models import PosProduct, PosStockMovement

    with app.app_context():
        products = PosProduct.query.filter(PosProduct.qty > 0).all()
        existing_ids = {
            movement.product_id
            for movement in PosStockMovement.query.filter_by(
                movement_type="opening",
                reference_type="product",
            ).all()
        }
        for product in products:
            if product.product_id not in existing_ids:
                db.session.add(
                    PosStockMovement(
                        product_id=product.product_id,
                        movement_type="opening",
                        quantity_delta=product.qty,
                        unit_cost=product.o_price,
                        reference_type="product",
                        reference_id=product.product_id,
                    )
                )
        if db.session.new:
            db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    if app.config["APP_ENV"] == "production" and not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set when APP_ENV=production.")

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config["CORS_ORIGINS"]
            }
        },
        supports_credentials=True,
    )

    db.init_app(app)

    from .routes import api_bp
    app.register_blueprint(api_bp)

    # -----------------------------------------------------------------------
    # Mesures de securite : En-tetes HTTP, Protection CSRF & Error Handlers
    # -----------------------------------------------------------------------

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not response.headers.get("Content-Security-Policy"):
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://unpkg.com; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self' http://localhost:5100 http://127.0.0.1:5100; "
                "frame-ancestors 'self';"
            )
            response.headers["Content-Security-Policy"] = csp
        return response

    @app.before_request
    def validate_request_security():
        from flask import request, jsonify
        if request.path.startswith("/api/"):
            if request.method in ("POST", "PUT", "DELETE", "PATCH"):
                origin = request.headers.get("Origin")
                if origin:
                    allowed_origins = app.config.get("CORS_ORIGINS", [])
                    if (
                        origin not in allowed_origins
                        and not origin.startswith(("http://localhost:", "http://127.0.0.1:"))
                        and not origin.endswith((".vercel.app", ".pages.dev", ".onrender.com"))
                    ):
                        return jsonify({"error": "Origine non autorisee (protection CSRF)."}), 403

    @app.errorhandler(413)
    def request_entity_too_large(error):
        from flask import jsonify
        return jsonify({"error": "Le volume des donnees envoyees depasse la limite autorisee (5 Mo)."}), 413

    @app.errorhandler(500)
    def internal_server_error(error):
        import logging
        from flask import jsonify
        logging.getLogger("okba_audit").error(f"Erreur interne 500 : {error}")
        return jsonify({"error": "Une erreur interne du serveur est survenue."}), 500

    frontend_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    )

    @app.get("/")
    def frontend_index():
        index_path = Path(frontend_dir) / "index.html"
        content = index_path.read_text(encoding="utf-8").replace(
            'content="__OKBA_API_URL__"',
            f'content="{html.escape(app.config["PUBLIC_API_URL"], quote=True)}"',
            1,
        )
        resp = make_response(content)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    @app.get("/src/<path:filename>")
    def frontend_asset(filename):
        resp = send_from_directory(os.path.join(frontend_dir, "src"), filename)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    with app.app_context():
        backup_before_pending_migrations(db.engine)
        db.create_all()
        _add_legacy_columns(db.engine)
        _add_pos_columns(db.engine)
        _restore_archived_legacy_fields(db.engine)
        sale_columns = {
            column["name"] for column in inspect(db.engine).get_columns("pos_sales")
        }
        if "paid_amount" not in sale_columns:
            with db.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE pos_sales "
                        "ADD COLUMN paid_amount NUMERIC(12, 2) NOT NULL DEFAULT 0"
                    )
                )
        apply_schema_migrations(db.engine)

    _backfill_pos_opening_movements(app)
    return app
