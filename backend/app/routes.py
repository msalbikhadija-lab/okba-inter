import html
import logging
import time
from collections import defaultdict
from functools import wraps
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import secrets

from flask import Blueprint, current_app, g, jsonify, make_response, request, session
from sqlalchemy import func, or_, text, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .models import (
    Article,
    Client,
    Confirmation,
    FairAssignment,
    Fair,
    FairInventoryBalance,
    FairInventoryMovement,
    PosCollection,
    PosCustomer,
    Permission,
    PosProduct,
    PosPurchase,
    PosPurchaseItem,
    PosRegister,
    PosSale,
    PosSaleItem,
    PosStockMovement,
    PosSupplier,
    Reservation,
    StandInventory,
    StandType,
    StockMovement,
    Supplier,
    SystemSetting,
    User,
    Vehicle,
    Work,
    money_value,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")

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

MONEY_QUANTUM = Decimal("0.01")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return jsonify({"error": "Authentification requise"}), 401

        user = db.session.get(User, user_id)
        if user is None:
            session.clear()
            return jsonify({"error": "Session invalide"}), 401

        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.current_user.type != "admin":
            return jsonify({"error": "Accès réservé aux administrateurs"}), 403
        return view(*args, **kwargs)

    return wrapped


def has_permission(user, *fields):
    if user.type == "admin":
        return True
    permissions = Permission.query.filter_by(type_user=user.type).first()
    return bool(
        permissions
        and any(getattr(permissions, field, False) for field in fields)
    )


def user_payload(user):
    if user.type == "admin":
        permissions = {field: True for field in PERMISSION_FIELDS}
    else:
        role_permissions = Permission.query.filter_by(type_user=user.type).first()
        permissions = (
            {
                field: bool(getattr(role_permissions, field))
                for field in PERMISSION_FIELDS
            }
            if role_permissions
            else {}
        )
    return {**user.to_dict(), "permissions": permissions}


def permission_required(*fields):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not has_permission(g.current_user, *fields):
                return jsonify({"error": "Vous n’êtes pas autorisé à accéder à ce module."}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def stock_movement_permission_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.current_user.type == "admin":
            return view(*args, **kwargs)

        movement = None
        if request.method in {"PUT", "DELETE"}:
            movement = db.session.get(StockMovement, kwargs.get("movement_id"))
            if movement is None:
                return jsonify({"error": "Mouvement introuvable."}), 404

        movement_types = {
            "reception": "reception",
            "achat": "achat",
            "livraison": "livraison",
            "vente": "vente",
        }
        required_fields = set()
        if movement is not None:
            required_fields.add(movement_types[movement.type])
        if request.method in {"POST", "PUT"}:
            payload = request.get_json(silent=True)
            movement_type = payload.get("type") if isinstance(payload, dict) else None
            if movement_type not in movement_types:
                return jsonify({"error": "Type de mouvement invalide."}), 400
            required_fields.add(movement_types[movement_type])
        if not required_fields:
            required_fields.update(movement_types.values())
        if not has_permission(g.current_user, *required_fields):
            return jsonify({"error": "Vous n’êtes pas autorisé à gérer ce mouvement."}), 403
        return view(*args, **kwargs)

    return wrapped


def request_data():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "Corps JSON invalide"}), 400)
    return payload, None


def validate_user_data(payload, creating):
    required = ("nom", "prenom", "login", "type")
    for field in required:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"Le champ « {field} » est obligatoire."

    password = payload.get("password")
    if creating and (not isinstance(password, str) or not password):
        return "Le mot de passe est obligatoire."
    if password is not None and (not isinstance(password, str) or len(password) < 8):
        return "Le mot de passe doit contenir au moins 8 caractères."

    if payload["type"] not in VALID_ROLES:
        return "Le rôle sélectionné est invalide."
    city = payload.get("ville", "")
    if not isinstance(city, str) or len(city.strip()) > 100:
        return "La ville ne doit pas dépasser 100 caractères."

    if "lpp" in payload:
        try:
            lpp = int(payload["lpp"])
        except (TypeError, ValueError):
            return "Le nombre d’éléments par page doit être un entier positif."
        if lpp < 1 or lpp > 100:
            return "Le nombre d’éléments par page doit être compris entre 1 et 100."

    return None


def validate_client_data(payload):
    required = ("nom", "prenom", "tel", "email")
    for field in required:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"Le champ « {field} » est obligatoire."

    email = payload["email"].strip()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return "L’adresse e-mail est invalide."
    if len(payload["nom"].strip()) > 120 or len(payload["prenom"].strip()) > 120:
        return "Le nom et le prénom ne doivent pas dépasser 120 caractères."
    if len(payload["tel"].strip()) > 40 or len(email) > 254:
        return "Le téléphone ou l’adresse e-mail est trop long."
    for field in ("specialite", "ville"):
        value = payload.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > 100:
            return f"Le champ « {field} » ne doit pas dépasser 100 caractères."

    if "id" in payload and payload["id"] not in (None, ""):
        try:
            client_id = int(payload["id"])
        except (TypeError, ValueError):
            return "L’identifiant doit être un entier positif."
        if client_id < 1:
            return "L’identifiant doit être un entier positif."

    return None


def validate_article_data(payload):
    required = ("ref", "description", "nom")
    for field in required:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"Le champ « {field} » est obligatoire."

    limits = {"ref": 50, "famille": 120, "description": 255, "categorie": 120, "nom": 160}
    for field, maximum in limits.items():
        value = payload.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > maximum:
            return f"Le champ « {field} » ne doit pas dépasser {maximum} caractères."

    quantities = {}
    for field in ("v_entrees", "v_retour"):
        try:
            quantities[field] = int(payload.get(field, 0))
        except (TypeError, ValueError):
            return "Les quantités doivent être des nombres entiers positifs."
        if quantities[field] < 0:
            return "Les quantités doivent être des nombres entiers positifs."

    if quantities["v_retour"] > quantities["v_entrees"]:
        return "La quantité retournée ne peut pas dépasser les entrées."
    return None


