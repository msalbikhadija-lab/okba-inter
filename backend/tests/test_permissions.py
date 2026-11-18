import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.config import Config
from app.schema_migrations import apply_schema_migrations
from app.models import (
    Article,
    Fair,
    FairAssignment,
    FairInventoryBalance,
    FairInventoryMovement,
    Permission,
    PosCollection,
    PosCustomer,
    PosProduct,
    PosPurchase,
    PosSale,
    PosStockMovement,
    PosSupplier,
    StockMovement,
    Supplier,
    User,
    Vehicle,
)
from werkzeug.security import generate_password_hash

Config.SQLALCHEMY_DATABASE_URI = "sqlite://"


class ModulePermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        if cls.app.config["SQLALCHEMY_DATABASE_URI"] != "sqlite://":
            raise RuntimeError("Permission tests must use an isolated in-memory database.")

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        with db.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS schema_migrations")
        apply_schema_migrations(db.engine)
        self.client = self.app.test_client()

        roles = (
            ("admin", "admin"),
            ("seller", "vendeur"),
            ("driver", "chauffeur"),
            ("clerk", "reservation"),
            ("employee", "chef"),
        )
        for login, role in roles:
            db.session.add(
                User(
                    nom="Test",
                    prenom=login,
                    login=login,
                    pw=generate_password_hash("test-password-123"),
                    type=role,
                    lpp=8,
                )
            )
        db.session.add(
            Permission(
                type_user="vendeur",
                client=True,
                article=True,
                vente=True,
            )
        )
        db.session.add(Permission(type_user="chauffeur", voiture=True))
        db.session.add(
            Permission(type_user="reservation", reservation=True)
        )
        db.session.add(Permission(type_user="chef", empl=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def sign_in(self, login):
        response = self.client.post(
            "/api/login",
            json={"login": login, "password": "test-password-123"},
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["user"]

    def test_production_requires_a_secret_key(self):
        with patch.object(Config, "APP_ENV", "production"), patch.object(
            Config, "SECRET_KEY", None
        ):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                create_app()

    def test_frontend_is_served_with_same_origin_api_url(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('content="/api"', response.get_data(as_text=True))
        asset = self.client.get("/src/App.js")
        self.assertEqual(asset.status_code, 200)
        self.assertIn(b"configuredApiUrl", asset.data)
        asset.close()

    def test_public_admin_seed_is_disabled_in_production(self):
        previous_environment = self.app.config["APP_ENV"]
        self.app.config["APP_ENV"] = "production"
        try:
            response = self.client.post("/api/seed")
        finally:
            self.app.config["APP_ENV"] = previous_environment
        self.assertEqual(response.status_code, 404)
        self.assertEqual(User.query.count(), 5)

    def test_cors_accepts_configured_frontend_origin(self):
        origin = "https://frontend.example.test"
        with patch.object(Config, "CORS_ORIGINS", [origin]):
            app = create_app()
        response = app.test_client().options(
            "/api/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), origin)
        self.assertEqual(response.headers.get("Access-Control-Allow-Credentials"), "true")

    def test_login_and_session_include_role_permissions(self):
        user = self.sign_in("seller")
        self.assertTrue(user["permissions"]["client"])
        self.assertFalse(user["permissions"]["fournisseur"])

        current = self.client.get("/api/me").get_json()["user"]
        self.assertEqual(current["permissions"], user["permissions"])

    def test_system_currency_is_readable_by_users_and_writable_only_by_admins(self):
        self.assertEqual(self.client.get("/api/settings").status_code, 401)

        self.sign_in("seller")
        self.assertEqual(
            self.client.get("/api/settings").get_json()["currency"],
            "TND",
        )
        self.assertEqual(
            self.client.put("/api/settings", json={"currency": "EUR"}).status_code,
            403,
        )

        self.client.post("/api/logout")
        self.sign_in("admin")
        invalid = self.client.put("/api/settings", json={"currency": "EURO"})
        self.assertEqual(invalid.status_code, 400)
        saved = self.client.put("/api/settings", json={"currency": "eur"})
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(saved.get_json()["currency"], "EUR")
        self.assertEqual(
            self.client.get("/api/settings").get_json()["currency"],
            "EUR",
        )

    def test_fair_metadata_and_date_rules(self):
        self.sign_in("admin")
        invalid_dates = self.client.post(
            "/api/fairs",
            json={
                "nom": "Foire invalide",
                "ville": "Tunis",
                "adresse": "Adresse",
                "contact": "Contact",
                "d_limite": "2026-10-01",
                "start_date": "2026-10-20",
                "end_date": "2026-10-19",
                "status": "planned",
            },
        )
        self.assertEqual(invalid_dates.status_code, 400)

        late_without_reason = self.client.post(
            "/api/fairs",
            json={
                "nom": "Foire sans raison",
                "ville": "Tunis",
                "adresse": "Adresse",
                "contact": "Contact",
                "d_limite": "2026-10-01",
                "start_date": "2026-10-20",
                "end_date": "2026-10-22",
                "product_send_deadline": "2026-10-21",
                "status": "planned",
                "allow_late_send": True,
                "late_send_reason": "",
            },
        )
        self.assertEqual(late_without_reason.status_code, 400)

        created = self.client.post(
            "/api/fairs",
            json={
                "nom": "Foire complète",
                "ville": "Tunis",
                "adresse": "Adresse",
                "contact": "Contact",
                "d_limite": "2026-10-01",
                "organizer": "Organisateur",
                "start_date": "2026-10-20",
                "end_date": "2026-10-22",
                "product_send_deadline": "2026-10-18",
                "status": "planned",
                "allow_late_send": True,
                "late_send_reason": "Validation du responsable",
                "manager_notes": "Préparer le stand",
            },
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        fair = created.get_json()["item"]
        self.assertEqual(fair["start_date"], "2026-10-20")
        self.assertEqual(fair["product_send_deadline"], "2026-10-18")
        self.assertEqual(fair["status"], "planned")
        self.assertTrue(fair["allow_late_send"])
        self.assertEqual(fair["late_send_reason"], "Validation du responsable")

    def test_creating_fair_automatically_assigns_team_vehicle_and_pos_context(self):
        self.sign_in("admin")
        today = date.today().isoformat()

        missing_dates = self.client.post(
            "/api/fairs",
            json={
                "nom": "Foire sans dates",
                "ville": "Tunis",
                "adresse": "Centre",
                "contact": "Contact",
                "d_limite": today,
                "auto_assign": True,
            },
        )
        self.assertEqual(missing_dates.status_code, 400)
        self.assertEqual(Fair.query.count(), 0)

        unavailable = self.client.post(
            "/api/fairs",
            json={
                "nom": "Foire sans véhicule",
                "ville": "Tunis",
                "adresse": "Centre",
                "contact": "Contact",
                "d_limite": today,
                "start_date": today,
                "end_date": today,
                "auto_assign": True,
            },
        )
        self.assertEqual(unavailable.status_code, 409)
        self.assertEqual(Fair.query.count(), 0)

        vehicle = Vehicle(
            model="Camionnette test",
            immatricule="AUTO-FAIR-1",
            annee=2024,
            puissance=6,
            location=False,
        )
        db.session.add(vehicle)
        db.session.commit()

        created = self.client.post(
            "/api/fairs",
            json={
                "nom": "Foire automatique",
                "ville": "Tunis",
                "adresse": "Centre",
                "contact": "Contact",
                "d_limite": today,
                "start_date": today,
                "end_date": today,
                "status": "planned",
                "auto_assign": True,
            },
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        result = created.get_json()
        fair_id = result["item"]["id"]
        self.assertIn("vendeur, chauffeur et véhicule", result["message"])
        self.assertEqual(result["item"]["assigned_vehicle_id"], vehicle.id)
        self.assertEqual(result["item"]["vehicle_name"], "Camionnette test — AUTO-FAIR-1")
        self.assertEqual(
            {assignment["role"] for assignment in result["assignments"]},
            {"vendeur", "chauffeur"},
        )
        self.assertTrue(all(item["source"] == "automatic" for item in result["assignments"]))
        self.assertEqual(
            FairAssignment.query.filter_by(fair_id=fair_id).count(),
            2,
        )

        contexts = self.client.get("/api/pos/fair-contexts")
        self.assertEqual(contexts.status_code, 200, contexts.get_json())
        context = next(
            row for row in contexts.get_json() if row["fair_id"] == fair_id
        )
        self.assertEqual(len(context["sellers"]), 1)

    def test_fair_assignment_suggestions_require_manager_selection_and_detect_conflicts(self):
        self.sign_in("admin")
        fair_response = self.client.post(
            "/api/fairs",
            json={
                "nom": "Salon de novembre",
                "ville": "Tunis",
                "adresse": "Centre",
                "contact": "Contact",
                "d_limite": "2026-10-01",
                "start_date": "2026-11-01",
                "end_date": "2026-11-05",
            },
        )
        self.assertEqual(fair_response.status_code, 201, fair_response.get_json())
        fair_id = fair_response.get_json()["item"]["id"]
        suggestion_payload = {
            "fair_id": fair_id,
            "role": "vendeur",
            "start_date": "2026-11-01",
            "end_date": "2026-11-05",
        }

        suggestions = self.client.post(
            "/api/fair-assignments/suggestions",
            json=suggestion_payload,
        )
        self.assertEqual(suggestions.status_code, 200, suggestions.get_json())
        seller = next(
            suggestion for suggestion in suggestions.get_json()["suggestions"]
            if suggestion["user_id"] == 2
        )
        self.assertTrue(seller["available"])
        self.assertEqual(
            self.client.get("/api/fair-assignments").get_json(),
            [],
            "Suggestions must not assign anyone without manager confirmation.",
        )

        assignment = self.client.post(
            "/api/fair-assignments",
            json={
                **suggestion_payload,
                "user_id": 2,
                "notes": "Affectation approuvée par le responsable",
            },
        )
        self.assertEqual(assignment.status_code, 201, assignment.get_json())
        self.assertEqual(assignment.get_json()["item"]["source"], "manual")
        self.assertEqual(assignment.get_json()["item"]["status"], "confirmed")
        self.assertEqual(len(self.client.get("/api/fair-assignments").get_json()), 1)

        overlapping = self.client.post(
            "/api/fair-assignments",
            json={
                **suggestion_payload,
                "user_id": 2,
            },
        )
        self.assertEqual(overlapping.status_code, 409)
        refreshed_suggestions = self.client.post(
            "/api/fair-assignments/suggestions",
            json=suggestion_payload,
        )
        seller_after_assignment = next(
            suggestion for suggestion in refreshed_suggestions.get_json()["suggestions"]
            if suggestion["user_id"] == 2
        )
        self.assertFalse(seller_after_assignment["available"])
        self.assertIn("Salon de novembre", seller_after_assignment["conflict"])

        outside_fair = self.client.post(
            "/api/fair-assignments",
            json={
                **suggestion_payload,
                "user_id": 2,
                "start_date": "2026-10-31",
            },
        )
        self.assertEqual(outside_fair.status_code, 400)

        deleted = self.client.delete(
            f"/api/fair-assignments/{assignment.get_json()['item']['id']}"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/fair-assignments").get_json(), [])

    def test_fair_assignment_conflicts_with_existing_reservations_and_missions(self):
        self.sign_in("admin")
        fair = self.client.post(
            "/api/fairs",
            json={
                "nom": "Foire affectation",
                "ville": "Tunis",
                "adresse": "Centre",
                "contact": "Contact",
                "d_limite": "2026-10-01",
            },
        ).get_json()["item"]

        reservation = self.client.post(
            "/api/reservations",
            json={
                "id_agent": 2,
                "id_foire": fair["id"],
                "taille_stand": "3x3",
                "logement": "Hôtel",
                "date_d": "2026-11-01",
                "date_f": "2026-11-03",
            },
        )
        self.assertEqual(reservation.status_code, 201, reservation.get_json())
        reserved_suggestion = self.client.post(
            "/api/fair-assignments/suggestions",
            json={
                "fair_id": fair["id"],
                "role": "vendeur",
                "start_date": "2026-11-02",
                "end_date": "2026-11-04",
            },
        )
        seller = next(
            suggestion for suggestion in reserved_suggestion.get_json()["suggestions"]
            if suggestion["user_id"] == 2
        )
        self.assertFalse(seller["available"])
        self.assertIn("Réservation existante", seller["conflict"])

        vehicle = self.client.post(
            "/api/vehicles",
            json={
                "model": "Véhicule mission",
                "immatricule": "MISSION-1",
                "annee": 2020,
                "puissance": 5,
            },
        ).get_json()["item"]
        stand = self.client.post(
            "/api/stand-types",
            json={"type": "Stand mission", "etat": "disponible"},
        ).get_json()["item"]
        work = self.client.post(
            "/api/works",
            json={
                "date_d": "2026-12-01",
                "date_f": "2026-12-03",
                "id_foire": fair["id"],
                "id_stand": stand["id"],
                "id_vendeur": 2,
                "id_deco": 3,
                "id_chauffeur": 4,
                "id_voiture": vehicle["id"],
                "flow": "en attente",
            },
        )
        self.assertEqual(work.status_code, 201, work.get_json())
        work_suggestion = self.client.post(
            "/api/fair-assignments/suggestions",
            json={
                "fair_id": fair["id"],
                "role": "vendeur",
                "start_date": "2026-12-03",
                "end_date": "2026-12-04",
            },
        )
        seller_with_work = next(
            suggestion for suggestion in work_suggestion.get_json()["suggestions"]
            if suggestion["user_id"] == 2
        )
        self.assertFalse(seller_with_work["available"])
        self.assertIn("Mission existante", seller_with_work["conflict"])

    def test_fair_inventory_moves_are_atomic_and_append_only(self):
        self.sign_in("admin")
        fair = Fair(
            nom="Foire stock",
            ville="Tunis",
            adresse="Centre",
            contact="Contact",
            d_limite="2026-10-01",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 5),
        )
        article = Article(
            ref="FAIR-STOCK-1",
            famille="Test",
            description="Article stock foire",
            categorie="Test",
            nom="Produit test",
            v_entrees=10,
            v_retour=0,
            v_stocks=10,
        )
        db.session.add_all([fair, article])
        db.session.commit()
        product_response = self.client.post(
            "/api/pos/products",
            json={
                "article_ref": article.ref,
                "product_code": article.ref,
                "gen_name": article.nom,
                "price": 20,
                "o_price": 8,
                "qty": 10,
            },
        )
        self.assertEqual(product_response.status_code, 201, product_response.get_json())
        product = db.session.get(PosProduct, product_response.get_json()["item"]["product_id"])

        def move(movement_type, quantity, reference=""):
            return self.client.post(
                f"/api/fairs/{fair.id}/inventory/movements",
                json={
                    "movement_type": movement_type,
                    "article_ref": article.ref,
                    "quantity": quantity,
                    "movement_date": "2026-11-01",
                    "reference": reference,
                },
            )

        transfer = move("transfer_in", 4, "BON-TRANSFERT")
        self.assertEqual(transfer.status_code, 201, transfer.get_json())
        db.session.refresh(article)
        db.session.refresh(product)
        self.assertEqual((article.v_stocks, product.qty, transfer.get_json()["balance"]), (6, 6, 4))
        self.assertEqual(transfer.get_json()["item"]["quantity_delta"], 4)

        self.assertEqual(move("sale", 2, "TICKET-1").status_code, 201)
        self.assertEqual(move("return", 1, "RETOUR-1").status_code, 201)
        self.assertEqual(move("damage", 1, "CASSE-1").status_code, 201)
        transfer_back = move("transfer_out", 2, "RETOUR-STOCK")
        self.assertEqual(transfer_back.status_code, 201, transfer_back.get_json())
        db.session.refresh(article)
        db.session.refresh(product)
        self.assertEqual((article.v_stocks, product.qty, transfer_back.get_json()["balance"]), (8, 8, 0))

        product.qty = 7
        db.session.commit()
        mismatched_transfer = move("transfer_in", 1)
        self.assertEqual(mismatched_transfer.status_code, 409)
        db.session.refresh(article)
        db.session.refresh(product)
        self.assertEqual((article.v_stocks, product.qty), (8, 7))
        product.qty = 8
        db.session.commit()

        insufficient_fair = move("sale", 1)
        self.assertEqual(insufficient_fair.status_code, 409)
        insufficient_central = move("transfer_in", 9)
        self.assertEqual(insufficient_central.status_code, 409)

        inventory_response = self.client.get(f"/api/fairs/{fair.id}/inventory")
        self.assertEqual(inventory_response.status_code, 200)
        self.assertEqual(inventory_response.get_json()["inventory"], [])
        self.assertEqual(len(inventory_response.get_json()["movements"]), 5)
        self.assertEqual(
            StockMovement.query.filter_by(article_ref=article.ref).count(),
            2,
            "Transfers must also be auditable in general stock.",
        )
        pos_adjustments = PosStockMovement.query.filter_by(
            product_id=product.product_id,
            reference_type="fair_transfer",
        ).all()
        self.assertEqual(
            [movement.quantity_delta for movement in pos_adjustments],
            [-4, 2],
        )
        self.assertEqual(
            FairInventoryBalance.query.filter_by(
                fair_id=fair.id, article_ref=article.ref
            ).first().quantity,
            0,
        )

        movement = FairInventoryMovement.query.order_by(FairInventoryMovement.id).first()
        movement.notes = "forbidden change"
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.delete(movement)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        self.assertEqual(FairInventoryMovement.query.count(), 5)

    def test_fair_inventory_access_and_input_validation(self):
        self.sign_in("seller")
        fair = Fair(
            nom="Foire autorisation",
            ville="Sfax",
            adresse="Centre",
            contact="Contact",
            d_limite="2026-12-01",
        )
        db.session.add(fair)
        db.session.commit()
        self.assertEqual(self.client.get(f"/api/fairs/{fair.id}/inventory").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/fairs/{fair.id}/inventory/movements",
                json={"movement_type": "sale"},
            ).status_code,
            403,
        )

        self.client.post("/api/logout")
        self.sign_in("admin")
        article = Article(
            ref="FAIR-VALIDATION",
            description="Test",
            nom="Produit",
            v_entrees=2,
            v_retour=0,
            v_stocks=2,
        )
        db.session.add(article)
        db.session.commit()
        invalid = self.client.post(
            f"/api/fairs/{fair.id}/inventory/movements",
            json={
                "movement_type": "sale",
                "article_ref": article.ref,
                "quantity": True,
                "movement_date": "2026-11-01",
            },
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(FairInventoryMovement.query.count(), 0)

    def test_pos_fair_sales_use_assigned_seller_and_fair_inventory(self):
        self.sign_in("admin")
        today = date.today()
        fair = Fair(
            nom="Foire POS",
            ville="Tunis",
            adresse="Centre",
            contact="Contact",
            d_limite=today.isoformat(),
            start_date=today,
            end_date=today,
        )
        article = Article(
            ref="FAIR-POS-1",
            famille="Test",
            description="Article POS foire",
            categorie="Test",
            nom="Produit POS foire",
            v_entrees=10,
            v_retour=0,
            v_stocks=10,
        )
        seller = User.query.filter_by(login="seller").one()
        second_seller = User(
            nom="Test",
            prenom="second",
            login="second-seller",
            pw=generate_password_hash("test-password-123"),
            type="vendeur",
            lpp=8,
        )
        db.session.add_all([fair, article, second_seller])
        db.session.flush()
        db.session.add(
            FairAssignment(
                fair_id=fair.id,
                user_id=seller.id,
                role="vendeur",
                start_date=today,
                end_date=today,
                status="confirmed",
            )
        )
        db.session.add(
            FairAssignment(
                fair_id=fair.id,
                user=second_seller,
                role="vendeur",
                start_date=today,
                end_date=today,
                status="confirmed",
            )
        )
        db.session.commit()

        linked_response = self.client.post(
            "/api/pos/products",
            json={
                "article_ref": article.ref,
                "product_code": article.ref,
                "gen_name": article.nom,
                "price": 12,
                "o_price": 5,
                "qty": 10,
            },
        )
        self.assertEqual(linked_response.status_code, 201, linked_response.get_json())
        linked_product = db.session.get(
            PosProduct, linked_response.get_json()["item"]["product_id"]
        )
        unlinked_response = self.client.post(
            "/api/pos/products",
            json={
                "product_code": "FAIR-UNLINKED",
                "gen_name": "Produit non lié",
                "price": 8,
                "o_price": 3,
                "qty": 2,
            },
        )
        self.assertEqual(unlinked_response.status_code, 201, unlinked_response.get_json())
        unlinked_product_id = unlinked_response.get_json()["item"]["product_id"]

        transfer = self.client.post(
            f"/api/fairs/{fair.id}/inventory/movements",
            json={
                "movement_type": "transfer_in",
                "article_ref": article.ref,
                "quantity": 5,
                "movement_date": today.isoformat(),
            },
        )
        self.assertEqual(transfer.status_code, 201, transfer.get_json())

        self.client.post("/api/logout")
        self.sign_in("seller")
        contexts = self.client.get("/api/pos/fair-contexts")
        self.assertEqual(contexts.status_code, 200, contexts.get_json())
        context = next(
            row for row in contexts.get_json() if row["fair_id"] == fair.id
        )
        self.assertEqual(context["sellers"], [{
            "user_id": seller.id,
            "name": f"{seller.prenom} {seller.nom}".strip(),
        }])
        self.assertEqual(context["inventory"], [{
            "article_ref": article.ref,
            "quantity": 5,
        }])

        def checkout(product_id, quantity, fair_id=fair.id, seller_id=seller.id):
            return self.client.post(
                "/api/pos/checkout",
                json={
                    "items": [{"product_id": product_id, "qty": quantity}],
                    "payment_type": "cash",
                    "cash_received": 100,
                    "fair_id": fair_id,
                    "seller_id": seller_id,
                },
            )

        wrong_role = checkout(linked_product.product_id, 1, seller_id=4)
        self.assertEqual(wrong_role.status_code, 403, wrong_role.get_json())
        other_seller_sale = checkout(
            linked_product.product_id, 1, seller_id=second_seller.id
        )
        self.assertEqual(other_seller_sale.status_code, 403, other_seller_sale.get_json())
        unlinked = checkout(unlinked_product_id, 1)
        self.assertEqual(unlinked.status_code, 409, unlinked.get_json())
        insufficient = checkout(linked_product.product_id, 6)
        self.assertEqual(insufficient.status_code, 409, insufficient.get_json())
        self.assertEqual(PosSale.query.count(), 0)

        general_sale_response = self.client.post(
            "/api/pos/checkout",
            json={
                "items": [{"product_id": linked_product.product_id, "qty": 1}],
                "payment_type": "cash",
                "cash_received": 12,
            },
        )
        self.assertEqual(
            general_sale_response.status_code, 400, general_sale_response.get_json()
        )

        fair_sale_response = checkout(linked_product.product_id, 2)
        self.assertEqual(fair_sale_response.status_code, 201, fair_sale_response.get_json())
        fair_sale = fair_sale_response.get_json()["sale"]
        self.assertEqual(fair_sale["fair_id"], fair.id)
        self.assertEqual(fair_sale["fair_name"], fair.nom)
        self.assertEqual(fair_sale["seller_id"], seller.id)
        self.assertEqual(fair_sale["seller_name"], f"{seller.prenom} {seller.nom}".strip())
        self.assertEqual(fair_sale["cashier_user_id"], seller.id)
        self.assertEqual(
            fair_sale["cashier_user_name"], f"{seller.prenom} {seller.nom}".strip()
        )
        self.assertEqual((article.v_stocks, linked_product.qty), (5, 5))
        self.assertEqual(linked_product.qty_sold, 2)
        self.assertEqual(
            FairInventoryBalance.query.filter_by(
                fair_id=fair.id, article_ref=article.ref
            ).one().quantity,
            3,
        )
        self.assertEqual(
            [
                (movement.movement_type, movement.quantity_delta)
                for movement in FairInventoryMovement.query.filter_by(
                    fair_id=fair.id
                ).order_by(FairInventoryMovement.id)
            ],
            [("transfer_in", 5), ("sale", -2)],
        )
        filtered_sales = self.client.get(
            f"/api/pos/sales?fair_id={fair.id}&seller_id={seller.id}"
        )
        self.assertEqual(filtered_sales.status_code, 200, filtered_sales.get_json())
        self.assertEqual(
            [sale["transaction_id"] for sale in filtered_sales.get_json()],
            [fair_sale["transaction_id"]],
        )
        report = self.client.get(
            f"/api/pos/reports/sales?fair_id={fair.id}&seller_id={seller.id}"
        )
        self.assertEqual(report.status_code, 200, report.get_json())
        self.assertEqual(report.get_json()["count"], 1)
        self.assertEqual(report.get_json()["sales"][0]["fair_name"], fair.nom)
        self.assertEqual(
            self.client.get("/api/pos/sales?fair_id=invalid").status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                f"/api/pos/sales/{fair_sale['transaction_id']}"
            ).status_code,
            200,
        )

        self.client.post("/api/logout")
        self.sign_in("second-seller")
        second_context = self.client.get("/api/pos/fair-contexts").get_json()
        self.assertEqual(len(second_context), 1)
        self.assertEqual(
            [row["user_id"] for row in second_context[0]["sellers"]],
            [second_seller.id],
        )
        second_sale_response = checkout(
            linked_product.product_id, 1, seller_id=second_seller.id
        )
        self.assertEqual(second_sale_response.status_code, 201, second_sale_response.get_json())
        second_sale = second_sale_response.get_json()["sale"]
        self.assertEqual(
            [sale["transaction_id"] for sale in self.client.get("/api/pos/sales").get_json()],
            [second_sale["transaction_id"]],
        )
        self.assertEqual(
            self.client.get(
                f"/api/pos/sales/{fair_sale['transaction_id']}"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/pos/sales/{fair_sale['transaction_id']}/collections",
                json={"amount": 1},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get("/api/pos/collections").get_json()["count"], 0)
        self.assertEqual(
            self.client.get("/api/pos/reports/sales").get_json()["count"],
            1,
        )

        self.assertEqual(self.client.get("/api/pos/reports/fairs").status_code, 403)
        self.client.post("/api/logout")
        self.sign_in("admin")
        fair_report = self.client.get(
            f"/api/pos/reports/fairs?from={today.isoformat()}&to={today.isoformat()}"
        )
        self.assertEqual(fair_report.status_code, 200, fair_report.get_json())
        report_data = fair_report.get_json()
        self.assertEqual(report_data["count"], 2)
        self.assertEqual(report_data["total_amount"], 36)
        self.assertEqual(report_data["total_profit"], 21)
        self.assertEqual(report_data["general_sales"]["count"], 0)
        self.assertEqual(report_data["general_sales"]["total_amount"], 0)
        reported_fair = next(
            row for row in report_data["fairs"] if row["fair_id"] == fair.id
        )
        self.assertEqual(reported_fair["count"], 2)
        self.assertEqual(
            {row["seller_id"] for row in reported_fair["sellers"]},
            {seller.id, second_seller.id},
        )
        invalid_dates = self.client.get("/api/pos/reports/fairs?from=invalid")
        self.assertEqual(invalid_dates.status_code, 400)
        reversed_dates = self.client.get(
            "/api/pos/reports/fairs?from=2026-10-21&to=2026-10-20"
        )
        self.assertEqual(reversed_dates.status_code, 400)

    def test_assigned_and_unassigned_modules_are_enforced(self):
        self.sign_in("seller")
        self.assertEqual(self.client.get("/api/clients").status_code, 200)
        self.assertEqual(self.client.get("/api/articles").status_code, 200)
        self.assertEqual(self.client.get("/api/pos/sales").status_code, 200)
        self.assertEqual(self.client.get("/api/pos/purchases").status_code, 403)
        self.assertEqual(self.client.get("/api/vehicles").status_code, 403)

    def test_module_permission_allows_its_writes(self):
        self.sign_in("seller")
        response = self.client.post(
            "/api/clients",
            json={
                "nom": "Client",
                "prenom": "Test",
                "tel": "123",
                "email": "client@example.com",
                "specialite": "Bois",
                "ville": "Sousse",
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["client"]["specialite"], "Bois")
        self.assertEqual(response.get_json()["client"]["ville"], "Sousse")

    def test_role_can_read_employee_and_permission_modules(self):
        self.sign_in("employee")
        self.assertEqual(self.client.get("/api/employees").status_code, 200)
        self.assertEqual(self.client.get("/api/permissions").status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/permissions",
                json={"type_user": "vendeur", "vente": False},
            ).status_code,
            403,
        )

    def test_administrator_has_all_module_access(self):
        user = self.sign_in("admin")
        self.assertTrue(all(user["permissions"].values()))
        self.assertEqual(self.client.get("/api/clients").status_code, 200)
        self.assertEqual(self.client.get("/api/vehicles").status_code, 200)
        self.assertEqual(self.client.get("/api/employees").status_code, 200)
        created = self.client.post(
            "/api/users",
            json={
                "nom": "Ville",
                "prenom": "Test",
                "login": "city-test",
                "password": "new-password-123",
                "type": "vendeur",
                "ville": "Tunis",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["user"]["ville"], "Tunis")
        user_id = created.get_json()["user"]["id"]
        changed = self.client.put(
            f"/api/users/{user_id}",
            json={
                "nom": "Ville",
                "prenom": "Test",
                "login": "city-test",
                "type": "vendeur",
                "ville": "Sfax",
            },
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.get_json()["user"]["ville"], "Sfax")

    def test_stock_permissions_are_checked_by_movement_type(self):
        self.sign_in("seller")
        denied = self.client.post(
            "/api/stock/movements",
            json={"type": "reception"},
        )
        self.assertEqual(denied.status_code, 403)

        allowed = self.client.post(
            "/api/stock/movements",
            json={"type": "vente"},
        )
        self.assertEqual(allowed.status_code, 400)
        self.assertIn("error", allowed.get_json())

    def test_pos_database_tracks_contacts_purchases_sales_and_inventory(self):
        self.sign_in("admin")
        today = date.today()
        article = Article(
            ref="POS-ARTICLE-001",
            famille="Test",
            description="Article lié au POS",
            categorie="POS",
            nom="Produit de caisse",
            v_entrees=5,
            v_retour=0,
            v_stocks=5,
        )
        fair = Fair(
            nom="Foire caisse",
            ville="Tunis",
            adresse="Centre",
            contact="Contact",
            d_limite=today.isoformat(),
            start_date=today,
            end_date=today,
        )
        seller = User.query.filter_by(login="seller").one()
        db.session.add_all([article, fair])
        db.session.flush()
        db.session.add(
            FairAssignment(
                fair_id=fair.id,
                user_id=seller.id,
                role="vendeur",
                start_date=today,
                end_date=today,
                status="confirmed",
            )
        )
        db.session.commit()

        product_response = self.client.post(
            "/api/pos/products",
            json={
                "article_ref": article.ref,
                "product_code": "POS-001",
                "gen_name": "Produit de caisse",
                "product_name": "Format test",
                "supplier": "",
                "date_arrival": "2026-10-19",
                "expiry_date": "",
                "price": 10,
                "o_price": 4,
                "qty": 5,
            },
        )
        self.assertEqual(product_response.status_code, 201, product_response.get_json())
        product_id = product_response.get_json()["item"]["product_id"]

        purchase_response = self.client.post(
            "/api/pos/purchases",
            json={
                "invoice_number": "FACT-POS-001",
                "date": "2026-10-19",
                "supplier": "Fournisseur POS",
                "remarks": "",
                "items": [{"product_id": product_id, "qty": 3, "unit_cost": 5}],
            },
        )
        self.assertEqual(purchase_response.status_code, 201, purchase_response.get_json())
        self.assertEqual(purchase_response.get_json()["purchase"]["supplier_id"], 1)

        adjusted_product = self.client.put(
            f"/api/pos/products/{product_id}",
            json={
                "article_ref": article.ref,
                "product_code": "POS-001",
                "gen_name": "Produit de caisse",
                "product_name": "Format test",
                "supplier": "",
                "date_arrival": "2026-10-19",
                "expiry_date": "",
                "price": 10,
                "o_price": 4,
                "qty": 9,
            },
        )
        self.assertEqual(adjusted_product.status_code, 200, adjusted_product.get_json())
        db.session.add(
            FairInventoryBalance(
                fair_id=fair.id,
                article_ref=article.ref,
                quantity=9,
            )
        )
        db.session.commit()

        sale_response = self.client.post(
            "/api/pos/checkout",
            json={
                "items": [{"product_id": product_id, "qty": 2}],
                "payment_type": "cash",
                "customer_name": "Client POS",
                "cash_received": 20,
                "fair_id": fair.id,
                "seller_id": seller.id,
            },
        )
        self.assertEqual(sale_response.status_code, 201, sale_response.get_json())
        cash_sale = sale_response.get_json()["sale"]
        self.assertIsNotNone(cash_sale["customer_id"])

        credit_response = self.client.post(
            "/api/pos/checkout",
            json={
                "items": [{"product_id": product_id, "qty": 1}],
                "payment_type": "credit",
                "customer_name": " client pos ",
                "due_date": "2026-10-30",
                "fair_id": fair.id,
                "seller_id": seller.id,
            },
        )
        self.assertEqual(credit_response.status_code, 201, credit_response.get_json())
        credit_sale = credit_response.get_json()["sale"]
        self.assertEqual(credit_sale["customer_id"], cash_sale["customer_id"])

        collection_response = self.client.post(
            f"/api/pos/sales/{credit_sale['transaction_id']}/collections",
            json={"amount": 3, "date": "2026-10-19", "remarks": "Acompte"},
        )
        self.assertEqual(collection_response.status_code, 201, collection_response.get_json())

        product = db.session.get(PosProduct, product_id)
        self.assertEqual(product.qty, 9)
        self.assertEqual(product.qty_sold, 3)
        self.assertEqual(
            FairInventoryBalance.query.filter_by(
                fair_id=fair.id, article_ref=article.ref
            ).one().quantity,
            6,
        )
        self.assertEqual(PosCustomer.query.count(), 1)
        self.assertEqual(PosSupplier.query.count(), 1)
        self.assertEqual(PosPurchase.query.count(), 1)
        self.assertEqual(PosSale.query.count(), 2)
        self.assertEqual(PosCollection.query.count(), 1)
        movements = PosStockMovement.query.filter_by(product_id=product_id).all()
        self.assertCountEqual(
            [(movement.movement_type, movement.quantity_delta) for movement in movements],
            [
                ("opening", 5),
                ("purchase", 3),
                ("adjustment", 1),
            ],
        )

        history = self.client.get("/api/pos/stock-movements")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.get_json()), 3)
        self.assertIn("unit_cost", history.get_json()[0])
        self.sign_in("seller")
        restricted_history = self.client.get("/api/pos/stock-movements")
        self.assertEqual(restricted_history.status_code, 200)
        self.assertNotIn("unit_cost", restricted_history.get_json()[0])
        self.assertEqual(
            self.client.get("/api/pos/sales").get_json()[0]["fair_id"],
            fair.id,
        )

    def test_importing_articles_creates_unpriced_pos_catalog_without_changing_stock(self):
        self.sign_in("admin")
        created_article = self.client.post(
            "/api/articles",
            json={
                "ref": "IMPORT-POS-01",
                "famille": "Test",
                "description": "Article à importer dans la caisse",
                "categorie": "POS",
                "nom": "Produit à configurer",
                "v_entrees": 4,
                "v_retour": 1,
            },
        )
        self.assertEqual(created_article.status_code, 201, created_article.get_json())
        article = db.session.get(Article, "IMPORT-POS-01")
        stock_before = article.v_stocks

        imported = self.client.post("/api/pos/products/import-articles", json={})
        self.assertEqual(imported.status_code, 200, imported.get_json())
        self.assertEqual(imported.get_json()["created_count"], 1)
        product = PosProduct.query.filter_by(article_ref=article.ref).one()
        self.assertEqual(product.qty, stock_before)
        self.assertEqual((product.price, product.o_price), (0, 0))
        self.assertFalse(product.pricing_configured)
        self.assertEqual(article.v_stocks, stock_before)
        self.assertEqual(
            [
                (movement.movement_type, movement.quantity_delta)
                for movement in PosStockMovement.query.filter_by(
                    product_id=product.product_id
                )
            ],
            [("opening", stock_before)],
        )

        repeated_import = self.client.post(
            "/api/pos/products/import-articles", json={}
        )
        self.assertEqual(repeated_import.status_code, 200)
        self.assertEqual(repeated_import.get_json()["created_count"], 0)
        self.assertEqual(PosProduct.query.filter_by(article_ref=article.ref).count(), 1)

        today = date.today()
        fair = Fair(
            nom="Foire import POS",
            ville="Tunis",
            adresse="Centre",
            contact="Contact",
            d_limite=today.isoformat(),
            start_date=today,
            end_date=today,
        )
        seller = User.query.filter_by(login="seller").one()
        db.session.add(fair)
        db.session.flush()
        db.session.add_all([
            FairAssignment(
                fair_id=fair.id,
                user_id=seller.id,
                role="vendeur",
                start_date=today,
                end_date=today,
                status="confirmed",
            ),
            FairInventoryBalance(
                fair_id=fair.id,
                article_ref=article.ref,
                quantity=1,
            ),
        ])
        db.session.commit()

        missing_fair_sale = self.client.post(
            "/api/pos/checkout",
            json={
                "items": [{"product_id": product.product_id, "qty": 1}],
                "payment_type": "cash",
                "cash_received": 10,
            },
        )
        self.assertEqual(missing_fair_sale.status_code, 400)
        self.assertIn("associée à une foire", missing_fair_sale.get_json()["error"])
        blocked_sale = self.client.post(
            "/api/pos/checkout",
            json={
                "items": [{"product_id": product.product_id, "qty": 1}],
                "payment_type": "cash",
                "cash_received": 10,
                "fair_id": fair.id,
                "seller_id": seller.id,
            },
        )
        self.assertEqual(blocked_sale.status_code, 409)
        self.assertIn("doivent être configurés", blocked_sale.get_json()["error"])
        self.assertEqual(PosSale.query.count(), 0)

        configured = self.client.put(
            f"/api/pos/products/{product.product_id}",
            json={
                "article_ref": article.ref,
                "product_code": article.ref,
                "gen_name": article.nom,
                "product_name": article.description,
                "supplier": "",
                "date_arrival": "",
                "expiry_date": "",
                "price": 8,
                "o_price": 3,
                "pricing_configured": True,
                "qty": stock_before,
            },
        )
        self.assertEqual(configured.status_code, 200, configured.get_json())
        self.assertTrue(configured.get_json()["item"]["pricing_configured"])
        sale = self.client.post(
            "/api/pos/checkout",
            json={
                "items": [{"product_id": product.product_id, "qty": 1}],
                "payment_type": "cash",
                "cash_received": 8,
                "fair_id": fair.id,
                "seller_id": seller.id,
            },
        )
        self.assertEqual(sale.status_code, 201, sale.get_json())
        db.session.refresh(article)
        db.session.refresh(product)
        self.assertEqual(article.v_stocks, stock_before)
        self.assertEqual(product.qty, stock_before)

        self.client.post("/api/logout")
        self.sign_in("seller")
        denied = self.client.post("/api/pos/products/import-articles", json={})
        self.assertEqual(denied.status_code, 403)

    def test_linked_pos_products_share_stock_with_general_inventory(self):
        self.sign_in("admin")
        article_response = self.client.post(
            "/api/articles",
            json={
                "ref": "SHARED-01",
                "famille": "Test",
                "description": "Article lié",
                "categorie": "POS",
                "nom": "Article partagé",
                "v_entrees": 10,
                "v_retour": 0,
            },
        )
        self.assertEqual(article_response.status_code, 201, article_response.get_json())

        mismatch = self.client.post(
            "/api/pos/products",
            json={
                "article_ref": "SHARED-01",
                "product_code": "SHARED-01",
                "gen_name": "Article partagé",
                "price": 12,
                "o_price": 5,
                "qty": 9,
            },
        )
        self.assertEqual(mismatch.status_code, 409)

        product_response = self.client.post(
            "/api/pos/products",
            json={
                "article_ref": "SHARED-01",
                "product_code": "any-value-is-normalized",
                "gen_name": "Nom normalisé depuis l’article",
                "price": 12,
                "o_price": 5,
                "qty": 10,
            },
        )
        self.assertEqual(product_response.status_code, 201, product_response.get_json())
        product = product_response.get_json()["item"]
        self.assertEqual(product["article_ref"], "SHARED-01")
        self.assertEqual(product["product_code"], "SHARED-01")
        self.assertEqual(product["gen_name"], "Article partagé")

        today = date.today()
        fair = Fair(
            nom="Foire stock partagé",
            ville="Tunis",
            adresse="Centre",
            contact="Contact",
            d_limite=today.isoformat(),
            start_date=today,
            end_date=today,
        )
        seller = User.query.filter_by(login="seller").one()
        db.session.add(fair)
        db.session.flush()
        db.session.add_all([
            FairAssignment(
                fair_id=fair.id,
                user_id=seller.id,
                role="vendeur",
                start_date=today,
                end_date=today,
                status="confirmed",
            ),
            FairInventoryBalance(
                fair_id=fair.id,
                article_ref="SHARED-01",
                quantity=13,
            ),
        ])
        db.session.commit()

        supplier = Supplier(
            nom="Test",
            prenom="Fournisseur",
            tel="123",
            email="supplier@example.com",
        )
        db.session.add(supplier)
        db.session.commit()

        purchase = self.client.post(
            "/api/pos/purchases",
            json={
                "invoice_number": "SHARED-PURCHASE",
                "date": "2026-10-19",
                "supplier": "Fournisseur POS",
                "items": [{"product_id": product["product_id"], "qty": 3, "unit_cost": 5}],
            },
        )
        self.assertEqual(purchase.status_code, 201, purchase.get_json())
        article = db.session.get(Article, "SHARED-01")
        pos_product = db.session.get(PosProduct, product["product_id"])
        self.assertEqual((article.v_stocks, pos_product.qty), (13, 13))

        sale = self.client.post(
            "/api/pos/checkout",
            json={
                "items": [{"product_id": product["product_id"], "qty": 2}],
                "payment_type": "cash",
                "cash_received": 24,
                "fair_id": fair.id,
                "seller_id": seller.id,
            },
        )
        self.assertEqual(sale.status_code, 201, sale.get_json())
        self.assertEqual((article.v_stocks, pos_product.qty), (13, 13))
        self.assertEqual(
            FairInventoryBalance.query.filter_by(
                fair_id=fair.id, article_ref=article.ref
            ).one().quantity,
            11,
        )

        reception = self.client.post(
            "/api/stock/movements",
            json={
                "type": "reception",
                "article_ref": "SHARED-01",
                "quantite": 4,
                "date_mouvement": "2026-10-19",
                "id_fournisseur": supplier.id,
            },
        )
        self.assertEqual(reception.status_code, 201, reception.get_json())
        self.assertEqual((article.v_stocks, pos_product.qty), (17, 17))
        movement_id = reception.get_json()["mouvement"]["id"]
        adjusted_reception = self.client.put(
            f"/api/stock/movements/{movement_id}",
            json={
                "type": "reception",
                "article_ref": "SHARED-01",
                "quantite": 2,
                "date_mouvement": "2026-10-19",
                "id_fournisseur": supplier.id,
            },
        )
        self.assertEqual(adjusted_reception.status_code, 200, adjusted_reception.get_json())
        self.assertEqual((article.v_stocks, pos_product.qty), (15, 15))
        removed_reception = self.client.delete(f"/api/stock/movements/{movement_id}")
        self.assertEqual(removed_reception.status_code, 200, removed_reception.get_json())
        self.assertEqual((article.v_stocks, pos_product.qty), (13, 13))

        changed_article = self.client.put(
            "/api/articles/SHARED-01",
            json={
                "ref": "SHARED-01",
                "famille": "Test",
                "description": "Article lié",
                "categorie": "POS",
                "nom": "Article partagé modifié",
                "v_entrees": 12,
                "v_retour": 2,
            },
        )
        self.assertEqual(changed_article.status_code, 200, changed_article.get_json())
        self.assertEqual((article.v_stocks, pos_product.qty), (10, 10))
        self.assertEqual(
            PosStockMovement.query.filter_by(
                product_id=product["product_id"],
                movement_type="adjustment",
            ).count(),
            1,
        )
        self.assertEqual(
            self.client.delete("/api/articles/SHARED-01").status_code,
            409,
        )
        changed_reference = self.client.put(
            "/api/articles/SHARED-01",
            json={
                "ref": "SHARED-02",
                "famille": "Test",
                "description": "Article lié",
                "categorie": "POS",
                "nom": "Article partagé modifié",
                "v_entrees": 12,
                "v_retour": 2,
            },
        )
        self.assertEqual(changed_reference.status_code, 409)
        unlinked_product = self.client.put(
            f"/api/pos/products/{product['product_id']}",
            json={
                "article_ref": "",
                "product_code": "SHARED-01",
                "gen_name": "Article partagé",
                "price": 12,
                "o_price": 5,
                "qty": 11,
            },
        )
        self.assertEqual(unlinked_product.status_code, 409)

    def test_legacy_resource_modules_support_crud(self):
        self.sign_in("admin")
        resource_urls = (
            "/vehicles",
            "/fairs",
            "/stand-types",
            "/stand-inventory",
            "/reservations",
            "/works",
            "/permissions",
        )
        for url in resource_urls:
            with self.subTest(url=url):
                response = self.client.get(f"/api{url}")
                self.assertEqual(response.status_code, 200, response.get_json())

        vehicle = self.client.post(
            "/api/vehicles",
            json={
                "model": "Camion",
                "immatricule": "123ABC",
                "annee": 2022,
                "puissance": 8,
                "location": True,
                "date_d_loc": "2026-10-20",
                "date_f_loc": "2026-10-25",
            },
        )
        self.assertEqual(vehicle.status_code, 201, vehicle.get_json())
        self.assertTrue(vehicle.get_json()["item"]["location"])
        self.assertEqual(vehicle.get_json()["item"]["date_d_loc"], "2026-10-20")
        vehicle_id = vehicle.get_json()["item"]["id"]
        changed_vehicle = self.client.put(
            f"/api/vehicles/{vehicle_id}",
            json={
                "model": "Camion modifié",
                "immatricule": "123ABC",
                "annee": 2022,
                "puissance": 8,
            },
        )
        self.assertEqual(changed_vehicle.status_code, 200)
        self.assertEqual(changed_vehicle.get_json()["item"]["model"], "Camion modifié")
        disposable_vehicle = self.client.post(
            "/api/vehicles",
            json={
                "model": "Voiture test",
                "immatricule": "DEL-123",
                "annee": 2020,
                "puissance": 5,
                "location": False,
                "date_d_loc": "",
                "date_f_loc": "",
            },
        )
        self.assertEqual(disposable_vehicle.status_code, 201)
        self.assertEqual(
            self.client.delete(
                f"/api/vehicles/{disposable_vehicle.get_json()['item']['id']}"
            ).status_code,
            200,
        )

        fair = self.client.post(
            "/api/fairs",
            json={
                "nom": "Foire test",
                "ville": "Paris",
                "adresse": "1 rue test",
                "contact": "01 00 00 00 00",
                "d_limite": "2026-12-01",
                "type": "boutique",
            },
        )
        self.assertEqual(fair.status_code, 201, fair.get_json())
        self.assertEqual(fair.get_json()["item"]["type"], "boutique")
        fair_id = fair.get_json()["item"]["id"]
        stand_type = self.client.post(
            "/api/stand-types",
            json={"type": "3x3", "etat": "disponible"},
        )
        self.assertEqual(stand_type.status_code, 201, stand_type.get_json())
        stand_id = stand_type.get_json()["item"]["id"]

        article = self.client.post(
            "/api/articles",
            json={
                "ref": "REF-TEST",
                "nom": "Article test",
                "description": "Article pour test d’intégration",
            },
        )
        self.assertEqual(article.status_code, 201, article.get_json())
        inventory = self.client.post(
            "/api/stand-inventory",
            json={
                "id_stand": stand_id,
                "ref_article": "REF-TEST",
                "quantite": 2,
                "date_ch": "2026-10-19",
            },
        )
        self.assertEqual(inventory.status_code, 201, inventory.get_json())
        inventory_options = self.client.get(
            "/api/resource-lookups/stand-inventory"
        )
        self.assertEqual(inventory_options.status_code, 200)
        self.assertEqual(
            inventory_options.get_json()["ref_article"][0]["label"],
            "REF-TEST — Article test",
        )

        reservation = self.client.post(
            "/api/reservations",
            json={
                "id_agent": 1,
                "id_foire": fair_id,
                "taille_stand": "3x3",
                "logement": "Hôtel",
                "date_d": "2026-11-01",
                "date_f": "2026-11-05",
                "etat": 1,
                "date_c": "2026-10-19",
            },
        )
        self.assertEqual(reservation.status_code, 201, reservation.get_json())
        self.assertEqual(reservation.get_json()["item"]["etat"], 1)
        self.assertEqual(reservation.get_json()["item"]["date_c"], "2026-10-19")
        reservation_options = self.client.get(
            "/api/resource-lookups/reservations"
        )
        self.assertEqual(reservation_options.status_code, 200)
        self.assertIn(
            "seller Test",
            [option["label"] for option in reservation_options.get_json()["id_agent"]],
        )

        work = self.client.post(
            "/api/works",
            json={
                "date_d": "2026-11-01",
                "date_f": "2026-11-05",
                "id_foire": fair_id,
                "id_stand": stand_id,
                "id_vendeur": 2,
                "id_deco": 3,
                "id_chauffeur": 4,
                "id_voiture": vehicle_id,
                "flow": "en attente",
            },
        )
        self.assertEqual(work.status_code, 201, work.get_json())
        self.assertEqual(
            set(work.get_json()["item"]["confirmations"]),
            {"id", "c_vendeur", "c_chauffeur", "c_deco"},
        )
        self.assertEqual(work.get_json()["item"]["foire_nom"], "Foire test")
        self.assertEqual(work.get_json()["item"]["vendeur_nom"], "seller Test")
        work_options = self.client.get("/api/resource-lookups/works")
        self.assertEqual(work_options.status_code, 200)
        self.assertEqual(
            [option["label"] for option in work_options.get_json()["id_vendeur"]],
            ["seller Test"],
        )

        permission = self.client.post(
            "/api/permissions",
            json={
                "type_user": "laga",
                "foire": True,
                "stand": False,
                "liste_stand": False,
                "article": False,
                "work": False,
                "fournisseur": False,
                "client": False,
                "reservation": False,
                "empl": False,
                "voiture": False,
                "mouvement": False,
                "livraison": False,
                "reception": False,
                "vente": False,
                "achat": False,
            },
        )
        self.assertEqual(permission.status_code, 201, permission.get_json())
        updated_permission = self.client.put(
            "/api/permissions/laga",
            json={
                "type_user": "laga",
                "foire": False,
                "stand": True,
                "liste_stand": False,
                "article": False,
                "work": False,
                "fournisseur": False,
                "client": False,
                "reservation": False,
                "empl": False,
                "voiture": False,
                "mouvement": False,
                "livraison": False,
                "reception": False,
                "vente": False,
                "achat": False,
            },
        )
        self.assertEqual(updated_permission.status_code, 200)
        self.assertTrue(updated_permission.get_json()["item"]["stand"])

        supplier = self.client.post(
            "/api/suppliers",
            json={
                "nom": "Fournisseur",
                "prenom": "Test",
                "tel": "12345",
                "email": "supplier@example.test",
                "specialite": "Textile",
                "ville": "Sfax",
            },
        )
        self.assertEqual(supplier.status_code, 201, supplier.get_json())
        self.assertEqual(supplier.get_json()["fournisseur"]["specialite"], "Textile")
        self.assertEqual(supplier.get_json()["fournisseur"]["ville"], "Sfax")

    def test_resource_access_is_enforced_and_permission_writes_are_admin_only(self):
        self.sign_in("employee")
        self.assertEqual(self.client.get("/api/permissions").status_code, 200)
        self.assertEqual(self.client.get("/api/vehicles").status_code, 403)
        self.assertEqual(
            self.client.get("/api/resource-lookups/works").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/permissions",
                json={"type_user": "laga"},
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
