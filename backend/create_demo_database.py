import os
import sys
from pathlib import Path

from sqlalchemy import inspect

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database" / "app.demo.db"
ACTIVE_DATABASE_PATH = BASE_DIR / "database" / "app.db"


def main():
    destination = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else DATABASE_PATH
    if destination == ACTIVE_DATABASE_PATH.resolve():
        raise SystemExit("Refus : le générateur de démonstration ne modifie jamais app.db.")
    if destination.exists():
        raise SystemExit(f"Refus d’écraser une base existante : {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{destination.as_posix()}"
    os.environ.setdefault("APP_ENV", "development")
    sys.path.insert(0, str(BASE_DIR))

    from app import create_app, db
    from app.models import Article, PosProduct, PosStockMovement

    app = create_app()
    demo_items = (
        {
            "ref": "DEMO-001",
            "family": "Démonstration",
            "category": "Accessoire",
            "name": "Sac de démonstration",
            "stock": 12,
            "cost": "8.00",
            "price": "15.00",
        },
        {
            "ref": "DEMO-002",
            "family": "Démonstration",
            "category": "Décoration",
            "name": "Lampe de démonstration",
            "stock": 6,
            "cost": "20.00",
            "price": "35.00",
        },
        {
            "ref": "DEMO-003",
            "family": "Démonstration",
            "category": "Mobilier",
            "name": "Chaise de démonstration",
            "stock": 4,
            "cost": "30.00",
            "price": "49.00",
        },
    )

    with app.app_context():
        for item in demo_items:
            article = Article(
                ref=item["ref"],
                famille=item["family"],
                description="Article fictif pour tester l’application.",
                categorie=item["category"],
                nom=item["name"],
                v_entrees=item["stock"],
                v_retour=0,
                v_stocks=item["stock"],
            )
            product = PosProduct(
                article=article,
                product_code=item["ref"],
                gen_name=item["name"],
                product_name=item["category"],
                supplier="Fournisseur de démonstration",
                date_arrival="2026-01-01",
                expiry_date="",
                price=item["price"],
                o_price=item["cost"],
                qty=item["stock"],
                qty_sold=0,
            )
            db.session.add_all(
                [
                    article,
                    product,
                    PosStockMovement(
                        product=product,
                        movement_type="opening",
                        quantity_delta=item["stock"],
                        unit_cost=item["cost"],
                        reference_type="product",
                    ),
                ]
            )
        db.session.commit()
        table_names = set(inspect(db.engine).get_table_names())
        required_tables = {
            "users",
            "articles",
            "pos_products",
            "pos_sales",
            "pos_purchases",
            "pos_collections",
            "pos_stock_movements",
        }
        if not required_tables.issubset(table_names):
            raise RuntimeError("Le schéma de démonstration est incomplet.")
        if destination == ACTIVE_DATABASE_PATH.resolve():
            raise RuntimeError("Le chemin de destination correspond à la base active.")
        db.engine.dispose()

    print(f"Base de démonstration fictive créée : {destination}")
    print("Catalogue : 3 produits liés au stock. Aucun compte utilisateur n’a été créé.")
    print("Créez l’administrateur séparément avec create_admin.py.")


if __name__ == "__main__":
    main()