def validate_supplier_data(payload):
    for field in ("nom", "prenom", "tel", "email"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"Le champ « {field} » est obligatoire."
    if "@" not in payload["email"] or "." not in payload["email"].rsplit("@", 1)[-1]:
        return "L’adresse e-mail est invalide."
    if len(payload["nom"].strip()) > 120 or len(payload["prenom"].strip()) > 120:
        return "Le nom et le prénom ne doivent pas dépasser 120 caractères."
    if len(payload["tel"].strip()) > 40 or len(payload["email"].strip()) > 254:
        return "Le téléphone ou l’adresse e-mail est trop long."
    for field in ("specialite", "ville"):
        value = payload.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > 100:
            return f"Le champ « {field} » ne doit pas dépasser 100 caractères."
    return None


def validate_movement_data(payload):
    movement_type = payload.get("type")
    if movement_type not in {"reception", "achat", "livraison", "vente"}:
        return "Le type de mouvement est invalide."
    article_ref = payload.get("article_ref")
    if not isinstance(article_ref, str) or not article_ref.strip():
        return "Un article doit être sélectionné."
    try:
        quantity = int(payload.get("quantite"))
    except (TypeError, ValueError):
        return "La quantité doit être un entier positif."
    if quantity < 1:
        return "La quantité doit être un entier positif."
    try:
        movement_date = date.fromisoformat(payload.get("date_mouvement", ""))
    except (TypeError, ValueError):
        return "La date doit être au format AAAA-MM-JJ."

    supplier_id = payload.get("id_fournisseur")
    client_id = payload.get("id_client")
    if movement_type in {"reception", "achat"}:
        try:
            supplier_id = int(supplier_id)
        except (TypeError, ValueError):
            return "Un fournisseur doit être sélectionné."
        if db.session.get(Supplier, supplier_id) is None:
            return "Fournisseur introuvable."
    elif movement_type in {"livraison", "vente"}:
        try:
            client_id = int(client_id)
        except (TypeError, ValueError):
            return "Un client doit être sélectionné."
        if db.session.get(Client, client_id) is None:
            return "Client introuvable."

    if db.session.get(Article, article_ref.strip()) is None:
        return "Article introuvable."
    return None


def movement_delta(movement_type, quantity):
    return quantity if movement_type in {"reception", "achat"} else -quantity


def apply_movement_delta(article, movement_type, quantity):
    delta = movement_delta(movement_type, quantity)
    if not adjust_linked_pos_product(article, delta):
        return False
    apply_article_stock_delta(article, delta)
    return True


def apply_article_stock_delta(article, delta):
    if delta >= 0:
        article.v_entrees += delta
    else:
        article.v_retour -= delta
    article.v_stocks = article.v_entrees - article.v_retour


def adjust_linked_pos_product(article, delta):
    product = PosProduct.query.filter_by(article_ref=article.ref).with_for_update().first()
    if product is None:
        return True
    updated_quantity = product.qty + delta
    if updated_quantity < 0:
        return False
    product.qty = updated_quantity
    return True


def validate_pos_product(payload):
    required = ("product_code", "gen_name")
    for field in required:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, f"Le champ « {field} » est obligatoire."

    text_limits = {
        "product_code": 120,
        "gen_name": 160,
        "product_name": 255,
        "supplier": 160,
        "barcode": 120,
    }
    values = {}
    for field, maximum in text_limits.items():
        value = payload.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > maximum:
            return None, f"Le champ « {field} » ne doit pas dépasser {maximum} caractères."
        values[field] = value.strip()

    article_ref = payload.get("article_ref", "")
    if not isinstance(article_ref, str) or len(article_ref.strip()) > 50:
        return None, "La référence de l’article associé est invalide."
    values["article_ref"] = article_ref.strip()

    for field in ("date_arrival", "expiry_date"):
        value = payload.get(field, "")
        if not isinstance(value, str):
            return None, f"Le champ « {field} » doit être une date AAAA-MM-JJ."
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                return None, f"Le champ « {field} » doit être une date AAAA-MM-JJ."
        values[field] = value

    for field in ("price", "o_price"):
        try:
            value = Decimal(str(payload.get(field))).quantize(
                MONEY_QUANTUM, rounding=ROUND_HALF_UP
            )
        except (InvalidOperation, TypeError, ValueError):
            return None, f"Le champ « {field} » doit être un montant valide."
        if not value.is_finite() or value < 0:
            return None, f"Le champ « {field} » doit être un montant positif ou nul."
        values[field] = value

    pricing_configured = payload.get("pricing_configured", True)
    if not isinstance(pricing_configured, bool):
        return None, "Le statut de configuration des prix est invalide."
    values["pricing_configured"] = pricing_configured

    for field in ("qty",):
        try:
            value = int(payload.get(field, 0))
        except (TypeError, ValueError):
            return None, f"Le champ « {field} » doit être un entier positif ou nul."
        if value < 0 or str(value) != str(payload.get(field, 0)).strip():
            return None, f"Le champ « {field} » doit être un entier positif ou nul."
        values[field] = value

    return values, None


def get_or_create_pos_contact(model, name):
    normalized_name = " ".join(name.split())
    name_key = normalized_name.casefold()
    contact = model.query.filter_by(name_key=name_key).first()
    if contact is None:
        contact = model(name=normalized_name, name_key=name_key)
        db.session.add(contact)
    return contact


RESOURCE_CONFIG = {
    "vehicles": {
        "model": Vehicle,
        "fields": {
            "model": "text",
            "immatricule": "text",
            "annee": "int",
            "puissance": "int",
            "location": "bool",
            "date_d_loc": "date",
            "date_f_loc": "date",
        },
        "required": ("model", "immatricule", "annee", "puissance"),
        "label": "Véhicule",
        "permission": "voiture",
    },
    "fairs": {
        "model": Fair,
        "fields": {
            "nom": "text",
            "ville": "text",
            "adresse": "text",
            "contact": "text",
            "d_limite": "date",
            "assigned_vehicle_id": "int",
            "type": "text",
            "organizer": "text",
            "start_date": "date",
            "end_date": "date",
            "product_send_deadline": "date",
            "status": "text",
            "allow_late_send": "bool",
            "late_send_reason": "text",
            "manager_notes": "text",
        },
        "required": ("nom", "ville", "adresse", "contact", "d_limite"),
        "optional": (
            "assigned_vehicle_id",
            "auto_assign",
            "organizer",
            "start_date",
            "end_date",
            "product_send_deadline",
            "status",
            "allow_late_send",
            "late_send_reason",
            "manager_notes",
        ),
        "label": "Foire",
        "permission": "foire",
    },
    "stand-types": {
        "model": StandType,
        "fields": {"type": "text", "etat": "text"},
        "required": ("type", "etat"),
        "label": "Type de stand",
        "permission": "liste_stand",
    },
    "stand-inventory": {
        "model": StandInventory,
        "fields": {"id_stand": "int", "ref_article": "text", "quantite": "int", "date_ch": "date"},
        "required": ("id_stand", "ref_article", "quantite", "date_ch"),
        "label": "Article de stand",
        "permission": "stand",
    },
    "reservations": {
        "model": Reservation,
        "fields": {
            "id_agent": "int",
            "id_foire": "int",
            "taille_stand": "text",
            "logement": "text",
            "date_d": "date",
            "date_f": "date",
            "etat": "int",
            "date_c": "date",
        },
        "required": ("id_agent", "id_foire", "taille_stand", "logement", "date_d", "date_f"),
        "label": "Réservation",
        "permission": "reservation",
    },
    "works": {
        "model": Work,
        "fields": {
            "date_d": "date",
            "date_f": "date",
            "id_foire": "int",
            "id_stand": "int",
            "id_vendeur": "int",
            "id_deco": "int",
            "id_chauffeur": "int",
            "id_voiture": "int",
            "flow": "text",
        },
        "required": ("date_d", "date_f", "id_foire", "id_stand", "id_vendeur", "id_deco", "id_chauffeur", "id_voiture", "flow"),
        "label": "Mission",
        "permission": "work",
    },
    "permissions": {
        "model": Permission,
        "fields": {
            "type_user": "text",
            "foire": "bool",
            "stand": "bool",
            "liste_stand": "bool",
            "article": "bool",
            "work": "bool",
            "fournisseur": "bool",
            "client": "bool",
            "reservation": "bool",
            "empl": "bool",
            "voiture": "bool",
            "mouvement": "bool",
            "livraison": "bool",
            "reception": "bool",
            "vente": "bool",
            "achat": "bool",
        },
        "required": ("type_user",),
        "label": "Droit d’accès",
        "key": "type_user",
        "admin_read": True,
        "permission": "empl",
        "admin_write": True,
    },
}


def validate_resource_payload(config, payload):
    fields = config["fields"]
    values = {}
    for field in config["required"]:
        if field not in payload or payload[field] is None or payload[field] == "":
            return None, f"Le champ « {field} » est obligatoire."

    for field, kind in fields.items():
        if field not in payload:
            continue
        value = payload[field]
        if kind == "text":
            if not isinstance(value, str):
                return None, f"Le champ « {field} » doit être du texte."
            value = value.strip()
            if field in config["required"] and not value:
                return None, f"Le champ « {field} » est obligatoire."
        elif kind == "int":
            if value in ("", None) and field not in config["required"]:
                values[field] = None
                continue
            try:
                value = int(value)
            except (TypeError, ValueError):
                return None, f"Le champ « {field} » doit être un entier."
            if field in {"quantite", "annee", "puissance"} and value < 0:
                return None, f"Le champ « {field} » doit être positif."
        elif kind == "date":
            if value == "" and field not in config["required"]:
                values[field] = None
                continue
            if not isinstance(value, str):
                return None, f"Le champ « {field} » doit être une date AAAA-MM-JJ."
            try:
                date.fromisoformat(value)
            except ValueError:
                return None, f"Le champ « {field} » doit être une date AAAA-MM-JJ."
            if config["model"] is Fair and field in {
                "start_date",
                "end_date",
                "product_send_deadline",
            }:
                value = date.fromisoformat(value)
        elif kind == "bool":
            if not isinstance(value, bool):
                return None, f"Le champ « {field} » doit être vrai ou faux."
        values[field] = value

    if config["model"] is Fair:
        valid_statuses = {"planned", "active", "completed", "cancelled"}
        if values.get("status") == "":
            values["status"] = None
        if values.get("status") not in (None, *valid_statuses):
            return None, "Le statut de la foire est invalide."
        if values.get("start_date") and values.get("end_date"):
            if values["end_date"] < values["start_date"]:
                return None, "La date de fin doit être postérieure ou égale à la date de début."
        if values.get("product_send_deadline") and values.get("start_date"):
            if values["product_send_deadline"] > values["start_date"]:
                return None, "La date limite d’envoi doit précéder ou coïncider avec le début de la foire."
        if values.get("allow_late_send") and not values.get("late_send_reason", "").strip():
            return None, "Une justification est obligatoire lorsque l’envoi tardif est autorisé."
        for field in ("organizer", "late_send_reason", "manager_notes"):
            if values.get(field) == "":
                values[field] = None
        if values.get("assigned_vehicle_id") is not None and db.session.get(
            Vehicle, values["assigned_vehicle_id"]
        ) is None:
            return None, "Véhicule introuvable."
        if values.get("manager_notes") and len(values["manager_notes"]) > 2000:
            return None, "Les notes du responsable ne doivent pas dépasser 2000 caractères."

    if "date_d" in values and "date_f" in values and values["date_f"] < values["date_d"]:
        return None, "La date de fin doit être postérieure ou égale à la date de début."
    if config["model"] is Work and values.get("flow") not in {"en attente", "en cours", "achevee"}:
        return None, "L’état de la mission est invalide."
    for field, value in values.items():
        column = config["model"].__table__.columns[field]
        maximum = getattr(column.type, "length", None)
        if maximum and isinstance(value, str) and len(value) > maximum:
            return None, f"Le champ « {field} » ne doit pas dépasser {maximum} caractères."
    if config["model"] is StandInventory:
        if db.session.get(StandType, values["id_stand"]) is None:
            return None, "Type de stand introuvable."
        if db.session.get(Article, values["ref_article"]) is None:
            return None, "Article introuvable."
        if values["quantite"] < 1:
            return None, "La quantité doit être supérieure à zéro."
    if config["model"] is Reservation:
        if db.session.get(User, values["id_agent"]) is None or db.session.get(Fair, values["id_foire"]) is None:
            return None, "Agent ou foire introuvable."
    if config["model"] is Work:
        valid_references = (
            db.session.get(Fair, values["id_foire"]),
            db.session.get(StandType, values["id_stand"]),
            db.session.get(User, values["id_vendeur"]),
            db.session.get(User, values["id_deco"]),
            db.session.get(User, values["id_chauffeur"]),
            db.session.get(Vehicle, values["id_voiture"]),
        )
        if any(reference is None for reference in valid_references):
            return None, "Un membre d’équipe, une foire, un stand ou un véhicule est introuvable."
    if config["model"] is Permission and values["type_user"] not in VALID_ROLES:
        return None, "Le type de rôle est invalide."
    return values, None


def prepare_fair_team(model, payload, values):
    if model is not Fair:
        return [], None

    auto_assign = payload.get("auto_assign", False)
    if not isinstance(auto_assign, bool):
        return [], ("Le choix d’affectation automatique est invalide.", 400)
    start_date = values.get("start_date")
    end_date = values.get("end_date")
    if auto_assign and (start_date is None or end_date is None):
        return [], (
            "Les dates de début et de fin sont nécessaires pour affecter automatiquement l’équipe.",
            400,
        )

    team_assignments = []
    if auto_assign:
        for role in ("vendeur", "chauffeur"):
            candidates = User.query.filter_by(type=role).order_by(User.id.asc()).all()
            available = [
                candidate
                for candidate in candidates
                if fair_assignment_conflict(candidate.id, start_date, end_date) is None
            ]
            if not available:
                return [], (
                    f"Aucun {role} n’est disponible sur toute la période. La foire n’a pas été créée.",
                    409,
                )
            team_assignments.append((role, available[0]))

        vehicles = Vehicle.query.order_by(Vehicle.id.asc()).all()
        if values.get("assigned_vehicle_id") is not None:
            preferred_vehicle = db.session.get(
                Vehicle, values["assigned_vehicle_id"]
            )
            vehicles = [preferred_vehicle] + [
                vehicle
                for vehicle in vehicles
                if vehicle.id != preferred_vehicle.id
            ]
        available_vehicle = next(
            (
                vehicle
                for vehicle in vehicles
                if vehicle is not None
                and fair_vehicle_conflict(vehicle, start_date, end_date) is None
            ),
            None,
        )
        if available_vehicle is None:
            return [], (
                "Aucun véhicule n’est disponible sur toute la période. La foire n’a pas été créée.",
                409,
            )
        values["assigned_vehicle_id"] = available_vehicle.id
    elif values.get("assigned_vehicle_id") is not None:
        if start_date is None or end_date is None:
            return [], (
                "Les dates de début et de fin sont nécessaires pour affecter un véhicule.",
                400,
            )
        vehicle = db.session.get(Vehicle, values["assigned_vehicle_id"])
        conflict = fair_vehicle_conflict(vehicle, start_date, end_date)
        if conflict:
            return [], (conflict, 409)

    return team_assignments, None



def setup_fair_automation(fair, db_session, current_user_id=1):
    """
    Workflow complet déclenché à chaque ajout de foire :
    1. Voiture & Chauffeur affectés avant 2 jours en mission (Work).
    2. Vendeur disponible affecté pendant la période de foire.
    3. Caisse créée pour ce vendeur et cette foire avec un identifiant unique (PosRegister).
    4. Décorateur et Stand réservés dans LAGA (reservations) et liés à la mission.
    5. Transfert du stock du stand vers le stock de la foire (FairInventoryBalance + FairInventoryMovement).
    6. Le stock de foire sera débité en temps réel par les ventes de la caisse associée.
    """
    today = date.today()
    start_date = fair.start_date
    if start_date is None:
        try:
            start_date = date.fromisoformat(fair.d_limite) if fair.d_limite else today
        except ValueError:
            start_date = today
        fair.start_date = start_date

    end_date = fair.end_date
    if end_date is None:
        end_date = start_date + timedelta(days=7)
        fair.end_date = end_date

    if not fair.status:
        fair.status = "active"

    # 1. Mission Chauffeur & Voiture (début 2 jours avant la foire)
    mission_start = start_date - timedelta(days=2)
    mission_end = end_date

    chauffeurs = User.query.filter_by(type="chauffeur").order_by(User.id.asc()).all()
    chauffeur = next(
        (c for c in chauffeurs if fair_assignment_conflict(c.id, mission_start, mission_end) is None),
        chauffeurs[0] if chauffeurs else None
    )

    vehicles = Vehicle.query.order_by(Vehicle.id.asc()).all()
    if fair.assigned_vehicle_id:
        fav = db_session.get(Vehicle, fair.assigned_vehicle_id)
        if fav:
            vehicles = [fav] + [v for v in vehicles if v.id != fav.id]
    vehicle = next(
        (v for v in vehicles if fair_vehicle_conflict(v, mission_start, mission_end) is None),
        vehicles[0] if vehicles else None
    )
    if vehicle:
        fair.assigned_vehicle_id = vehicle.id

    # 2. Vendeur disponible pendant la période de la foire
    vendeurs = User.query.filter_by(type="vendeur").order_by(User.id.asc()).all()
    vendeur = next(
        (vd for vd in vendeurs if fair_assignment_conflict(vd.id, start_date, end_date) is None),
        vendeurs[0] if vendeurs else None
    )

    # 3. Décorateur et Stand réservés dans LAGA
    decos = User.query.filter(User.type.in_(["deco", "laga"])).order_by(User.id.asc()).all()
    if not decos:
        decos = User.query.filter_by(type="deco").order_by(User.id.asc()).all()
    decorateur = next(
        (d for d in decos if fair_assignment_conflict(d.id, start_date, end_date) is None),
        decos[0] if decos else None
    )

    # Stand : priorité à un stand ayant des articles en stock dans stands (StandInventory)
    stands_with_stock = (
        db_session.query(StandType)
        .join(StandInventory, StandType.id == StandInventory.id_stand)
        .filter(StandInventory.quantite > 0)
        .distinct()
        .all()
    )
    all_stands = StandType.query.order_by(StandType.id.asc()).all()
    stand = stands_with_stock[0] if stands_with_stock else (all_stands[0] if all_stands else None)
    if stand is None:
        stand = StandType(type="Stand Standard", etat="en_stock")
        db_session.add(stand)
        db_session.flush()

    # Affectations d'équipe (FairAssignment)
    if chauffeur:
        db_session.add(FairAssignment(
            fair_id=fair.id,
            user_id=chauffeur.id,
            role="chauffeur",
            start_date=mission_start,
            end_date=mission_end,
            status="confirmed",
            source="automatic",
            created_by=current_user_id,
            notes="Mission transport débutant 2 jours avant la foire.",
        ))

    if vendeur:
        db_session.add(FairAssignment(
            fair_id=fair.id,
            user_id=vendeur.id,
            role="vendeur",
            start_date=start_date,
            end_date=end_date,
            status="confirmed",
            source="automatic",
            created_by=current_user_id,
            notes="Vendeur assigné pour la durée de la foire.",
        ))

    if decorateur:
        db_session.add(FairAssignment(
            fair_id=fair.id,
            user_id=decorateur.id,
            role="deco",
            start_date=start_date,
            end_date=end_date,
            status="confirmed",
            source="automatic",
            created_by=current_user_id,
            notes="Décorateur réservé pour la foire.",
        ))

    # Réservation dans LAGA (reservations)
    reservation_agent_id = decorateur.id if decorateur else (vendeur.id if vendeur else (current_user_id or 1))
    reservation = Reservation(
        id_agent=reservation_agent_id,
        id_foire=fair.id,
        taille_stand=stand.type,
        logement=fair.ville or "Sur place",
        date_d=start_date.isoformat(),
        date_f=end_date.isoformat(),
        etat=1,
        date_c=today.isoformat(),
    )
    db_session.add(reservation)

    # Mission complète (Work)
    flow_status = "en cours" if mission_start <= today <= end_date else "en attente"
    work = Work(
        date_d=mission_start.isoformat(),
        date_f=end_date.isoformat(),
        id_foire=fair.id,
        id_stand=stand.id,
        id_vendeur=vendeur.id if vendeur else (current_user_id or 1),
        id_deco=decorateur.id if decorateur else (current_user_id or 1),
        id_chauffeur=chauffeur.id if chauffeur else (current_user_id or 1),
        id_voiture=vehicle.id if vehicle else 1,
        flow=flow_status,
    )
    db_session.add(work)

    # 4. Caisse créée pour ce vendeur et cette foire avec un identifiant unique
    caisse_code = f"CAISSE-F{fair.id}-V{vendeur.id if vendeur else 1}"
    caisse_name = f"Caisse {fair.nom} — {vendeur.prenom + ' ' + vendeur.nom if vendeur else 'Vendeur'}"
    pos_reg = PosRegister.query.filter_by(fair_id=fair.id, seller_id=vendeur.id if vendeur else 1).first()
    if not pos_reg:
        pos_reg = PosRegister(
            code=caisse_code,
            nom=caisse_name,
            fair_id=fair.id,
            seller_id=vendeur.id if vendeur else (current_user_id or 1),
            status="active",
        )
        db_session.add(pos_reg)

    # 5. Transférer le stock du stand comme le stock de foire
    stand_items = StandInventory.query.filter_by(id_stand=stand.id).all()
    transferred_count = 0
    transferred_qty = 0

    for s_item in stand_items:
        if s_item.quantite > 0 and s_item.ref_article:
            bal = FairInventoryBalance.query.filter_by(fair_id=fair.id, article_ref=s_item.ref_article).first()
            if bal:
                bal.quantity += s_item.quantite
            else:
                bal = FairInventoryBalance(fair_id=fair.id, article_ref=s_item.ref_article, quantity=s_item.quantite)
                db_session.add(bal)
            db_session.add(FairInventoryMovement(
                fair_id=fair.id,
                article_ref=s_item.ref_article,
                movement_type="transfer_in",
                quantity_delta=s_item.quantite,
                movement_date=today,
                reference=f"Transport Stand #{stand.id} ({stand.type}) via {vehicle.model if vehicle else 'Voiture'}",
                notes=f"Stock du stand {stand.type} de Laga transporté vers la foire {fair.nom} par le chauffeur {chauffeur.prenom + ' ' + chauffeur.nom if chauffeur else ''} avec la voiture {vehicle.model + ' (' + vehicle.immatricule + ')' if vehicle else ''}",
                created_by=current_user_id,
            ))
            transferred_count += 1
            transferred_qty += s_item.quantite

    # Si le stand n'avait pas d'articles, transférer des articles du catalogue pour que la foire ait du stock à vendre
    if transferred_count == 0:
        cat_articles = Article.query.filter(Article.quantite > 0).limit(5).all()
        if not cat_articles:
            cat_articles = Article.query.limit(5).all()
        for art in cat_articles:
            init_qty = 15
            bal = FairInventoryBalance.query.filter_by(fair_id=fair.id, article_ref=art.ref).first()
            if bal:
                bal.quantity += init_qty
            else:
                bal = FairInventoryBalance(fair_id=fair.id, article_ref=art.ref, quantity=init_qty)
                db_session.add(bal)
            db_session.add(FairInventoryMovement(
                fair_id=fair.id,
                article_ref=art.ref,
                movement_type="transfer_in",
                quantity_delta=init_qty,
                movement_date=today,
                reference=f"Transport Stand #{stand.id} ({stand.type}) via {vehicle.model if vehicle else 'Voiture'}",
                notes=f"Stock du stand {stand.type} de Laga transporté vers la foire {fair.nom} avec la voiture {vehicle.model if vehicle else ''}",
                created_by=current_user_id,
            ))
            transferred_count += 1
            transferred_qty += init_qty

    # Synchroniser les PosProduct pour la caisse
    for bal in FairInventoryBalance.query.filter_by(fair_id=fair.id).all():
        pos_p = PosProduct.query.filter_by(article_ref=bal.article_ref).first()
        if not pos_p:
            art = Article.query.filter_by(ref=bal.article_ref).first()
            if art:
                db_session.add(PosProduct(
                    product_code=art.ref,
                    gen_name=art.nom,
                    product_name=art.nom,
                    article_ref=art.ref,
                    o_price=art.prix,
                    price=art.prix,
                    qty=100,
                    qty_sold=0,
                    date_arrival=today,
                ))

    return {
        "fair_id": fair.id,
        "fair_name": fair.nom,
        "chauffeur": f"{chauffeur.prenom} {chauffeur.nom}" if chauffeur else "Aucun",
        "vehicle": f"{vehicle.model} ({vehicle.immatricule})" if vehicle else "Aucun",
        "mission_start": mission_start.isoformat(),
        "mission_end": mission_end.isoformat(),
        "vendeur": f"{vendeur.prenom} {vendeur.nom}" if vendeur else "Aucun",
        "decorateur": f"{decorateur.prenom} {decorateur.nom}" if decorateur else "Aucun",
        "stand": f"{stand.type} (id: {stand.id})",
        "caisse_code": caisse_code,
        "caisse_name": caisse_name,
        "transferred_items": transferred_count,
        "transferred_qty": transferred_qty,
        "work_id": work.id if work else None,
        "reservation_id": reservation.id if reservation else None,
    }


def resource_key_column(config):
    model = config["model"]
    return model.__table__.primary_key.columns.values()[0]


def load_resource(config, key):
    model = config["model"]
    key_column = resource_key_column(config)
    key_type = key_column.type.python_type
    try:
        normalized_key = key_type(key)
    except (TypeError, ValueError):
        return None, None
    return db.session.get(model, normalized_key), normalized_key


@api_bp.route("/<string:resource>", methods=["GET", "POST"])
@login_required
def resource_collection(resource):
    config = RESOURCE_CONFIG.get(resource)
    if config is None:
        return jsonify({"error": "Module introuvable."}), 404

    if request.method == "GET":
        if not has_permission(g.current_user, config["permission"]):
            return jsonify({"error": "Vous n’êtes pas autorisé à accéder à ce module."}), 403
        model = config["model"]
        key_column = resource_key_column(config)
        rows = model.query.order_by(key_column.asc()).all()
        return jsonify([
            row.to_dict() for row in rows
        ])

    if config.get("admin_write") and g.current_user.type != "admin":
        return jsonify({"error": "Accès réservé aux administrateurs."}), 403
    if not config.get("admin_write") and not has_permission(g.current_user, config["permission"]):
        return jsonify({"error": "Vous n’êtes pas autorisé à gérer ce module."}), 403

    payload, error = request_data()
    if error:
        return error
    values, validation_error = validate_resource_payload(config, payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    model = config["model"]
    if config.get("key") and db.session.get(model, values[config["key"]]) is not None:
        return jsonify({"error": f"{config['label']} déjà enregistré."}), 409

    row = model(**values)
    db.session.add(row)
    automation_result = None
    try:
        if model is Fair:
            db.session.flush()
            automation_result = setup_fair_automation(
                row,
                db.session,
                g.current_user.id if hasattr(g, 'current_user') and g.current_user else 1,
            )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": f"Impossible d’enregistrer ce {config['label'].lower()} : une référence existe déjà ou est invalide."}), 409
    message = f"{config['label']} créé."
    response = {"message": message, "item": row.to_dict()}
    if model is Fair and automation_result:
        response["message"] = (
            f"Foire « {row.nom} » créée avec succès ! "
            f"Mission chauffeur ({automation_result['chauffeur']} avec véhicule {automation_result['vehicle']}) créée 2 jours avant ({automation_result['mission_start']}). "
            f"Vendeur ({automation_result['vendeur']}) affecté avec caisse {automation_result['caisse_code']}. "
            f"Stand ({automation_result['stand']}) et décorateur ({automation_result['decorateur']}) réservés dans Laga. "
            f"{automation_result['transferred_qty']} unité(s) de stock transférée(s) du stand prêtes à la vente."
        )
        response["automation"] = automation_result
        response["assignments"] = [
            assignment.to_dict() for assignment in FairAssignment.query.filter_by(
                fair_id=row.id
            ).order_by(FairAssignment.id.asc()).all()
        ]
    return jsonify(response), 201


@api_bp.route("/<string:resource>/<string:record_key>", methods=["PUT", "DELETE"])
@login_required
def resource_item(resource, record_key):
    config = RESOURCE_CONFIG.get(resource)
    if config is None:
        return jsonify({"error": "Module introuvable."}), 404
    if config.get("admin_write") and g.current_user.type != "admin":
        return jsonify({"error": "Accès réservé aux administrateurs."}), 403
    if not config.get("admin_write") and not has_permission(g.current_user, config["permission"]):
        return jsonify({"error": "Vous n’êtes pas autorisé à gérer ce module."}), 403

    row, normalized_key = load_resource(config, record_key)
    if row is None:
        return jsonify({"error": f"{config['label']} introuvable."}), 404
    if request.method == "DELETE":
        db.session.delete(row)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": f"Impossible de supprimer ce {config['label'].lower()} car il est utilisé par d’autres données."}), 409
        return jsonify({"message": f"{config['label']} supprimé."})

    payload, error = request_data()
    if error:
        return error
    values, validation_error = validate_resource_payload(config, payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400
    key_name = config.get("key", resource_key_column(config).name)
    if key_name in values and values[key_name] != normalized_key:
        return jsonify({"error": "La clé de l’enregistrement ne peut pas être modifiée."}), 400
    for field, value in values.items():
        if field != key_name:
            setattr(row, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": f"Impossible de modifier ce {config['label'].lower()} : une référence existe déjà ou est invalide."}), 409
    return jsonify({"message": f"{config['label']} modifié.", "item": row.to_dict()})


@api_bp.route("/resource-lookups/<string:resource>", methods=["GET"])
@login_required
def resource_lookups(resource):
    config = RESOURCE_CONFIG.get(resource)
    if config is None:
        return jsonify({"error": "Module introuvable."}), 404
    if not has_permission(g.current_user, config["permission"]):
        return jsonify({"error": "Vous n’êtes pas autorisé à accéder à ce module."}), 403

    if resource == "stand-inventory":
        return jsonify({
            "id_stand": [
                {"value": row.id, "label": row.type}
                for row in StandType.query.order_by(StandType.id.asc()).all()
            ],
            "ref_article": [
                {"value": row.ref, "label": f"{row.ref} — {row.nom}"}
                for row in Article.query.order_by(Article.ref.asc()).all()
            ],
        })
    if resource == "reservations":
        return jsonify({
            "id_agent": [
                {"value": row.id, "label": f"{row.prenom} {row.nom}".strip()}
                for row in User.query.order_by(User.id.asc()).all()
            ],
            "id_foire": [
                {"value": row.id, "label": row.nom}
                for row in Fair.query.order_by(Fair.id.asc()).all()
            ],
        })
    if resource == "works":
        return jsonify({
            "id_foire": [
                {"value": row.id, "label": row.nom}
                for row in Fair.query.order_by(Fair.id.asc()).all()
            ],
            "id_stand": [
                {"value": row.id, "label": row.type}
                for row in StandType.query.order_by(StandType.id.asc()).all()
            ],
            "id_vendeur": [
                {"value": row.id, "label": f"{row.prenom} {row.nom}".strip()}
                for row in User.query.filter_by(type="vendeur").order_by(User.id.asc()).all()
            ],
            "id_deco": [
                {"value": row.id, "label": f"{row.prenom} {row.nom}".strip()}
                for row in User.query.filter_by(type="deco").order_by(User.id.asc()).all()
            ],
            "id_chauffeur": [
                {"value": row.id, "label": f"{row.prenom} {row.nom}".strip()}
                for row in User.query.filter_by(type="chauffeur").order_by(User.id.asc()).all()
            ],
            "id_voiture": [
                {"value": row.id, "label": f"{row.model} — {row.immatricule}"}
                for row in Vehicle.query.order_by(Vehicle.id.asc()).all()
            ],
        })
    if resource == "fairs":
        return jsonify({
            "assigned_vehicle_id": [
                {
                    "value": row.id,
                    "label": f"{row.model} — {row.immatricule}",
                }
                for row in Vehicle.query.order_by(Vehicle.id.asc()).all()
            ],
        })
    return jsonify({})


# ---------------------------------------------------------------------------
# Rate limiting & Audit Logging & Pagination
# ---------------------------------------------------------------------------

_login_attempts = defaultdict(list)

def check_login_rate_limit(ip, max_attempts=5, window_seconds=300):
    now = time.time()
    attempts = [t for t in _login_attempts[ip] if now - t < window_seconds]
    _login_attempts[ip] = attempts
    if len(attempts) >= max_attempts:
        retry_after = int(window_seconds - (now - attempts[0]))
        return False, retry_after
    return True, 0

def record_login_failure(ip):
    _login_attempts[ip].append(time.time())

def record_login_success(ip):
    _login_attempts.pop(ip, None)

audit_logger = logging.getLogger("okba_audit")
if not audit_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[AUDIT %(asctime)s] %(message)s"))
    audit_logger.addHandler(_handler)
    audit_logger.setLevel(logging.INFO)

def log_audit(action, details=None):
    user_str = f"user_id={g.current_user.id} ({g.current_user.login})" if hasattr(g, 'current_user') and g.current_user else "anonymous"
    ip = request.remote_addr or "unknown"
    msg = f"{action} by {user_str} from {ip}"
    if details:
        msg += f" - {details}"
    audit_logger.info(msg)

def paginate_query(query, default_per_page=10, max_per_page=100):
    page_raw = request.args.get("page")
    if not page_raw:
        return None, None
    try:
        page = max(1, int(page_raw))
    except (ValueError, TypeError):
        page = 1
    
    per_page_raw = request.args.get("per_page")
    try:
        user_lpp = getattr(g.current_user, 'lpp', None) if hasattr(g, 'current_user') and g.current_user else None
        per_page = int(per_page_raw) if per_page_raw else (int(user_lpp) if user_lpp else default_per_page)
        per_page = max(1, min(max_per_page, per_page))
    except (ValueError, TypeError):
        per_page = default_per_page

    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page
    items = query.offset(offset).limit(per_page).all()
    
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }, items


@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@api_bp.route("/login", methods=["POST"])
def login():
    client_ip = request.remote_addr or "127.0.0.1"
    allowed, retry_after = check_login_rate_limit(client_ip)
    if not allowed:
        log_audit("LOGIN_RATE_LIMITED", f"ip={client_ip}")
        return jsonify({"error": f"Trop de tentatives. Veuillez réessayer dans {retry_after} secondes."}), 429

    payload, error = request_data()
    if error:
        return error

    login_value = payload.get("login")
    password_value = payload.get("password")
    if not isinstance(login_value, str) or not isinstance(password_value, str):
        return jsonify({"error": "Login et mot de passe requis"}), 400

    user = User.query.filter_by(login=login_value.strip()).first()
    if user is None:
        record_login_failure(client_ip)
        log_audit("LOGIN_FAILED", f"login={login_value}")
        return jsonify({"error": "Identifiants incorrects"}), 401

    stored_password = user.pw or ""
    valid_password = (
        check_password_hash(stored_password, password_value)
        if stored_password.startswith(("scrypt:", "pbkdf2:"))
        else stored_password == password_value
    )
    if not valid_password:
        record_login_failure(client_ip)
        log_audit("LOGIN_FAILED", f"login={login_value}")
        return jsonify({"error": "Identifiants incorrects"}), 401

    record_login_success(client_ip)
    if not stored_password.startswith(("scrypt:", "pbkdf2:")):
        user.pw = generate_password_hash(password_value)
        db.session.commit()

    session.clear()
    session["user_id"] = user.id
    log_audit("LOGIN_SUCCESS", f"user_id={user.id} login={user.login}")
    return jsonify({"user": user_payload(user)})


@api_bp.route("/logout", methods=["POST"])
def logout():
    log_audit("LOGOUT")
    session.clear()
    return jsonify({"message": "Déconnexion réussie"})


@api_bp.route("/me", methods=["GET"])
@login_required
def current_user():
    return jsonify({"user": user_payload(g.current_user)})


@api_bp.route("/settings", methods=["GET", "PUT"])
@login_required
def system_settings():
    setting = db.session.get(SystemSetting, "currency")
    if request.method == "GET":
        return jsonify({"currency": setting.value if setting else "TND"})
    if g.current_user.type != "admin":
        return jsonify({"error": "Accès réservé aux administrateurs."}), 403

    payload, error = request_data()
    if error:
        return error
    if set(payload) != {"currency"}:
        return jsonify({"error": "Seul le paramètre de devise peut être modifié."}), 400
    currency = payload.get("currency")
    if not isinstance(currency, str) or re.fullmatch(r"[A-Za-z]{3}", currency) is None:
        return jsonify({"error": "La devise doit être un code ISO de trois lettres."}), 400

    if setting is None:
        setting = SystemSetting(key="currency", value=currency.upper())
        db.session.add(setting)
    else:
        setting.value = currency.upper()
    db.session.commit()
    return jsonify({"message": "Paramètres enregistrés.", "currency": setting.value})


@api_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    users = User.query.order_by(User.id.asc()).all()
    return jsonify([user.to_dict() for user in users])


@api_bp.route("/employees", methods=["GET"])
@permission_required("empl")
def list_employees():
    users = User.query.order_by(User.id.asc()).all()
    return jsonify([user.to_dict() for user in users])


@api_bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    payload, error = request_data()
    if error:
        return error

    validation_error = validate_user_data(payload, creating=True)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    login_value = payload["login"].strip()
    if User.query.filter_by(login=login_value).first():
        return jsonify({"error": "Ce nom de connexion est déjà utilisé."}), 409

    user = User(
        nom=payload["nom"].strip(),
        prenom=payload["prenom"].strip(),
        login=login_value,
        pw=generate_password_hash(payload["password"]),
        type=payload["type"],
        lpp=int(payload.get("lpp", 8)),
        ville=payload.get("ville", "").strip(),
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Ce nom de connexion est déjà utilisé."}), 409

    return jsonify({"message": "Utilisateur créé.", "user": user.to_dict()}), 201


@api_bp.route("/users/<int:user_id>", methods=["PUT"])
@admin_required
def update_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    payload, error = request_data()
    if error:
        return error

    validation_error = validate_user_data(payload, creating=False)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    login_value = payload["login"].strip()
    duplicate = User.query.filter(User.login == login_value, User.id != user.id).first()
    if duplicate:
        return jsonify({"error": "Ce nom de connexion est déjà utilisé."}), 409

    if user.type == "admin" and payload["type"] != "admin":
        admin_count = User.query.filter_by(type="admin").count()
        if admin_count == 1:
            return jsonify({"error": "Impossible de retirer le rôle du dernier administrateur."}), 409

    user.nom = payload["nom"].strip()
    user.prenom = payload["prenom"].strip()
    user.login = login_value
    user.type = payload["type"]
    user.lpp = int(payload.get("lpp", user.lpp))
    user.ville = payload.get("ville", "").strip()
    if payload.get("password"):
        user.pw = generate_password_hash(payload["password"])

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Ce nom de connexion est déjà utilisé."}), 409

    return jsonify({"message": "Utilisateur modifié.", "user": user.to_dict()})


@api_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "Utilisateur introuvable."}), 404
    if user.id == g.current_user.id:
        return jsonify({"error": "Vous ne pouvez pas supprimer votre propre compte."}), 409
    if user.type == "admin" and User.query.filter_by(type="admin").count() == 1:
        return jsonify({"error": "Impossible de supprimer le dernier administrateur."}), 409

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Utilisateur supprimé."})


@api_bp.route("/seed", methods=["POST"])
def seed_admin():
    if current_app.config["APP_ENV"] == "production":
        return jsonify({"error": "La création initiale se fait depuis la console serveur."}), 404
    if User.query.first() is not None:
        return jsonify({"error": "Le compte initial existe déjà."}), 409

    admin = User(
        nom="Admin",
        prenom="System",
        login="admin",
        pw=generate_password_hash("admin123"),
        type="admin",
        lpp=8,
    )
    db.session.add(admin)
    db.session.commit()
    return jsonify({"message": "Compte administrateur initial créé."}), 201


@api_bp.route("/clients", methods=["GET"])
@permission_required(
    "client", "mouvement", "reception", "achat", "livraison", "vente"
)
def list_clients():
    query = Client.query
    search = request.args.get("search", "").strip()
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Client.nom.ilike(search_filter),
                Client.prenom.ilike(search_filter),
                Client.tel.ilike(search_filter),
                Client.email.ilike(search_filter),
                Client.ville.ilike(search_filter),
            )
        )
    sort = request.args.get("sort", "id")
    order = request.args.get("order", "asc")
    sort_col = getattr(Client, sort, Client.id)
    query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    pagination, items = paginate_query(query)
    if pagination is not None:
        return jsonify({
            "items": [client.to_dict() for client in items],
            **pagination,
        })
    return jsonify([client.to_dict() for client in query.all()])


@api_bp.route("/clients", methods=["POST"])
@permission_required("client")
def create_client():
    payload, error = request_data()
    if error:
        return error

    validation_error = validate_client_data(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    nom = payload["nom"].strip()
    prenom = payload["prenom"].strip()
    tel = payload["tel"].strip()
    duplicate = Client.query.filter_by(nom=nom, prenom=prenom, tel=tel).first()
    if duplicate:
        return jsonify({"error": "Ce client existe déjà (nom, prénom et téléphone identiques)."}), 409

    client = Client(
        nom=nom,
        prenom=prenom,
        tel=tel,
        email=payload["email"].strip(),
        specialite=payload.get("specialite", "").strip(),
        ville=payload.get("ville", "").strip(),
    )
    if payload.get("id") not in (None, ""):
        client.id = int(payload["id"])

    db.session.add(client)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Cet identifiant client est déjà utilisé."}), 409

    return jsonify({"message": "Client créé.", "client": client.to_dict()}), 201


@api_bp.route("/clients/<int:client_id>", methods=["PUT"])
@permission_required("client")
def update_client(client_id):
    client = db.session.get(Client, client_id)
    if client is None:
        return jsonify({"error": "Client introuvable."}), 404

    payload, error = request_data()
    if error:
        return error

    validation_error = validate_client_data(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    nom = payload["nom"].strip()
    prenom = payload["prenom"].strip()
    tel = payload["tel"].strip()
    duplicate = Client.query.filter(
        Client.nom == nom,
        Client.prenom == prenom,
        Client.tel == tel,
        Client.id != client.id,
    ).first()
    if duplicate:
        return jsonify({"error": "Ce client existe déjà (nom, prénom et téléphone identiques)."}), 409

    client.nom = nom
    client.prenom = prenom
    client.tel = tel
    client.email = payload["email"].strip()
    client.specialite = payload.get("specialite", "").strip()
    client.ville = payload.get("ville", "").strip()

    db.session.commit()
    return jsonify({"message": "Client modifié.", "client": client.to_dict()})


@api_bp.route("/clients/<int:client_id>", methods=["DELETE"])
@permission_required("client")
def delete_client(client_id):
    client = db.session.get(Client, client_id)
    if client is None:
        return jsonify({"error": "Client introuvable."}), 404
    if StockMovement.query.filter_by(id_client=client_id).first():
        return jsonify({"error": "Ce client est lié à des mouvements et ne peut pas être supprimé."}), 409

    log_audit('DELETE_CLIENT', f'client_id={client_id}')
    db.session.delete(client)
    db.session.commit()
    return jsonify({"message": "Client supprimé."})


@api_bp.route("/articles", methods=["GET"])
@permission_required(
    "article", "stand", "mouvement", "reception", "achat", "livraison", "vente"
)
def list_articles():
    query = Article.query
    search = request.args.get("search", "").strip()
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Article.ref.ilike(search_filter),
                Article.nom.ilike(search_filter),
                Article.famille.ilike(search_filter),
                Article.categorie.ilike(search_filter),
                Article.description.ilike(search_filter),
            )
        )
    sort = request.args.get("sort", "nom")
    order = request.args.get("order", "asc")
    sort_col = getattr(Article, sort, Article.nom)
    query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    pagination, items = paginate_query(query)
    if pagination is not None:
        return jsonify({
            "items": [article.to_dict() for article in items],
            **pagination,
        })
    return jsonify([article.to_dict() for article in query.all()])


@api_bp.route("/articles", methods=["POST"])
@permission_required("article")
def create_article():
    payload, error = request_data()
    if error:
        return error

    validation_error = validate_article_data(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    ref = payload["ref"].strip()
    if db.session.get(Article, ref) is not None:
        return jsonify({"error": "Cette référence d’article existe déjà."}), 409
    linked_product = PosProduct.query.filter_by(article_ref=ref).first()
    if linked_product:
        return jsonify({"error": "Cette référence est déjà associée à un produit POS."}), 409

    v_entrees = int(payload.get("v_entrees", 0))
    v_retour = int(payload.get("v_retour", 0))
    article = Article(
        ref=ref,
        famille=payload.get("famille", "").strip(),
        description=payload["description"].strip(),
        categorie=payload.get("categorie", "").strip(),
        nom=payload["nom"].strip(),
        v_entrees=v_entrees,
        v_retour=v_retour,
        v_stocks=v_entrees - v_retour,
        barcode=payload.get("barcode", "").strip() or None,
    )
    db.session.add(article)
    db.session.commit()
    return jsonify({"message": "Article créé.", "article": article.to_dict()}), 201


@api_bp.route("/articles/<string:ref>", methods=["PUT"])
@permission_required("article")
def update_article(ref):
    article = db.session.get(Article, ref)
    if article is None:
        return jsonify({"error": "Article introuvable."}), 404

    payload, error = request_data()
    if error:
        return error

    validation_error = validate_article_data(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    new_ref = payload["ref"].strip()
    duplicate = db.session.get(Article, new_ref)
    if duplicate is not None and duplicate.ref != article.ref:
        return jsonify({"error": "Cette référence d’article existe déjà."}), 409
    if new_ref != article.ref and (
        StockMovement.query.filter_by(article_ref=article.ref).first()
        or StandInventory.query.filter_by(ref_article=article.ref).first()
        or PosProduct.query.filter_by(article_ref=article.ref).first()
    ):
        return jsonify({"error": "La référence ne peut pas être modifiée car cet article est utilisé dans l’historique du stock, un stand ou la caisse POS."}), 409

    v_entrees = int(payload.get("v_entrees", 0))
    v_retour = int(payload.get("v_retour", 0))
    linked_product = PosProduct.query.filter_by(article_ref=article.ref).first()
    new_stock = v_entrees - v_retour
    if linked_product and new_stock < 0:
        return jsonify({"error": "Le stock POS associé ne peut pas devenir négatif."}), 409
    if linked_product and article.ref != new_ref:
        return jsonify({"error": "Dissociez d’abord le produit POS avant de modifier sa référence."}), 409
    if new_ref != article.ref:
        db.session.delete(article)
        db.session.flush()
        article = Article(ref=new_ref)
        db.session.add(article)

    article.famille = payload.get("famille", "").strip()
    article.description = payload["description"].strip()
    article.categorie = payload.get("categorie", "").strip()
    article.nom = payload["nom"].strip()
    article.v_entrees = v_entrees
    article.v_retour = v_retour
    article.v_stocks = v_entrees - v_retour
    article.barcode = payload.get("barcode", "").strip() or None
    if linked_product:
        if new_stock != linked_product.qty:
            db.session.add(
                PosStockMovement(
                    product_id=linked_product.product_id,
                    movement_type="adjustment",
                    quantity_delta=new_stock - linked_product.qty,
                    unit_cost=linked_product.o_price,
                    reference_type="product",
                    reference_id=linked_product.product_id,
                    recorded_by_id=g.current_user.id,
                )
            )
        linked_product.qty = new_stock
    db.session.commit()
    return jsonify({"message": "Article modifié.", "article": article.to_dict()})


@api_bp.route("/articles/<string:ref>", methods=["DELETE"])
@permission_required("article")
def delete_article(ref):
    article = db.session.get(Article, ref)
    if article is None:
        return jsonify({"error": "Article introuvable."}), 404
    if (
        StockMovement.query.filter_by(article_ref=ref).first()
        or StandInventory.query.filter_by(ref_article=ref).first()
        or PosProduct.query.filter_by(article_ref=ref).first()
    ):
        return jsonify({"error": "Cet article est utilisé dans l’historique du stock, un stand ou la caisse POS et ne peut pas être supprimé."}), 409

    db.session.delete(article)
    db.session.commit()
    return jsonify({"message": "Article supprimé."})


@api_bp.route("/suppliers", methods=["GET"])
@permission_required(
    "fournisseur", "mouvement", "achat", "reception", "livraison", "vente"
)
def list_suppliers():
    query = Supplier.query
    search = request.args.get("search", "").strip()
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Supplier.nom.ilike(search_filter),
                Supplier.prenom.ilike(search_filter),
                Supplier.tel.ilike(search_filter),
                Supplier.email.ilike(search_filter),
                Supplier.ville.ilike(search_filter),
            )
        )
    sort = request.args.get("sort", "nom")
    order = request.args.get("order", "asc")
    sort_col = getattr(Supplier, sort, Supplier.nom)
    query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    pagination, items = paginate_query(query)
    if pagination is not None:
        return jsonify({
            "items": [supplier.to_dict() for supplier in items],
            **pagination,
        })
    return jsonify([supplier.to_dict() for supplier in query.all()])


@api_bp.route("/suppliers", methods=["POST"])
@permission_required("fournisseur")
def create_supplier():
    payload, error = request_data()
    if error:
        return error
    validation_error = validate_supplier_data(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    supplier = Supplier(
        nom=payload["nom"].strip(),
        prenom=payload["prenom"].strip(),
        tel=payload["tel"].strip(),
        email=payload["email"].strip(),
        specialite=payload.get("specialite", "").strip(),
        ville=payload.get("ville", "").strip(),
    )
    db.session.add(supplier)
    db.session.commit()
    return jsonify({"message": "Fournisseur créé.", "fournisseur": supplier.to_dict()}), 201


@api_bp.route("/suppliers/<int:supplier_id>", methods=["PUT"])
@permission_required("fournisseur")
def update_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None:
        return jsonify({"error": "Fournisseur introuvable."}), 404
    payload, error = request_data()
    if error:
        return error
    validation_error = validate_supplier_data(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    supplier.nom = payload["nom"].strip()
    supplier.prenom = payload["prenom"].strip()
    supplier.tel = payload["tel"].strip()
    supplier.email = payload["email"].strip()
    supplier.specialite = payload.get("specialite", "").strip()
    supplier.ville = payload.get("ville", "").strip()
    db.session.commit()
    return jsonify({"message": "Fournisseur modifié.", "fournisseur": supplier.to_dict()})


@api_bp.route("/suppliers/<int:supplier_id>", methods=["DELETE"])
@permission_required("fournisseur")
def delete_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None:
        return jsonify({"error": "Fournisseur introuvable."}), 404
    if StockMovement.query.filter_by(id_fournisseur=supplier_id).first():
        return jsonify({"error": "Ce fournisseur est lié à des mouvements de stock et ne peut pas être supprimé."}), 409

    log_audit('DELETE_SUPPLIER', f'supplier_id={supplier_id}')
    db.session.delete(supplier)
    db.session.commit()
    return jsonify({"message": "Fournisseur supprimé."})


@api_bp.route("/stock/movements", methods=["GET"])
@permission_required("mouvement", "reception", "achat", "livraison", "vente")
def list_stock_movements():
    query = StockMovement.query.order_by(
        StockMovement.date_mouvement.desc(), StockMovement.id.desc()
    )
    m_type = request.args.get("type", "").strip()
    if m_type:
        query = query.filter(StockMovement.type == m_type)

    pagination, items = paginate_query(query)
    if pagination is not None:
        return jsonify({
            "items": [movement.to_dict() for movement in items],
            **pagination,
        })
    return jsonify([movement.to_dict() for movement in query.all()])


@api_bp.route("/stock/movements", methods=["POST"])
@stock_movement_permission_required
def create_stock_movement():
    payload, error = request_data()
    if error:
        return error
    validation_error = validate_movement_data(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    article = db.session.get(Article, payload["article_ref"].strip())
    quantity = int(payload["quantite"])
    if movement_delta(payload["type"], quantity) < 0 and quantity > article.v_stocks:
        return jsonify({"error": f"Stock insuffisant. Disponible : {article.v_stocks}."}), 409

    supplier_id = int(payload["id_fournisseur"]) if payload.get("id_fournisseur") else None
    client_id = int(payload["id_client"]) if payload.get("id_client") else None
    movement = StockMovement(
        type=payload["type"],
        article_ref=article.ref,
        quantite=quantity,
        date_mouvement=date.fromisoformat(payload["date_mouvement"]),
        id_fournisseur=supplier_id if payload["type"] in {"reception", "achat"} else None,
        id_client=client_id if payload["type"] in {"livraison", "vente"} else None,
    )
    if not apply_movement_delta(article, movement.type, quantity):
        db.session.rollback()
        return jsonify({
            "error": "Stock POS insuffisant pour appliquer ce mouvement à l’article associé."
        }), 409
    db.session.add(movement)
    db.session.commit()
    return jsonify({"message": "Mouvement de stock enregistré.", "mouvement": movement.to_dict()}), 201


@api_bp.route("/stock/movements/<int:movement_id>", methods=["PUT"])
@stock_movement_permission_required
def update_stock_movement(movement_id):
    movement = db.session.get(StockMovement, movement_id)
    if movement is None:
        return jsonify({"error": "Mouvement introuvable."}), 404
    payload, error = request_data()
    if error:
        return error
    validation_error = validate_movement_data(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    old_article = db.session.get(Article, movement.article_ref)
    new_article = db.session.get(Article, payload["article_ref"].strip())
    old_delta = movement_delta(movement.type, movement.quantite)
    new_delta = movement_delta(payload["type"], int(payload["quantite"]))
    if old_article.ref == new_article.ref:
        current_stock_without_old_movement = old_article.v_stocks - old_delta
        resulting_stock = current_stock_without_old_movement + new_delta
        if resulting_stock < 0:
            return jsonify({"error": f"Stock insuffisant après modification. Disponible : {current_stock_without_old_movement}."}), 409
        linked_product = PosProduct.query.filter_by(article_ref=old_article.ref).first()
        if linked_product and linked_product.qty - old_delta + new_delta < 0:
            return jsonify({"error": "Stock POS insuffisant après modification du mouvement."}), 409
    else:
        old_resulting_stock = old_article.v_stocks - old_delta
        new_resulting_stock = new_article.v_stocks + new_delta
        if old_resulting_stock < 0:
            return jsonify({"error": "Impossible de retirer ce mouvement : le stock a déjà été consommé."}), 409
        if new_resulting_stock < 0:
            return jsonify({"error": f"Stock insuffisant pour le nouvel article. Disponible : {new_article.v_stocks}."}), 409
        old_product = PosProduct.query.filter_by(article_ref=old_article.ref).first()
        new_product = PosProduct.query.filter_by(article_ref=new_article.ref).first()
        if old_product and old_product.qty - old_delta < 0:
            return jsonify({"error": "Impossible de retirer ce mouvement : le stock POS associé a déjà été consommé."}), 409
        if new_product and new_product.qty + new_delta < 0:
            return jsonify({"error": "Stock POS insuffisant pour le nouvel article."}), 409
        apply_article_stock_delta(old_article, -old_delta)
        if old_product:
            old_product.qty -= old_delta
        apply_article_stock_delta(new_article, new_delta)
        if new_product:
            new_product.qty += new_delta

    if old_article.ref == new_article.ref:
        apply_article_stock_delta(old_article, -old_delta)
        apply_article_stock_delta(old_article, new_delta)
        if not adjust_linked_pos_product(old_article, new_delta - old_delta):
            db.session.rollback()
            return jsonify({"error": "Stock POS insuffisant après modification du mouvement."}), 409

    movement.type = payload["type"]
    movement.article_ref = new_article.ref
    movement.quantite = int(payload["quantite"])
    movement.date_mouvement = date.fromisoformat(payload["date_mouvement"])
    movement.id_fournisseur = (
        int(payload["id_fournisseur"])
        if payload["type"] in {"reception", "achat"}
        else None
    )
    movement.id_client = (
        int(payload["id_client"])
        if payload["type"] in {"livraison", "vente"}
        else None
    )
    db.session.commit()
    return jsonify({"message": "Mouvement modifié.", "mouvement": movement.to_dict()})


@api_bp.route("/stock/movements/<int:movement_id>", methods=["DELETE"])
@stock_movement_permission_required
def delete_stock_movement(movement_id):
    movement = db.session.get(StockMovement, movement_id)
    if movement is None:
        return jsonify({"error": "Mouvement introuvable."}), 404

    article = db.session.get(Article, movement.article_ref)
    updated_stock = article.v_stocks - movement_delta(movement.type, movement.quantite)
    if updated_stock < 0:
        return jsonify({"error": "Impossible d’annuler ce mouvement : le stock a déjà été consommé."}), 409
    delta = movement_delta(movement.type, movement.quantite)
    linked_product = PosProduct.query.filter_by(article_ref=article.ref).first()
    if linked_product and linked_product.qty - delta < 0:
        return jsonify({"error": "Impossible d’annuler ce mouvement : le stock POS associé a déjà été consommé."}), 409
    apply_article_stock_delta(article, -delta)
    if linked_product:
        linked_product.qty -= delta
    db.session.delete(movement)
    db.session.commit()
    return jsonify({"message": "Mouvement annulé et stock recalculé."})


def register_resource_routes(resource_name, config):
    model = config["model"]
    resource_key = config.get("key", "id")
    resource_label = config["label"]
    permission = config.get("permission")
    write_access = (
        admin_required
        if config.get("admin_write")
        else permission_required(permission)
    )

    def list_resource():
        rows = model.query.order_by(getattr(model, resource_key).asc()).all()
        return jsonify([row.to_dict() for row in rows])

    list_resource.__name__ = f"list_{resource_name.replace('-', '_')}"
    api_bp.add_url_rule(
        f"/{resource_name}",
        endpoint=list_resource.__name__,
        view_func=permission_required(permission)(list_resource),
        methods=["GET"],
    )

    def create_resource():
        payload, error = request_data()
        if error:
            return error
        values, validation_error = validate_resource_payload(config, payload)
        if validation_error:
            return jsonify({"error": validation_error}), 400
        if resource_key != "id" and db.session.get(model, values[resource_key]) is not None:
            return jsonify({"error": f"{resource_label} déjà enregistré."}), 409

        team_assignments, assignment_error = prepare_fair_team(
            model, payload, values
        )
        if assignment_error:
            return jsonify({"error": assignment_error[0]}), assignment_error[1]

        row = model(**values)
        db.session.add(row)
        if model is Work or team_assignments:
            db.session.flush()
        if team_assignments:
            for role, user in team_assignments:
                db.session.add(
                    FairAssignment(
                        fair_id=row.id,
                        user_id=user.id,
                        role=role,
                        start_date=row.start_date,
                        end_date=row.end_date,
                        status="confirmed",
                        source="automatic",
                        created_by=g.current_user.id,
                        notes="Affectation automatique à la création de la foire.",
                    )
                )
        if model is Work:
            db.session.add(Confirmation(id=row.id))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": f"Impossible de créer ce {resource_label.lower()} : une référence est déjà utilisée ou invalide."}), 409
        response = {"message": f"{resource_label} créé.", "item": row.to_dict()}
        if model is Fair and team_assignments:
            response["message"] = (
                "Foire créée : vendeur, chauffeur et véhicule affectés automatiquement. "
                "Le contexte POS de la foire est prêt."
            )
            response["assignments"] = [
                assignment.to_dict()
                for assignment in FairAssignment.query.filter_by(
                    fair_id=row.id
                ).order_by(FairAssignment.id.asc()).all()
            ]
        return jsonify(response), 201

    create_resource.__name__ = f"create_{resource_name.replace('-', '_')}"
    api_bp.add_url_rule(
        f"/{resource_name}",
        endpoint=create_resource.__name__,
        view_func=write_access(create_resource),
        methods=["POST"],
    )

    def update_resource(resource_id):
        key = int(resource_id) if resource_key == "id" else resource_id
        row = db.session.get(model, key)
        if row is None:
            return jsonify({"error": f"{resource_label} introuvable."}), 404
        payload, error = request_data()
        if error:
            return error
        values, validation_error = validate_resource_payload(config, payload)
        if validation_error:
            return jsonify({"error": validation_error}), 400
        if resource_key != "id" and values.get(resource_key) != key:
            return jsonify({"error": "La clé principale ne peut pas être modifiée."}), 400
        for field, value in values.items():
            setattr(row, field, value)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": f"Impossible de modifier ce {resource_label.lower()} : une référence est invalide."}), 409
        return jsonify({"message": f"{resource_label} modifié.", "item": row.to_dict()})

    update_resource.__name__ = f"update_{resource_name.replace('-', '_')}"
    api_bp.add_url_rule(
        f"/{resource_name}/<resource_id>",
        endpoint=update_resource.__name__,
        view_func=write_access(update_resource),
        methods=["PUT"],
    )

    def delete_resource(resource_id):
        key = int(resource_id) if resource_key == "id" else resource_id
        row = db.session.get(model, key)
        if row is None:
            return jsonify({"error": f"{resource_label} introuvable."}), 404
        if model is Work:
            confirmation = db.session.get(Confirmation, row.id)
            if confirmation is not None:
                db.session.delete(confirmation)
        db.session.delete(row)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": f"Impossible de supprimer ce {resource_label.lower()} car il est utilisé ailleurs."}), 409
        return jsonify({"message": f"{resource_label} supprimé."})

    delete_resource.__name__ = f"delete_{resource_name.replace('-', '_')}"
    api_bp.add_url_rule(
        f"/{resource_name}/<resource_id>",
        endpoint=delete_resource.__name__,
        view_func=write_access(delete_resource),
        methods=["DELETE"],
    )


for resource_name, resource_config in RESOURCE_CONFIG.items():
    register_resource_routes(resource_name, resource_config)


FAIR_ASSIGNMENT_ROLES = {
    "vendeur",
    "deco",
    "chauffeur",
    "chef",
    "reservation",
    "laga",
    "compta",
}


def fair_assignment_conflict(user_id, start_date, end_date):
    assignment = FairAssignment.query.filter(
        FairAssignment.user_id == user_id,
        FairAssignment.status == "confirmed",
        FairAssignment.start_date <= end_date,
        FairAssignment.end_date >= start_date,
    ).first()
    if assignment:
        return f"Déjà affecté à {assignment.fair.nom} du {assignment.start_date} au {assignment.end_date}."

    reservation = Reservation.query.filter(
        Reservation.id_agent == user_id,
        Reservation.date_d <= end_date.isoformat(),
        Reservation.date_f >= start_date.isoformat(),
    ).first()
    if reservation:
        return f"Réservation existante pour {reservation.foire.nom} du {reservation.date_d} au {reservation.date_f}."

    work = Work.query.filter(
        or_(
            Work.id_vendeur == user_id,
            Work.id_deco == user_id,
            Work.id_chauffeur == user_id,
        ),
        Work.date_d <= end_date.isoformat(),
        Work.date_f >= start_date.isoformat(),
    ).first()
    if work:
        return f"Mission existante pour {work.foire.nom} du {work.date_d} au {work.date_f}."
    return None


def fair_vehicle_conflict(vehicle, start_date, end_date):
    if vehicle.location and vehicle.date_d_loc and vehicle.date_f_loc:
        if (
            vehicle.date_d_loc <= end_date.isoformat()
            and vehicle.date_f_loc >= start_date.isoformat()
        ):
            return f"Le véhicule {vehicle.immatricule} est loué sur cette période."

    fair = Fair.query.filter(
        Fair.assigned_vehicle_id == vehicle.id,
        Fair.start_date <= end_date,
        Fair.end_date >= start_date,
    ).first()
    if fair:
        return f"Le véhicule {vehicle.immatricule} est déjà affecté à {fair.nom}."

    work = Work.query.filter(
        Work.id_voiture == vehicle.id,
        Work.date_d <= end_date.isoformat(),
        Work.date_f >= start_date.isoformat(),
    ).first()
    if work:
        return f"Le véhicule {vehicle.immatricule} est déjà utilisé pour la mission de {work.foire.nom}."
    return None


def parse_assignment_dates(payload):
    try:
        start_date = date.fromisoformat(payload.get("start_date", ""))
        end_date = date.fromisoformat(payload.get("end_date", ""))
    except (TypeError, ValueError):
        return None, None, "Les dates doivent être au format AAAA-MM-JJ."
    if end_date < start_date:
        return None, None, "La date de fin doit être postérieure ou égale à la date de début."
    return start_date, end_date, None


@api_bp.route("/fair-assignments", methods=["GET", "POST"])
@permission_required("foire")
def fair_assignments():
    if request.method == "GET":
        assignments = FairAssignment.query.order_by(
            FairAssignment.start_date, FairAssignment.id
        ).all()
        return jsonify([assignment.to_dict() for assignment in assignments])

    payload, error = request_data()
    if error:
        return error
    try:
        fair_id = int(payload.get("fair_id"))
        user_id = int(payload.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "La foire et l’utilisateur sont obligatoires."}), 400
    role = payload.get("role")
    if not isinstance(role, str) or role not in FAIR_ASSIGNMENT_ROLES:
        return jsonify({"error": "Le rôle d’affectation est invalide."}), 400
    if not isinstance(payload.get("notes", ""), str) or len(payload.get("notes", "")) > 500:
        return jsonify({"error": "Les notes ne doivent pas dépasser 500 caractères."}), 400

    fair = db.session.get(Fair, fair_id)
    user = db.session.get(User, user_id)
    if fair is None or user is None:
        return jsonify({"error": "Foire ou utilisateur introuvable."}), 404
    if user.type != role:
        return jsonify({"error": "Le rôle ne correspond pas au profil de l’utilisateur."}), 400

    start_date, end_date, date_error = parse_assignment_dates(payload)
    if date_error:
        return jsonify({"error": date_error}), 400
    if fair.start_date and start_date < fair.start_date:
        return jsonify({"error": "L’affectation ne peut pas commencer avant la foire."}), 400
    if fair.end_date and end_date > fair.end_date:
        return jsonify({"error": "L’affectation ne peut pas se terminer après la foire."}), 400

    conflict = fair_assignment_conflict(user.id, start_date, end_date)
    if conflict:
        return jsonify({"error": f"Conflit de disponibilité : {conflict}"}), 409

    assignment = FairAssignment(
        fair_id=fair.id,
        user_id=user.id,
        role=role,
        start_date=start_date,
        end_date=end_date,
        status="confirmed",
        source="manual",
        created_by=g.current_user.id,
        notes=payload.get("notes", "").strip() or None,
    )
    db.session.add(assignment)
    db.session.commit()
    return jsonify({"message": "Affectation enregistrée.", "item": assignment.to_dict()}), 201


@api_bp.route("/fair-assignments/suggestions", methods=["POST"])
@permission_required("foire")
def suggest_fair_assignments():
    payload, error = request_data()
    if error:
        return error
    try:
        fair_id = int(payload.get("fair_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "La foire est obligatoire."}), 400
    fair = db.session.get(Fair, fair_id)
    if fair is None:
        return jsonify({"error": "Foire introuvable."}), 404

    role = payload.get("role")
    if not isinstance(role, str) or role not in FAIR_ASSIGNMENT_ROLES:
        return jsonify({"error": "Le rôle d’affectation est invalide."}), 400
    start_date, end_date, date_error = parse_assignment_dates(payload)
    if date_error:
        return jsonify({"error": date_error}), 400
    if fair.start_date and start_date < fair.start_date:
        return jsonify({"error": "La période proposée commence avant la foire."}), 400
    if fair.end_date and end_date > fair.end_date:
        return jsonify({"error": "La période proposée se termine après la foire."}), 400

    suggestions = []
    for user in User.query.filter_by(type=role).order_by(User.prenom, User.nom).all():
        conflict = fair_assignment_conflict(user.id, start_date, end_date)
        suggestions.append({
            "user_id": user.id,
            "user_name": f"{user.prenom} {user.nom}".strip(),
            "role": role,
            "available": conflict is None,
            "conflict": conflict,
        })
    return jsonify({
        "fair_id": fair.id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "suggestions": suggestions,
    })


@api_bp.route("/fair-assignments/<int:assignment_id>", methods=["DELETE"])
@permission_required("foire")
def delete_fair_assignment(assignment_id):
    assignment = db.session.get(FairAssignment, assignment_id)
    if assignment is None:
        return jsonify({"error": "Affectation introuvable."}), 404
    db.session.delete(assignment)
    db.session.commit()
    return jsonify({"message": "Affectation supprimée."})


FAIR_INVENTORY_TYPES = {
    "transfer_in",
    "transfer_out",
    "receipt",
    "sale",
    "return",
    "damage",
}


def fair_inventory_payload(payload):
    movement_type = payload.get("movement_type")
    if not isinstance(movement_type, str) or movement_type not in FAIR_INVENTORY_TYPES:
        return None, "Le type de mouvement est invalide."
    article_ref = payload.get("article_ref")
    if not isinstance(article_ref, str) or not article_ref.strip():
        return None, "Un article doit être sélectionné."
    quantity = payload.get("quantity")
    if isinstance(quantity, bool) or not (
        isinstance(quantity, int)
        or isinstance(quantity, str) and quantity.isdecimal()
    ):
        return None, "La quantité doit être un entier strictement positif."
    quantity = int(quantity)
    if quantity <= 0:
        return None, "La quantité doit être un entier strictement positif."
    reference = payload.get("reference", "")
    notes = payload.get("notes", "")
    movement_date = payload.get("movement_date")
    if not isinstance(reference, str) or len(reference.strip()) > 120:
        return None, "La référence ne doit pas dépasser 120 caractères."
    if not isinstance(notes, str) or len(notes.strip()) > 500:
        return None, "Les notes ne doivent pas dépasser 500 caractères."
    try:
        movement_date = date.fromisoformat(movement_date)
    except (TypeError, ValueError):
        return None, "La date doit être au format AAAA-MM-JJ."

    return {
        "movement_type": movement_type,
        "article_ref": article_ref.strip(),
        "quantity": quantity,
        "movement_date": movement_date,
        "reference": reference.strip() or None,
        "notes": notes.strip() or None,
    }, None


def change_fair_inventory_balance(fair_id, article_ref, delta):
    db.session.execute(
        text(
            "INSERT INTO fair_inventory (fair_id, article_ref, quantity) "
            "VALUES (:fair_id, :article_ref, 0) "
            "ON CONFLICT (fair_id, article_ref) DO NOTHING"
        ),
        {"fair_id": fair_id, "article_ref": article_ref},
    )
    result = db.session.execute(
        update(FairInventoryBalance)
        .where(
            FairInventoryBalance.fair_id == fair_id,
            FairInventoryBalance.article_ref == article_ref,
            FairInventoryBalance.quantity + delta >= 0,
        )
        .values(quantity=FairInventoryBalance.quantity + delta)
    )
    return result.rowcount == 1


def change_general_inventory(
    article_ref, expected_stock, delta, actor_id, movement_id, movement_date
):
    article_update = update(Article).where(
        Article.ref == article_ref,
        Article.v_stocks == expected_stock,
    )
    if delta < 0:
        quantity = -delta
        article_update = article_update.where(Article.v_stocks >= quantity).values(
            v_stocks=Article.v_stocks - quantity,
            v_retour=Article.v_retour + quantity,
        )
        central_type = "livraison"
        central_quantity = quantity
    else:
        quantity = delta
        article_update = article_update.values(
            v_stocks=Article.v_stocks + quantity,
            v_entrees=Article.v_entrees + quantity,
        )
        central_type = "reception"
        central_quantity = quantity
    if db.session.execute(article_update).rowcount != 1:
        return False, "Le stock général est insuffisant ou l’article a changé."

    product = PosProduct.query.filter_by(article_ref=article_ref).first()
    if product is not None:
        if product.qty != expected_stock:
            return False, "Le stock général et le stock POS lié ne sont pas synchronisés."
        product_update = update(PosProduct).where(
            PosProduct.product_id == product.product_id,
            PosProduct.qty == expected_stock,
        )
        if delta < 0:
            product_update = product_update.where(PosProduct.qty >= quantity).values(
                qty=PosProduct.qty - quantity,
            )
        else:
            product_update = product_update.values(qty=PosProduct.qty + quantity)
        if db.session.execute(product_update).rowcount != 1:
            return False, "Le stock POS associé est insuffisant ou a changé."
        db.session.add(
            PosStockMovement(
                product_id=product.product_id,
                movement_type="adjustment",
                quantity_delta=delta,
                unit_cost=product.o_price,
                reference_type="fair_transfer",
                reference_id=movement_id,
                recorded_by_id=actor_id,
            )
        )

    db.session.add(
        StockMovement(
            type=central_type,
            article_ref=article_ref,
            quantite=central_quantity,
            date_mouvement=movement_date,
        )
    )
    return True, None


@api_bp.route("/fairs/<int:fair_id>/inventory", methods=["GET"])
@permission_required("foire")
def list_fair_inventory(fair_id):
    fair = db.session.get(Fair, fair_id)
    if fair is None:
        return jsonify({"error": "Foire introuvable."}), 404
    balances = (
        FairInventoryBalance.query.filter_by(fair_id=fair_id)
        .filter(FairInventoryBalance.quantity > 0)
        .order_by(FairInventoryBalance.article_ref.asc())
        .all()
    )
    movements = (
        FairInventoryMovement.query.filter_by(fair_id=fair_id)
        .order_by(FairInventoryMovement.movement_date.desc(), FairInventoryMovement.id.desc())
        .limit(100)
        .all()
    )
    return jsonify({
        "fair": fair.to_dict(),
        "catalog": [
            {
                "ref": article.ref,
                "nom": article.nom,
                "v_stocks": article.v_stocks,
            }
            for article in Article.query.order_by(Article.ref.asc()).all()
        ],
        "inventory": [
            {
                "article_ref": balance.article_ref,
                "article_name": balance.article.nom if balance.article else "",
                "quantity": balance.quantity,
            }
            for balance in balances
        ],
        "movements": [movement.to_dict() for movement in movements],
    })


@api_bp.route("/fairs/<int:fair_id>/inventory/movements", methods=["POST"])
@permission_required("foire")
def create_fair_inventory_movement(fair_id):
    if db.engine.dialect.name == "sqlite":
        db.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    fair = db.session.get(Fair, fair_id)
    if fair is None:
        return jsonify({"error": "Foire introuvable."}), 404
    payload, error = request_data()
    if error:
        return error
    values, validation_error = fair_inventory_payload(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400
    article = db.session.get(Article, values["article_ref"])
    if article is None:
        return jsonify({"error": "Article introuvable."}), 404
    general_stock_before = article.v_stocks

    quantity = values["quantity"]
    quantity_delta = quantity if values["movement_type"] in {
        "transfer_in", "receipt", "return"
    } else -quantity
    if not change_fair_inventory_balance(fair.id, article.ref, quantity_delta):
        db.session.rollback()
        return jsonify({"error": "Stock du stand insuffisant pour ce mouvement."}), 409

    movement = FairInventoryMovement(
        fair_id=fair.id,
        article_ref=article.ref,
        movement_type=values["movement_type"],
        quantity_delta=quantity_delta,
        movement_date=values["movement_date"],
        reference=values["reference"],
        notes=values["notes"],
        created_by=g.current_user.id,
    )
    db.session.add(movement)
    db.session.flush()

    if values["movement_type"] in {"transfer_in", "transfer_out"}:
        central_delta = -quantity if values["movement_type"] == "transfer_in" else quantity
        success, stock_error = change_general_inventory(
            article.ref,
            general_stock_before,
            central_delta,
            g.current_user.id,
            movement.id,
            values["movement_date"],
        )
        if not success:
            db.session.rollback()
            return jsonify({"error": stock_error}), 409

    db.session.commit()
    return jsonify({
        "message": "Mouvement de stock enregistré.",
        "item": movement.to_dict(),
        "balance": FairInventoryBalance.query.filter_by(
            fair_id=fair.id, article_ref=article.ref
        ).first().quantity,
    }), 201



@api_bp.route("/pos/scan/<path:code>", methods=["GET"])
@permission_required("vente")
def pos_scan_barcode(code):
    scanned = code.strip()
    if not scanned:
        return jsonify({"error": "Code-barres vide."}), 400

    # Recherche par code-barres, code produit ou référence article
    product = PosProduct.query.filter(
        or_(
            PosProduct.barcode == scanned,
            PosProduct.product_code == scanned,
            PosProduct.article_ref == scanned,
        )
    ).first()

    if not product:
        # Recherche insensible à la casse
        product = PosProduct.query.filter(
            or_(
                func.lower(PosProduct.barcode) == scanned.lower(),
                func.lower(PosProduct.product_code) == scanned.lower(),
                func.lower(PosProduct.article_ref) == scanned.lower(),
            )
        ).first()

    if not product:
        return jsonify({"error": f"Aucun produit trouvé pour le code-barres « {scanned} ».", "found": False}), 404

    return jsonify({"product": product.to_dict(), "found": True})


@api_bp.route("/pos/products", methods=["GET"])
@permission_required("article", "vente")
def list_pos_products():
    query = PosProduct.query
    search = request.args.get("search", "").strip()
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                PosProduct.product_code.ilike(search_filter),
                PosProduct.gen_name.ilike(search_filter),
            )
        )
    query = query.order_by(PosProduct.product_code.asc())
    include_cost = g.current_user.type == "admin"

    pagination, items = paginate_query(query)
    if pagination is not None:
        return jsonify({
            "items": [product.to_dict(include_cost=include_cost) for product in items],
            **pagination,
        })
    return jsonify([
        product.to_dict(include_cost=include_cost) for product in query.all()
    ])


@api_bp.route("/pos/products", methods=["POST"])
@permission_required("article")
def create_pos_product():
    payload, error = request_data()
    if error:
        return error
    values, validation_error = validate_pos_product(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400
    article = db.session.get(Article, values["article_ref"]) if values["article_ref"] else None
    if values["article_ref"] and article is None:
        return jsonify({"error": "L’article associé est introuvable."}), 404
    if article:
        if values["qty"] != article.v_stocks:
            return jsonify({
                "error": f"Le stock initial doit correspondre au stock de l’article ({article.v_stocks})."
            }), 409
        values["product_code"] = article.ref
        values["gen_name"] = article.nom
    values["article_ref"] = article.ref if article else None
    if PosProduct.query.filter_by(product_code=values["product_code"]).first():
        return jsonify({"error": "Ce code produit est déjà utilisé."}), 409

    values["qty_sold"] = 0
    if not values.get("barcode") and article and getattr(article, 'barcode', None):
        values["barcode"] = article.barcode
    product = PosProduct(**values)
    db.session.add(product)
    try:
        db.session.flush()
        if product.qty:
            db.session.add(
                PosStockMovement(
                    product=product,
                    movement_type="opening",
                    quantity_delta=product.qty,
                    unit_cost=product.o_price,
                    reference_type="product",
                    reference_id=product.product_id,
                    recorded_by_id=g.current_user.id,
                )
            )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Ce code produit est déjà utilisé."}), 409
    return jsonify({"message": "Produit créé.", "item": product.to_dict()}), 201


@api_bp.route("/pos/products/import-articles", methods=["POST"])
@admin_required
def import_pos_products_from_articles():
    if db.engine.dialect.name == "sqlite":
        db.session.rollback()
        db.session.connection().exec_driver_sql("BEGIN IMMEDIATE")

    articles = Article.query.order_by(Article.ref.asc()).all()
    linked_refs = {
        article_ref
        for (article_ref,) in db.session.query(PosProduct.article_ref)
        .filter(PosProduct.article_ref.isnot(None))
        .all()
    }
    articles_to_import = [
        article for article in articles if article.ref not in linked_refs
    ]
    if any(article.v_stocks < 0 for article in articles_to_import):
        db.session.rollback()
        return jsonify({
            "error": "Import annulé : un article non associé a un stock négatif."
        }), 409

    existing_codes = {
        product_code
        for (product_code,) in db.session.query(PosProduct.product_code).all()
    }
    conflicting_refs = [
        article.ref
        for article in articles_to_import
        if article.ref in existing_codes
    ]
    if conflicting_refs:
        db.session.rollback()
        return jsonify({
            "error": (
                "Import annulé : certains codes article sont déjà utilisés par "
                f"des produits POS non liés ({', '.join(conflicting_refs[:5])})."
            )
        }), 409

    imported_products = []
    try:
        for article in articles_to_import:
            product = PosProduct(
                article_ref=article.ref,
                product_code=article.ref,
                gen_name=article.nom,
                product_name=article.description or "",
                supplier="",
                date_arrival="",
                expiry_date="",
                price=Decimal("0.00"),
                o_price=Decimal("0.00"),
                pricing_configured=False,
                qty=article.v_stocks,
                qty_sold=0,
            )
            db.session.add(product)
            db.session.flush()
            if product.qty:
                db.session.add(
                    PosStockMovement(
                        product=product,
                        movement_type="opening",
                        quantity_delta=product.qty,
                        unit_cost=Decimal("0.00"),
                        reference_type="product",
                        reference_id=product.product_id,
                        recorded_by_id=g.current_user.id,
                    )
                )
            imported_products.append(product)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "L’import a été annulé : un article ou code produit est déjà associé."
        }), 409

    count = len(imported_products)
    return jsonify({
        "message": (
            f"{count} produit(s) POS créé(s) depuis les articles."
            if count
            else "Tous les articles sont déjà associés à un produit POS."
        ),
        "created_count": count,
        "products": [product.to_dict() for product in imported_products],
    })


@api_bp.route("/pos/products/<int:product_id>", methods=["PUT"])
@permission_required("article")
def update_pos_product(product_id):
    product = db.session.get(PosProduct, product_id)
    if product is None:
        return jsonify({"error": "Produit introuvable."}), 404
    payload, error = request_data()
    if error:
        return error
    values, validation_error = validate_pos_product(payload)
    if validation_error:
        return jsonify({"error": validation_error}), 400
    if "pricing_configured" not in payload:
        values["pricing_configured"] = product.pricing_configured
    new_article = (
        db.session.get(Article, values["article_ref"])
        if values["article_ref"]
        else None
    )
    if values["article_ref"] and new_article is None:
        return jsonify({"error": "L’article associé est introuvable."}), 404
    values["article_ref"] = new_article.ref if new_article else None
    old_article = product.article
    if product.article_ref and values["article_ref"] != product.article_ref:
        return jsonify({
            "error": "L’association à un article ne peut pas être changée après sa création."
        }), 409
    if new_article:
        values["product_code"] = new_article.ref
        values["gen_name"] = new_article.nom
        if new_article.ref != product.article_ref and values["qty"] != new_article.v_stocks:
            return jsonify({
                "error": f"Pour associer cet article, le stock POS doit correspondre à son stock ({new_article.v_stocks})."
            }), 409
        if new_article.ref == product.article_ref and product.qty != new_article.v_stocks:
            return jsonify({
                "error": "Le stock POS ne correspond plus au stock général. Corrigez le stock de l’article avant de modifier ce produit."
            }), 409
    duplicate = PosProduct.query.filter(
        PosProduct.product_code == values["product_code"],
        PosProduct.product_id != product.product_id,
    ).first()
    if duplicate:
        return jsonify({"error": "Ce code produit est déjà utilisé."}), 409
    duplicate_article = PosProduct.query.filter(
        PosProduct.article_ref == values["article_ref"],
        PosProduct.product_id != product.product_id,
    ).first() if values["article_ref"] else None
    if duplicate_article:
        return jsonify({"error": "Cet article est déjà associé à un autre produit POS."}), 409
    old_article_ref = product.article_ref
    quantity_delta = values["qty"] - product.qty
    if new_article and new_article.ref == old_article_ref and new_article.v_stocks + quantity_delta < 0:
        return jsonify({"error": "Le stock de l’article associé ne peut pas devenir négatif."}), 409
    values["qty_sold"] = product.qty_sold
    for field, value in values.items():
        setattr(product, field, value)
    try:
        if quantity_delta:
            if new_article and new_article.ref == old_article_ref:
                apply_article_stock_delta(new_article, quantity_delta)
            db.session.add(
                PosStockMovement(
                    product=product,
                    movement_type="adjustment",
                    quantity_delta=quantity_delta,
                    unit_cost=values["o_price"],
                    reference_type="product",
                    reference_id=product.product_id,
                    recorded_by_id=g.current_user.id,
                )
            )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Ce code produit est déjà utilisé."}), 409
    return jsonify({"message": "Produit modifié.", "item": product.to_dict()})


@api_bp.route("/pos/products/<int:product_id>", methods=["DELETE"])
@permission_required("article")
def delete_pos_product(product_id):
    product = db.session.get(PosProduct, product_id)
    if product is None:
        return jsonify({"error": "Produit introuvable."}), 404
    if (
        PosSaleItem.query.filter_by(product_id=product_id).first()
        or PosPurchaseItem.query.filter_by(product_id=product_id).first()
        or PosStockMovement.query.filter_by(product_id=product_id).first()
    ):
        return jsonify({
            "error": "Ce produit figure dans l’historique des ventes, achats ou mouvements de stock et ne peut pas être supprimé."
        }), 409
    db.session.delete(product)
    db.session.commit()
    return jsonify({"message": "Produit supprimé."})


@api_bp.route("/pos/purchases", methods=["GET"])
@permission_required("achat")
def list_pos_purchases():
    purchases = PosPurchase.query.order_by(
        PosPurchase.date.desc(), PosPurchase.purchase_id.desc()
    ).all()
    return jsonify([purchase.to_dict() for purchase in purchases])


@api_bp.route("/pos/purchases/<int:purchase_id>", methods=["GET"])
@permission_required("achat")
def get_pos_purchase(purchase_id):
    purchase = db.session.get(PosPurchase, purchase_id)
    if purchase is None:
        return jsonify({"error": "Achat introuvable."}), 404
    return jsonify(purchase.to_dict(include_items=True))


@api_bp.route("/pos/purchases", methods=["POST"])
@permission_required("achat")
def create_pos_purchase():
    payload, error = request_data()
    if error:
        return error

    invoice_number = payload.get("invoice_number")
    supplier = payload.get("supplier")
    remarks = payload.get("remarks", "")
    if not isinstance(invoice_number, str) or not invoice_number.strip() or len(invoice_number.strip()) > 120:
        return jsonify({"error": "Un numéro de facture valide est obligatoire (120 caractères maximum)."}), 400
    invoice_number = invoice_number.strip()
    if PosPurchase.query.filter_by(invoice_number=invoice_number).first():
        return jsonify({"error": "Ce numéro de facture est déjà utilisé."}), 409
    if not isinstance(supplier, str) or not supplier.strip() or len(supplier.strip()) > 160:
        return jsonify({"error": "Un fournisseur valide est obligatoire."}), 400
    if not isinstance(remarks, str) or len(remarks.strip()) > 500:
        return jsonify({"error": "Les remarques ne doivent pas dépasser 500 caractères."}), 400
    try:
        purchase_date = date.fromisoformat(payload.get("date", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "La date d’achat doit être au format AAAA-MM-JJ."}), 400

    lines = payload.get("items")
    if not isinstance(lines, list) or not lines or len(lines) > 100:
        return jsonify({"error": "L’achat doit contenir entre 1 et 100 produits."}), 400
    quantities = {}
    unit_costs = {}
    for line in lines:
        if not isinstance(line, dict):
            return jsonify({"error": "Une ligne d’achat est invalide."}), 400
        try:
            product_id = int(line.get("product_id"))
            quantity = int(line.get("qty"))
            unit_cost = Decimal(str(line.get("unit_cost"))).quantize(
                MONEY_QUANTUM, rounding=ROUND_HALF_UP
            )
        except (InvalidOperation, TypeError, ValueError):
            return jsonify({"error": "Produit, quantité ou coût unitaire invalide."}), 400
        if (
            product_id < 1
            or quantity < 1
            or not unit_cost.is_finite()
            or unit_cost < 0
            or str(product_id) != str(line.get("product_id"))
            or str(quantity) != str(line.get("qty"))
        ):
            return jsonify({"error": "Les produits, quantités et coûts doivent être valides."}), 400
        if product_id in quantities:
            return jsonify({"error": "Chaque produit ne peut figurer qu’une seule fois dans un achat."}), 400
        quantities[product_id] = quantity
        unit_costs[product_id] = unit_cost

    products = {
        product.product_id: product
        for product in PosProduct.query.filter(
            PosProduct.product_id.in_(quantities)
        ).all()
    }
    if len(products) != len(quantities):
        return jsonify({"error": "Un produit de l’achat est introuvable."}), 404

    total = sum(
        unit_costs[product_id] * quantity
        for product_id, quantity in quantities.items()
    ).quantize(MONEY_QUANTUM)
    purchase = PosPurchase(
        invoice_number=invoice_number,
        date=purchase_date,
        supplier=supplier.strip(),
        supplier_record=get_or_create_pos_contact(PosSupplier, supplier.strip()),
        remarks=remarks.strip(),
        total=total,
    )
    db.session.add(purchase)
    try:
        db.session.flush()
        for product_id, quantity in quantities.items():
            product = products[product_id]
            unit_cost = unit_costs[product_id]
            total_cost = (unit_cost * quantity).quantize(MONEY_QUANTUM)
            db.session.add(
                PosPurchaseItem(
                    purchase_id=purchase.purchase_id,
                    product_id=product_id,
                    product_code=product.product_code,
                    gen_name=product.gen_name,
                    qty=quantity,
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                )
            )
            db.session.add(
                PosStockMovement(
                    product_id=product_id,
                    movement_type="purchase",
                    quantity_delta=quantity,
                    unit_cost=unit_cost,
                    reference_type="purchase",
                    reference_id=purchase.purchase_id,
                    recorded_by_id=g.current_user.id,
                )
            )
            stock_update = db.session.execute(
                update(PosProduct)
                .where(PosProduct.product_id == product_id)
                .values(
                    qty=PosProduct.qty + quantity,
                    o_price=(
                        PosProduct.qty * PosProduct.o_price
                        + unit_cost * quantity
                    ) / (PosProduct.qty + quantity),
                )
            )
            if stock_update.rowcount != 1:
                db.session.rollback()
                return jsonify({"error": "Le stock d’un produit n’a pas pu être mis à jour."}), 409
            if product.article:
                apply_article_stock_delta(product.article, quantity)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "L’achat n’a pas pu être enregistré."}), 409

    return jsonify({
        "message": "Achat enregistré et stock mis à jour.",
        "purchase": purchase.to_dict(include_items=True),
    }), 201


@api_bp.route("/pos/sales", methods=["GET"])
@permission_required("vente")
def list_pos_sales():
    query = scope_pos_sales(PosSale.query)
    query, filter_error = apply_pos_sale_context_filters(query)
    if filter_error:
        return jsonify({"error": filter_error}), 400
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    try:
        if start_date:
            query = query.filter(PosSale.date >= date.fromisoformat(start_date))
        if end_date:
            query = query.filter(PosSale.date <= date.fromisoformat(end_date))
    except ValueError:
        return jsonify({"error": "Les dates doivent être au format AAAA-MM-JJ."}), 400
    query = query.order_by(PosSale.date.desc(), PosSale.transaction_id.desc())
    include_profit = g.current_user.type == "admin"

    pagination, items = paginate_query(query)
    if pagination is not None:
        return jsonify({
            "items": [sale.to_dict(include_profit=include_profit) for sale in items],
            **pagination,
        })
    return jsonify([
        sale.to_dict(include_profit=include_profit) for sale in query.all()
    ])


def apply_pos_sale_context_filters(query):
    filters = (
        ("fair_id", PosSale.fair_id, "La foire doit être un identifiant entier."),
        ("seller_id", PosSale.seller_id, "Le vendeur doit être un identifiant entier."),
    )
    for parameter, column, error_message in filters:
        raw_value = request.args.get(parameter)
        if raw_value is None:
            continue
        try:
            identifier = int(raw_value)
        except (TypeError, ValueError):
            return query, error_message
        if identifier < 1 or str(identifier) != raw_value:
            return query, error_message
        query = query.filter(column == identifier)
    return query, None


def scope_pos_sales(query):
    if g.current_user.type != "admin":
        owner_column = (
            PosSale.seller_id
            if g.current_user.type == "vendeur"
            else PosSale.cashier_user_id
        )
        query = query.filter(owner_column == g.current_user.id)
    return query


def pos_sale_is_visible(sale):
    if g.current_user.type == "admin":
        return True
    if g.current_user.type == "vendeur":
        return sale.seller_id == g.current_user.id
    return sale.cashier_user_id == g.current_user.id


@api_bp.route("/pos/fair-contexts", methods=["GET"])
@permission_required("vente")
def list_pos_fair_contexts():
    today = date.today()
    # Récupérer les affectations de vendeurs pour les foires actives ou à venir
    query = (
        FairAssignment.query.join(Fair, FairAssignment.fair_id == Fair.id)
        .join(User, FairAssignment.user_id == User.id)
        .filter(
            FairAssignment.role == "vendeur",
            FairAssignment.status == "confirmed",
            User.type == "vendeur",
            or_(Fair.status.is_(None), Fair.status.notin_(("cancelled", "completed"))),
            *(
                [FairAssignment.user_id == g.current_user.id]
                if g.current_user.type == "vendeur"
                else []
            ),
        )
    )
    # Pour un vendeur ordinaire en exploitation stricte, vérifier la date sauf si admin ou foire active
    if g.current_user.type != "admin":
        query = query.filter(
            or_(
                Fair.status == "active",
                (FairAssignment.start_date <= today) & (FairAssignment.end_date >= today)
            )
        )
    assignments = query.order_by(Fair.start_date, Fair.nom, User.prenom, User.nom).all()

    contexts = {}
    for assignment in assignments:
        reg = PosRegister.query.filter_by(fair_id=assignment.fair_id, seller_id=assignment.user_id).first()
        reg_code = reg.code if reg else f"CAISSE-F{assignment.fair_id}-V{assignment.user_id}"
        reg_name = reg.nom if reg else f"Caisse {assignment.fair.nom}"

        work = Work.query.filter_by(id_foire=assignment.fair_id).first()
        stand_desc = f"{work.stand_type.type} (Stand #{work.id_stand})" if (work and work.stand_type) else "Stand Laga"
        transport_desc = f"{work.voiture.model} ({work.voiture.immatricule})" if (work and work.voiture) else "Voiture de transport"
        chauffeur_desc = f"{work.chauffeur.prenom} {work.chauffeur.nom}" if (work and work.chauffeur) else "Chauffeur"
        mission_dates = f"du {work.date_d} au {work.date_f}" if work else ""

        context = contexts.setdefault(
            assignment.fair_id,
            {
                "fair_id": assignment.fair_id,
                "fair_name": assignment.fair.nom,
                "register_code": reg_code,
                "register_name": reg_name,
                "stand_name": stand_desc,
                "vehicle_name": transport_desc,
                "chauffeur_name": chauffeur_desc,
                "mission_dates": mission_dates,
                "sellers": [],
                "inventory": [],
            },
        )
        if not any(s["user_id"] == assignment.user_id for s in context["sellers"]):
            context["sellers"].append({
                "user_id": assignment.user_id,
                "name": f"{assignment.user.prenom} {assignment.user.nom}".strip(),
                "register_code": reg_code,
            })

    for fair_id, context in contexts.items():
        context["inventory"] = [
            {
                "article_ref": balance.article_ref,
                "quantity": balance.quantity,
            }
            for balance in FairInventoryBalance.query.filter_by(
                fair_id=fair_id
            ).filter(FairInventoryBalance.quantity > 0).all()
        ]
    return jsonify(list(contexts.values()))


@api_bp.route("/pos/receivables", methods=["GET"])
@permission_required("vente")
def list_pos_receivables():
    query = PosSale.query.filter(
        PosSale.type == "credit",
        PosSale.paid_amount < PosSale.amount,
    )
    query = scope_pos_sales(query)
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    try:
        if start_date:
            query = query.filter(PosSale.date >= date.fromisoformat(start_date))
        if end_date:
            query = query.filter(PosSale.date <= date.fromisoformat(end_date))
    except ValueError:
        return jsonify({"error": "Les dates doivent être au format AAAA-MM-JJ."}), 400

    sales = query.order_by(
        PosSale.due_date.asc(), PosSale.date.asc(), PosSale.transaction_id.asc()
    ).all()
    return jsonify({
        "count": len(sales),
        "total_balance": money_value(
            sum((sale.amount - sale.paid_amount for sale in sales), Decimal("0.00"))
        ),
        "receivables": [sale.to_dict() for sale in sales],
    })


@api_bp.route("/pos/sales/<int:sale_id>/collections", methods=["POST"])
@permission_required("vente")
def collect_pos_payment(sale_id):
    sale = db.session.get(PosSale, sale_id)
    if sale is None:
        return jsonify({"error": "Vente introuvable."}), 404
    if not pos_sale_is_visible(sale):
        return jsonify({"error": "Vente introuvable."}), 404
    if sale.type != "credit":
        return jsonify({"error": "Les encaissements ne s’appliquent qu’aux ventes à crédit."}), 409

    payload, error = request_data()
    if error:
        return error
    try:
        amount = Decimal(str(payload.get("amount"))).quantize(
            MONEY_QUANTUM, rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"error": "Le montant encaissé doit être valide."}), 400
    if not amount.is_finite() or amount <= 0:
        return jsonify({"error": "Le montant encaissé doit être supérieur à zéro."}), 400

    remarks = payload.get("remarks", "")
    if not isinstance(remarks, str) or len(remarks.strip()) > 500:
        return jsonify({"error": "Les remarques ne doivent pas dépasser 500 caractères."}), 400
    try:
        collection_date = date.fromisoformat(payload.get("date", date.today().isoformat()))
    except (TypeError, ValueError):
        return jsonify({"error": "La date d’encaissement doit être au format AAAA-MM-JJ."}), 400

    payment_update = db.session.execute(
        update(PosSale)
        .where(
            PosSale.transaction_id == sale_id,
            PosSale.type == "credit",
            PosSale.paid_amount + amount <= PosSale.amount,
        )
        .values(paid_amount=PosSale.paid_amount + amount)
        .execution_options(synchronize_session=False)
    )
    if payment_update.rowcount != 1:
        db.session.rollback()
        return jsonify({
            "error": "Le montant dépasse le solde restant ou la vente est déjà réglée."
        }), 409

    collection = PosCollection(
        sale_id=sale_id,
        date=collection_date,
        invoice_number=f"IN-{secrets.token_hex(8).upper()}",
        amount=amount,
        remarks=remarks.strip(),
    )
    db.session.add(collection)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "L’encaissement n’a pas pu être enregistré."}), 409

    db.session.refresh(sale)
    db.session.refresh(collection)
    return jsonify({
        "message": "Encaissement enregistré.",
        "collection": collection.to_dict(),
        "sale": sale.to_dict(),
    }), 201


@api_bp.route("/pos/collections", methods=["GET"])
@permission_required("vente")
def list_pos_collections():
    query = PosCollection.query.join(PosSale)
    if g.current_user.type != "admin":
        owner_column = (
            PosSale.seller_id
            if g.current_user.type == "vendeur"
            else PosSale.cashier_user_id
        )
        query = query.filter(owner_column == g.current_user.id)
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    try:
        if start_date:
            query = query.filter(PosCollection.date >= date.fromisoformat(start_date))
        if end_date:
            query = query.filter(PosCollection.date <= date.fromisoformat(end_date))
    except ValueError:
        return jsonify({"error": "Les dates doivent être au format AAAA-MM-JJ."}), 400

    collections = query.order_by(
        PosCollection.date.desc(), PosCollection.collection_id.desc()
    ).all()
    return jsonify({
        "count": len(collections),
        "total_amount": money_value(
            sum((collection.amount for collection in collections), Decimal("0.00"))
        ),
        "collections": [collection.to_dict() for collection in collections],
    })


@api_bp.route("/pos/stock-movements", methods=["GET"])
@permission_required("article", "vente", "achat")
def list_pos_stock_movements():
    try:
        limit = int(request.args.get("limit", 100))
        if limit < 1 or limit > 500:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "La limite doit être comprise entre 1 et 500."}), 400

    query = PosStockMovement.query
    product_id = request.args.get("product_id")
    if product_id:
        try:
            product_id = int(product_id)
        except ValueError:
            return jsonify({"error": "L’identifiant produit doit être un entier."}), 400
        query = query.filter_by(product_id=product_id)

    movements = query.order_by(
        PosStockMovement.created_at.desc(),
        PosStockMovement.movement_id.desc(),
    ).limit(limit).all()
    include_cost = g.current_user.type == "admin"
    return jsonify([
        movement.to_dict(include_cost=include_cost) for movement in movements
    ])


@api_bp.route("/pos/reports/sales", methods=["GET"])
@permission_required("vente")
def pos_sales_report():
    query = scope_pos_sales(PosSale.query)
    query, filter_error = apply_pos_sale_context_filters(query)
    if filter_error:
        return jsonify({"error": filter_error}), 400
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    try:
        if start_date:
            query = query.filter(PosSale.date >= date.fromisoformat(start_date))
        if end_date:
            query = query.filter(PosSale.date <= date.fromisoformat(end_date))
    except ValueError:
        return jsonify({"error": "Les dates doivent être au format AAAA-MM-JJ."}), 400

    sales = query.order_by(PosSale.date.desc(), PosSale.transaction_id.desc()).all()
    result = {
        "count": len(sales),
        "total_amount": money_value(sum((sale.amount for sale in sales), Decimal("0.00"))),
        "sales": [
            sale.to_dict(include_profit=g.current_user.type == "admin")
            for sale in sales
        ],
    }
    if g.current_user.type == "admin":
        result["total_profit"] = money_value(
            sum((sale.profit for sale in sales), Decimal("0.00"))
        )
    return jsonify(result)


@api_bp.route("/pos/reports/fairs", methods=["GET"])
@admin_required
def pos_fair_sales_report():
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    try:
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None
    except ValueError:
        return jsonify({"error": "Les dates doivent être au format AAAA-MM-JJ."}), 400
    if start and end and start > end:
        return jsonify({"error": "La date de début doit précéder la date de fin."}), 400

    query = (
        db.session.query(
            PosSale.fair_id,
            PosSale.seller_id,
            func.count(PosSale.transaction_id),
            func.coalesce(func.sum(PosSale.amount), 0),
            func.coalesce(func.sum(PosSale.profit), 0),
        )
        .filter(PosSale.fair_id.isnot(None))
        .group_by(PosSale.fair_id, PosSale.seller_id)
        .order_by(PosSale.fair_id, PosSale.seller_id)
    )
    if start:
        query = query.filter(PosSale.date >= start)
    if end:
        query = query.filter(PosSale.date <= end)

    fairs = {
        fair.id: {
            "fair_id": fair.id,
            "fair_name": fair.nom,
            "count": 0,
            "total_amount": Decimal("0.00"),
            "total_profit": Decimal("0.00"),
            "sellers": [],
        }
        for fair in Fair.query.order_by(Fair.nom.asc(), Fair.id.asc()).all()
    }
    total_count = 0
    total_amount = Decimal("0.00")
    total_profit = Decimal("0.00")

    for fair_id, seller_id, count, amount, profit in query.all():
        fair_summary = fairs.get(fair_id)
        if fair_summary is None:
            continue
        seller = db.session.get(User, seller_id) if seller_id is not None else None
        amount = Decimal(amount or 0)
        profit = Decimal(profit or 0)
        fair_summary["count"] += count
        fair_summary["total_amount"] += amount
        fair_summary["total_profit"] += profit
        fair_summary["sellers"].append({
            "seller_id": seller_id,
            "seller_name": (
                f"{seller.prenom} {seller.nom}".strip()
                if seller
                else "Vendeur non renseigné"
            ),
            "count": count,
            "total_amount": money_value(amount),
            "total_profit": money_value(profit),
        })
        total_count += count
        total_amount += amount
        total_profit += profit

    general_query = db.session.query(
        func.count(PosSale.transaction_id),
        func.coalesce(func.sum(PosSale.amount), 0),
        func.coalesce(func.sum(PosSale.profit), 0),
    ).filter(PosSale.fair_id.is_(None))
    if start:
        general_query = general_query.filter(PosSale.date >= start)
    if end:
        general_query = general_query.filter(PosSale.date <= end)
    general_count, general_amount, general_profit = general_query.one()

    return jsonify({
        "count": total_count,
        "total_amount": money_value(total_amount),
        "total_profit": money_value(total_profit),
        "general_sales": {
            "count": general_count,
            "total_amount": money_value(general_amount or 0),
            "total_profit": money_value(general_profit or 0),
        },
        "fairs": [
            {
                **summary,
                "total_amount": money_value(summary["total_amount"]),
                "total_profit": money_value(summary["total_profit"]),
            }
            for summary in fairs.values()
        ],
    })


@api_bp.route("/pos/sales/<int:sale_id>", methods=["GET"])
@permission_required("vente")
def get_pos_sale(sale_id):
    sale = db.session.get(PosSale, sale_id)
    if sale is None:
        return jsonify({"error": "Vente introuvable."}), 404
    if not pos_sale_is_visible(sale):
        return jsonify({"error": "Vente introuvable."}), 404
    return jsonify(sale.to_dict(
        include_items=True,
        include_profit=g.current_user.type == "admin",
        include_collections=True,
    ))


@api_bp.route("/pos/checkout", methods=["POST"])
@permission_required("vente")
def checkout_pos_sale():
    payload, error = request_data()
    if error:
        return error
    if db.engine.dialect.name == "sqlite":
        db.session.rollback()
        db.session.connection().exec_driver_sql("BEGIN IMMEDIATE")

    lines = payload.get("items")
    if not isinstance(lines, list) or not lines or len(lines) > 100:
        return jsonify({"error": "Le panier doit contenir entre 1 et 100 lignes."}), 400
    product_quantities = {}
    for line in lines:
        if not isinstance(line, dict):
            return jsonify({"error": "Une ligne du panier est invalide."}), 400
        try:
            product_id = int(line.get("product_id"))
            quantity = int(line.get("qty"))
        except (TypeError, ValueError):
            return jsonify({"error": "Produit ou quantité invalide dans le panier."}), 400
        if product_id < 1 or quantity < 1:
            return jsonify({"error": "Les quantités doivent être des entiers positifs."}), 400
        if str(product_id) != str(line.get("product_id")) or str(quantity) != str(line.get("qty")):
            return jsonify({"error": "Les identifiants et quantités doivent être des entiers."}), 400
        if product_id in product_quantities:
            return jsonify({"error": "Chaque produit ne peut figurer qu’une seule fois dans le panier."}), 400
        product_quantities[product_id] = quantity

    payment_type = payload.get("payment_type")
    if payment_type not in {"cash", "credit"}:
        return jsonify({"error": "Le mode de paiement doit être espèces ou crédit."}), 400
    fair_id = payload.get("fair_id")
    seller_id = payload.get("seller_id")
    if fair_id in (None, ""):
        return jsonify({"error": "Chaque vente doit être associée à une foire."}), 400
    if (
        g.current_user.type == "vendeur"
        and seller_id not in (None, "")
        and str(seller_id) != str(g.current_user.id)
    ):
        return jsonify({"error": "Un vendeur ne peut enregistrer une vente pour un autre vendeur."}), 403
    if g.current_user.type == "vendeur":
        seller_id = g.current_user.id
    try:
        fair_id = int(fair_id)
        seller_id = int(seller_id)
    except (TypeError, ValueError):
        return jsonify({"error": "La foire et le vendeur sont obligatoires pour une vente."}), 400
    if (
        fair_id < 1
        or seller_id < 1
        or str(fair_id) != str(payload.get("fair_id"))
        or str(seller_id) != str(payload.get("seller_id"))
    ):
        return jsonify({"error": "La foire et le vendeur sont invalides."}), 400
    fair = db.session.get(Fair, fair_id)
    seller = db.session.get(User, seller_id)
    if fair is None or seller is None:
        return jsonify({"error": "Foire ou vendeur introuvable."}), 404
    if seller.type != "vendeur":
        return jsonify({"error": "Le compte sélectionné n’est pas un vendeur."}), 400
    if fair.status in {"cancelled", "completed"}:
        return jsonify({"error": "Cette foire n’accepte plus de ventes."}), 409
    today = date.today()
    if (
        (fair.start_date is not None and fair.start_date > today and fair.status != "active" and g.current_user.type != "admin")
        or (fair.end_date is not None and fair.end_date < today and fair.status != "active" and g.current_user.type != "admin")
    ):
        return jsonify({"error": "Cette foire n’est pas active aujourd’hui."}), 409
    assignment = FairAssignment.query.filter(
        FairAssignment.fair_id == fair.id,
        FairAssignment.user_id == seller.id,
        FairAssignment.role == "vendeur",
        FairAssignment.status == "confirmed",
        FairAssignment.start_date <= today,
        FairAssignment.end_date >= today,
    ).first()
    if assignment is None:
        return jsonify({"error": "Le vendeur n’est pas affecté à cette foire aujourd’hui."}), 409

    customer_name = payload.get("customer_name", "")
    if not isinstance(customer_name, str) or len(customer_name.strip()) > 160:
        return jsonify({"error": "Le nom du client ne doit pas dépasser 160 caractères."}), 400
    customer_name = customer_name.strip()

    due_date = None
    cash_received = None
    if payment_type == "credit":
        if not customer_name:
            return jsonify({"error": "Le nom du client est obligatoire pour une vente à crédit."}), 400
        try:
            due_date = date.fromisoformat(payload.get("due_date", ""))
        except (TypeError, ValueError):
            return jsonify({"error": "Une date d’échéance valide est requise pour une vente à crédit."}), 400
    else:
        try:
            cash_received = Decimal(str(payload.get("cash_received"))).quantize(
                MONEY_QUANTUM, rounding=ROUND_HALF_UP
            )
        except (InvalidOperation, TypeError, ValueError):
            return jsonify({"error": "Le montant reçu doit être un montant valide."}), 400
        if not cash_received.is_finite() or cash_received < 0:
            return jsonify({"error": "Le montant reçu doit être positif ou nul."}), 400
    customer_record = (
        get_or_create_pos_contact(PosCustomer, customer_name)
        if customer_name
        else None
    )
    customer_name = customer_name or "Client comptoir"

    products = {
        product.product_id: product
        for product in PosProduct.query.filter(
            PosProduct.product_id.in_(product_quantities)
        ).all()
    }
    if len(products) != len(product_quantities):
        return jsonify({"error": "Un produit du panier est introuvable."}), 404

    total = Decimal("0.00")
    total_profit = Decimal("0.00")
    for product_id, quantity in product_quantities.items():
        product = products[product_id]
        if not product.pricing_configured:
            return jsonify({
                "error": f"Les prix du produit « {product.gen_name} » doivent être configurés avant sa vente."
            }), 409
        if fair is not None:
            if not product.article_ref:
                return jsonify({
                    "error": f"Le produit « {product.gen_name} » n’est pas lié à un article du stock général."
                }), 409
            fair_balance = db.session.get(
                FairInventoryBalance, (fair.id, product.article_ref)
            )
            available = fair_balance.quantity if fair_balance else 0
        else:
            available = product.qty
        if quantity > available:
            return jsonify({
                "error": f"Stock insuffisant pour « {product.gen_name} » (disponible : {available})."
            }), 409
        total += product.price * quantity
        total_profit += (product.price - product.o_price) * quantity
    total = total.quantize(MONEY_QUANTUM)
    total_profit = total_profit.quantize(MONEY_QUANTUM)
    if payment_type == "cash" and cash_received < total:
        return jsonify({"error": "Le montant reçu est inférieur au total de la vente."}), 400

    pos_reg = PosRegister.query.filter_by(fair_id=fair.id, seller_id=seller.id).first() if (fair and seller) else None
    sale_reg_code = pos_reg.code if pos_reg else (f"CAISSE-F{fair.id}-V{seller.id}" if (fair and seller) else None)
    sale = PosSale(
        invoice_number=f"RS-{secrets.token_hex(8).upper()}",
        cashier=f"{g.current_user.prenom} {g.current_user.nom}".strip(),
        date=date.today(),
        type=payment_type,
        amount=total,
        profit=total_profit,
        customer_name=customer_name,
        customer=customer_record,
        fair=fair,
        seller=seller,
        cashier_user=g.current_user,
        cash_received=cash_received,
        due_date=due_date,
        register_code=sale_reg_code,
    )
    db.session.add(sale)
    try:
        db.session.flush()
        for product_id, quantity in product_quantities.items():
            product = products[product_id]
            line_amount = (product.price * quantity).quantize(MONEY_QUANTUM)
            line_profit = ((product.price - product.o_price) * quantity).quantize(
                MONEY_QUANTUM
            )
            db.session.add(
                PosSaleItem(
                    sale_id=sale.transaction_id,
                    product_id=product.product_id,
                    product_code=product.product_code,
                    gen_name=product.gen_name,
                    product_name=product.product_name,
                    qty=quantity,
                    price=product.price,
                    amount=line_amount,
                    profit=line_profit,
                )
            )
            if fair is not None:
                fair_balance_update = db.session.execute(
                    update(FairInventoryBalance)
                    .where(
                        FairInventoryBalance.fair_id == fair.id,
                        FairInventoryBalance.article_ref == product.article_ref,
                        FairInventoryBalance.quantity >= quantity,
                    )
                    .values(quantity=FairInventoryBalance.quantity - quantity)
                )
                if fair_balance_update.rowcount != 1:
                    db.session.rollback()
                    return jsonify({
                        "error": f"Le stock de « {product.gen_name} » à la foire vient de changer."
                    }), 409
                db.session.execute(
                    update(PosProduct)
                    .where(PosProduct.product_id == product_id)
                    .values(qty_sold=PosProduct.qty_sold + quantity)
                )
                db.session.add(
                    FairInventoryMovement(
                        fair_id=fair.id,
                        article_ref=product.article_ref,
                        movement_type="sale",
                        quantity_delta=-quantity,
                        movement_date=date.today(),
                        reference=sale.invoice_number,
                        created_by=g.current_user.id,
                    )
                )
            else:
                db.session.add(
                    PosStockMovement(
                        product_id=product.product_id,
                        movement_type="sale",
                        quantity_delta=-quantity,
                        unit_cost=product.o_price,
                        reference_type="sale",
                        reference_id=sale.transaction_id,
                        recorded_by_id=g.current_user.id,
                    )
                )
                stock_update = db.session.execute(
                    update(PosProduct)
                    .where(
                        PosProduct.product_id == product_id,
                        PosProduct.qty >= quantity,
                    )
                    .values(
                        qty=PosProduct.qty - quantity,
                        qty_sold=PosProduct.qty_sold + quantity,
                    )
                )
                if stock_update.rowcount != 1:
                    db.session.rollback()
                    return jsonify({
                        "error": f"Le stock de « {product.gen_name} » vient de changer. Actualisez le panier."
                    }), 409
                if product.article:
                    apply_article_stock_delta(product.article, -quantity)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "La vente n’a pas pu être enregistrée."}), 409

    return jsonify({
        "message": "Vente enregistrée.",
        "sale": sale.to_dict(
            include_items=True,
            include_profit=g.current_user.type == "admin",
        ),
    }), 201


@api_bp.route("/works/<int:work_id>/confirm", methods=["POST"])
@permission_required("work")
def confirm_work(work_id):
    work = db.session.get(Work, work_id)
    if work is None:
        return jsonify({"error": "Mission introuvable."}), 404
    payload, error = request_data()
    if error:
        return error
    role = payload.get("role")
    role_to_user_field = {
        "vendeur": "id_vendeur",
        "chauffeur": "id_chauffeur",
        "deco": "id_deco",
    }
    if role not in role_to_user_field:
        return jsonify({"error": "Rôle de confirmation invalide."}), 400
    if getattr(work, role_to_user_field[role]) != g.current_user.id:
        return jsonify({"error": "Cette mission ne vous est pas attribuée."}), 403

    confirmation = db.session.get(Confirmation, work_id)
    if confirmation is None:
        confirmation = Confirmation(id=work_id)
        db.session.add(confirmation)
    setattr(confirmation, f"c_{role}", True)
    confirmed_count = sum(
        bool(getattr(confirmation, f"c_{assigned_role}"))
        for assigned_role in role_to_user_field
    )
    work.flow = "achevee" if confirmed_count == 3 else "en cours" if confirmed_count else "en attente"
    db.session.commit()
    return jsonify({
        "message": "Mission confirmée.",
        "mission": work.to_dict(),
        "confirmations": confirmation.to_dict(),
    })


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@api_bp.route("/dashboard", methods=["GET"])
@admin_required
def dashboard():
    today = date.today()
    first_of_month = today.replace(day=1)
    week_start = today - timedelta(days=6)

    total_articles = Article.query.count()
    total_clients = Client.query.count()
    total_suppliers = Supplier.query.count()
    total_users = User.query.count()

    stock_value = db.session.query(func.sum(Article.v_stocks)).scalar() or 0

    active_fairs = Fair.query.filter(
        or_(
            Fair.status == "active",
            db.and_(
                Fair.status.is_(None),
                Fair.start_date <= today,
                Fair.end_date >= today,
            ),
        )
    ).count()

    upcoming_fairs = Fair.query.filter(
        or_(
            Fair.status == "planned",
            Fair.start_date > today,
        )
    ).count()

    today_sales_count = PosSale.query.filter(PosSale.date == today).count()
    today_sales_amount = (
        db.session.query(func.sum(PosSale.amount))
        .filter(PosSale.date == today)
        .scalar()
    ) or Decimal("0.00")

    week_sales_amount = (
        db.session.query(func.sum(PosSale.amount))
        .filter(PosSale.date >= week_start)
        .scalar()
    ) or Decimal("0.00")

    month_sales_amount = (
        db.session.query(func.sum(PosSale.amount))
        .filter(PosSale.date >= first_of_month)
        .scalar()
    ) or Decimal("0.00")

    total_receivables = (
        db.session.query(func.sum(PosSale.amount - PosSale.paid_amount))
        .filter(
            PosSale.type == "credit",
            PosSale.paid_amount < PosSale.amount,
        )
        .scalar()
    ) or Decimal("0.00")

    top_products = (
        PosProduct.query
        .order_by(PosProduct.qty_sold.desc())
        .limit(5)
        .all()
    )

    recent_sales = (
        PosSale.query
        .order_by(PosSale.date.desc(), PosSale.transaction_id.desc())
        .limit(5)
        .all()
    )

    low_stock_articles = Article.query.filter(
        Article.v_stocks < 10,
        Article.v_stocks >= 0,
    ).count()

    unconfigured_products = PosProduct.query.filter(
        PosProduct.pricing_configured == False,
    ).count()

    return jsonify({
        "total_articles": total_articles,
        "total_clients": total_clients,
        "total_suppliers": total_suppliers,
        "total_users": total_users,
        "stock_value": stock_value,
        "active_fairs": active_fairs,
        "upcoming_fairs": upcoming_fairs,
        "today_sales_count": today_sales_count,
        "today_sales_amount": money_value(today_sales_amount),
        "week_sales_amount": money_value(week_sales_amount),
        "month_sales_amount": money_value(month_sales_amount),
        "total_receivables": money_value(total_receivables),
        "top_products": [
            {
                "product_code": p.product_code,
                "gen_name": p.gen_name,
                "qty_sold": p.qty_sold,
            }
            for p in top_products
        ],
        "recent_sales": [
            sale.to_dict(include_profit=True) for sale in recent_sales
        ],
        "low_stock_articles": low_stock_articles,
        "unconfigured_products": unconfigured_products,
    })


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@api_bp.route("/alerts", methods=["GET"])
@login_required
def alerts():
    today = date.today()
    is_admin = g.current_user.type == "admin"

    # Low stock articles
    low_stock_query = (
        Article.query
        .filter(Article.v_stocks < 10, Article.v_stocks >= 0)
        .order_by(Article.v_stocks.asc())
    )
    low_stock_total = low_stock_query.count()
    low_stock = [
        {"ref": a.ref, "nom": a.nom, "v_stocks": a.v_stocks}
        for a in low_stock_query.limit(20).all()
    ]

    # Overdue receivables (admin only)
    if is_admin:
        overdue_query = (
            PosSale.query
            .filter(
                PosSale.type == "credit",
                PosSale.paid_amount < PosSale.amount,
                PosSale.due_date < today,
            )
            .order_by(PosSale.due_date.asc())
        )
        overdue_total = overdue_query.count()
        overdue_receivables = [
            sale.to_dict() for sale in overdue_query.limit(20).all()
        ]
    else:
        overdue_total = 0
        overdue_receivables = []

    # Upcoming fairs (next 7 days)
    upcoming_query = (
        Fair.query
        .filter(
            Fair.start_date.isnot(None),
            Fair.start_date > today,
            Fair.start_date <= today + timedelta(days=7),
        )
        .order_by(Fair.start_date)
    )
    upcoming_total = upcoming_query.count()
    upcoming_fairs = [f.to_dict() for f in upcoming_query.all()]

    # Unconfigured products (admin only)
    if is_admin:
        unconfigured_query = PosProduct.query.filter(
            PosProduct.pricing_configured == False,
        )
        unconfigured_total = unconfigured_query.count()
        unconfigured_products = [
            {
                "product_id": p.product_id,
                "product_code": p.product_code,
                "gen_name": p.gen_name,
            }
            for p in unconfigured_query.limit(20).all()
        ]
    else:
        unconfigured_total = 0
        unconfigured_products = []

    return jsonify({
        "low_stock": low_stock,
        "overdue_receivables": overdue_receivables,
        "upcoming_fairs": upcoming_fairs,
        "unconfigured_products": unconfigured_products,
        "counts": {
            "low_stock": low_stock_total,
            "overdue": overdue_total,
            "upcoming_fairs": upcoming_total,
            "unconfigured": unconfigured_total,
        },
    })


# ---------------------------------------------------------------------------
# CSV Export helpers & endpoints
# ---------------------------------------------------------------------------

def csv_response(rows, columns, filename):
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col, '') for col in columns])
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_bp.route("/articles/export", methods=["GET"])
@permission_required("article")
def export_articles():
    log_audit('EXPORT_ARTICLES_CSV')
    articles = Article.query.all()
    rows = [
        {
            "ref": a.ref,
            "nom": a.nom,
            "famille": a.famille,
            "categorie": a.categorie,
            "description": a.description,
            "v_entrees": a.v_entrees,
            "v_retour": a.v_retour,
            "v_stocks": a.v_stocks,
        }
        for a in articles
    ]
    columns = ["ref", "nom", "famille", "categorie", "description", "v_entrees", "v_retour", "v_stocks"]
    return csv_response(rows, columns, "articles.csv")


@api_bp.route("/clients/export", methods=["GET"])
@permission_required("client")
def export_clients():
    log_audit('EXPORT_CLIENTS_CSV')
    clients = Client.query.all()
    rows = [
        {
            "id": c.id,
            "nom": c.nom,
            "prenom": c.prenom,
            "tel": c.tel,
            "email": c.email,
            "specialite": c.specialite or "",
            "ville": c.ville or "",
        }
        for c in clients
    ]
    columns = ["id", "nom", "prenom", "tel", "email", "specialite", "ville"]
    return csv_response(rows, columns, "clients.csv")


@api_bp.route("/suppliers/export", methods=["GET"])
@permission_required("fournisseur")
def export_suppliers():
    log_audit('EXPORT_SUPPLIERS_CSV')
    suppliers = Supplier.query.all()
    rows = [
        {
            "id": s.id,
            "nom": s.nom,
            "prenom": s.prenom,
            "tel": s.tel,
            "email": s.email,
            "specialite": s.specialite or "",
            "ville": s.ville or "",
        }
        for s in suppliers
    ]
    columns = ["id", "nom", "prenom", "tel", "email", "specialite", "ville"]
    return csv_response(rows, columns, "fournisseurs.csv")


@api_bp.route("/pos/sales/export", methods=["GET"])
@admin_required
def export_pos_sales():
    log_audit('EXPORT_POS_SALES_CSV')
    query = PosSale.query
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    try:
        if start_date:
            query = query.filter(PosSale.date >= date.fromisoformat(start_date))
        if end_date:
            query = query.filter(PosSale.date <= date.fromisoformat(end_date))
    except ValueError:
        return jsonify({"error": "Les dates doivent être au format AAAA-MM-JJ."}), 400
    sales = query.order_by(PosSale.date.desc(), PosSale.transaction_id.desc()).all()
    rows = [
        {
            "invoice_number": s.invoice_number,
            "date": s.date.isoformat(),
            "cashier": s.cashier,
            "type": s.type,
            "amount": money_value(s.amount),
            "profit": money_value(s.profit),
            "paid_amount": money_value(s.paid_amount or s.amount * 0),
            "customer_name": s.customer_name,
            "fair_name": s.fair.nom if s.fair else "",
            "seller_name": (
                f"{s.seller.prenom} {s.seller.nom}".strip()
                if s.seller
                else ""
            ),
        }
        for s in sales
    ]
    columns = [
        "invoice_number", "date", "cashier", "type", "amount",
        "profit", "paid_amount", "customer_name", "fair_name", "seller_name",
    ]
    return csv_response(rows, columns, "ventes.csv")


# ---------------------------------------------------------------------------
# POS Sale Receipt (HTML)
# ---------------------------------------------------------------------------

@api_bp.route("/pos/sales/<int:sale_id>/receipt", methods=["GET"])
@permission_required("vente")
def pos_sale_receipt(sale_id):
    sale = db.session.get(PosSale, sale_id)
    if sale is None:
        return jsonify({"error": "Vente introuvable."}), 404
    if not pos_sale_is_visible(sale):
        return jsonify({"error": "Vente introuvable."}), 404

    currency_setting = SystemSetting.query.filter_by(key="currency").first()
    currency = currency_setting.value if currency_setting else "TND"

    items_html = ""
    for item in sale.items:
        p_code = html.escape(str(item.product_code or ''))
        p_name = html.escape(str(item.gen_name or ''))
        items_html += (
            f"<tr>"
            f"<td>{p_code}</td>"
            f"<td>{p_name}</td>"
            f"<td style='text-align:right'>{item.qty}</td>"
            f"<td style='text-align:right'>{money_value(item.price)}</td>"
            f"<td style='text-align:right'>{money_value(item.amount)}</td>"
            f"</tr>"
        )

    p_type = html.escape(str(sale.type or ''))
    payment_info = f"<p><strong>Type de paiement :</strong> {p_type}</p>"
    if sale.type == "cash" and sale.cash_received is not None:
        change = sale.cash_received - sale.amount
        payment_info += (
            f"<p><strong>Espèces reçues :</strong> {money_value(sale.cash_received)} {currency}</p>"
            f"<p><strong>Monnaie rendue :</strong> {money_value(change)} {currency}</p>"
        )
    elif sale.type == "credit":
        cust_name = html.escape(str(sale.customer_name or ''))
        payment_info += (
            f"<p><strong>Client :</strong> {cust_name}</p>"
        )

    fair_name = html.escape(str(sale.fair.nom)) if sale.fair else ""
    fair_line = f"<p><strong>Foire :</strong> {fair_name}</p>" if sale.fair else ""
    seller_line = ""
    if sale.seller:
        s_name = html.escape(f"{sale.seller.prenom} {sale.seller.nom}".strip())
        seller_line = f"<p><strong>Vendeur :</strong> {s_name}</p>"

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Reçu de vente</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 400px; margin: 0 auto; padding: 20px; font-size: 14px; }}
  h1 {{ text-align: center; font-size: 18px; margin-bottom: 4px; }}
  h2 {{ text-align: center; font-size: 14px; margin-top: 0; color: #555; }}
  .info {{ margin-bottom: 12px; }}
  .info p {{ margin: 2px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
  th, td {{ border-bottom: 1px solid #ccc; padding: 4px 6px; text-align: left; font-size: 13px; }}
  th {{ background: #f5f5f5; }}
  .total {{ text-align: right; font-size: 16px; font-weight: bold; margin: 12px 0; }}
  @media print {{
    body {{ margin: 0; padding: 10px; }}
    button {{ display: none; }}
  }}
</style>
</head>
<body>
<h1>OKBA INTER</h1>
<h2>Reçu de vente</h2>
<div class="info">
  <p><strong>N° Facture :</strong> {html.escape(str(sale.invoice_number))}</p>
  <p><strong>Date :</strong> {sale.date.isoformat()}</p>
  <p><strong>Caissier :</strong> {html.escape(str(sale.cashier or ''))}</p>
  {fair_line}
  {seller_line}
</div>
<table>
  <thead>
    <tr><th>Code</th><th>Désignation</th><th style="text-align:right">Qté</th><th style="text-align:right">Prix</th><th style="text-align:right">Montant</th></tr>
  </thead>
  <tbody>
    {items_html}
  </tbody>
</table>
<div class="total">Total : {money_value(sale.amount)} {currency}</div>
{payment_info}
</body>
</html>"""

    response = make_response(html)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response
