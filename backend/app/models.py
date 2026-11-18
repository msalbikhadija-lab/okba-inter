from datetime import datetime, timezone
from sqlalchemy import CheckConstraint

from . import db


def money_value(value):
    return float(value or 0)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(80), nullable=False)
    prenom = db.Column(db.String(80), nullable=False)
    login = db.Column(db.String(80), unique=True, nullable=False)
    pw = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(50), nullable=False, default="vendeur")
    lpp = db.Column(db.Integer, nullable=False, default=8)
    ville = db.Column(db.String(100), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "prenom": self.prenom,
            "login": self.login,
            "type": self.type,
            "lpp": self.lpp,
            "ville": self.ville or "",
        }


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nom = db.Column(db.String(120), nullable=False)
    prenom = db.Column(db.String(120), nullable=False)
    tel = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    specialite = db.Column(db.String(100), nullable=True)
    ville = db.Column(db.String(100), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "prenom": self.prenom,
            "tel": self.tel,
            "email": self.email,
            "specialite": self.specialite or "",
            "ville": self.ville or "",
        }


class Article(db.Model):
    __tablename__ = "articles"

    ref = db.Column(db.String(50), primary_key=True)
    famille = db.Column(db.String(120), nullable=False, default="")
    description = db.Column(db.String(255), nullable=False)
    categorie = db.Column(db.String(120), nullable=False, default="")
    nom = db.Column(db.String(160), nullable=False)
    v_entrees = db.Column(db.Integer, nullable=False, default=0)
    v_retour = db.Column(db.Integer, nullable=False, default=0)
    v_stocks = db.Column(db.Integer, nullable=False, default=0)
    barcode = db.Column(db.String(120), nullable=True, index=True)

    def to_dict(self):
        return {
            "famille": self.famille,
            "description": self.description,
            "categorie": self.categorie,
            "ref": self.ref,
            "nom": self.nom,
            "v_entrees": self.v_entrees,
            "v_retour": self.v_retour,
            "v_stocks": self.v_stocks,
            "barcode": self.barcode or "",
        }


class Supplier(db.Model):
    __tablename__ = "fournisseurs"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    prenom = db.Column(db.String(120), nullable=False)
    tel = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    specialite = db.Column(db.String(100), nullable=True)
    ville = db.Column(db.String(100), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "prenom": self.prenom,
            "tel": self.tel,
            "email": self.email,
            "specialite": self.specialite or "",
            "ville": self.ville or "",
        }


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    article_ref = db.Column(db.String(50), db.ForeignKey("articles.ref"), nullable=False)
    quantite = db.Column(db.Integer, nullable=False)
    date_mouvement = db.Column(db.Date, nullable=False)
    id_fournisseur = db.Column(db.Integer, db.ForeignKey("fournisseurs.id"))
    id_client = db.Column(db.Integer, db.ForeignKey("clients.id"))

    article = db.relationship("Article")
    fournisseur = db.relationship("Supplier")
    client = db.relationship("Client")

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "article_ref": self.article_ref,
            "article_nom": self.article.nom if self.article else "",
            "quantite": self.quantite,
            "date_mouvement": self.date_mouvement.isoformat(),
            "id_fournisseur": self.id_fournisseur,
            "fournisseur_nom": (
                f"{self.fournisseur.prenom} {self.fournisseur.nom}"
                if self.fournisseur
                else None
            ),
            "id_client": self.id_client,
            "client_nom": (
                f"{self.client.prenom} {self.client.nom}" if self.client else None
            ),
        }


class Vehicle(db.Model):
    __tablename__ = "voitures"

    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(120), nullable=False)
    immatricule = db.Column(db.String(40), nullable=False)
    annee = db.Column(db.Integer, nullable=False)
    puissance = db.Column(db.Integer, nullable=False)
    location = db.Column(db.Boolean, nullable=True)
    date_d_loc = db.Column(db.String(10), nullable=True)
    date_f_loc = db.Column(db.String(10), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "model": self.model,
            "immatricule": self.immatricule,
            "annee": self.annee,
            "puissance": self.puissance,
            "location": self.location,
            "date_d_loc": self.date_d_loc or "",
            "date_f_loc": self.date_f_loc or "",
        }


class Fair(db.Model):
    __tablename__ = "foires"

    id = db.Column(db.Integer, primary_key=True)
    assigned_vehicle_id = db.Column(
        db.Integer, db.ForeignKey("voitures.id", ondelete="SET NULL"), nullable=True
    )
    assigned_vehicle = db.relationship("Vehicle", foreign_keys=[assigned_vehicle_id])
    nom = db.Column(db.String(160), nullable=False)
    ville = db.Column(db.String(120), nullable=False)
    adresse = db.Column(db.String(255), nullable=False)
    contact = db.Column(db.String(120), nullable=False)
    d_limite = db.Column(db.String(10), nullable=False)
    type = db.Column(db.String(30), nullable=True)
    organizer = db.Column(db.String(160), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    product_send_deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=True)
    allow_late_send = db.Column(db.Boolean, nullable=False, default=False)
    late_send_reason = db.Column(db.String(500), nullable=True)
    manager_notes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "assigned_vehicle_id": self.assigned_vehicle_id,
            "vehicle_name": (
                f"{self.assigned_vehicle.model} — {self.assigned_vehicle.immatricule}"
                if self.assigned_vehicle
                else ""
            ),
            "nom": self.nom,
            "ville": self.ville,
            "adresse": self.adresse,
            "contact": self.contact,
            "d_limite": self.d_limite,
            "type": self.type or "",
            "organizer": self.organizer or "",
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "product_send_deadline": (
                self.product_send_deadline.isoformat()
                if self.product_send_deadline
                else None
            ),
            "status": self.status,
            "allow_late_send": self.allow_late_send,
            "late_send_reason": self.late_send_reason or "",
            "manager_notes": self.manager_notes or "",
        }


class FairAssignment(db.Model):
    __tablename__ = "fair_assignments"

    id = db.Column(db.Integer, primary_key=True)
    fair_id = db.Column(
        db.Integer, db.ForeignKey("foires.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role = db.Column(db.String(24), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="confirmed")
    source = db.Column(db.String(20), nullable=False, default="manual")
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes = db.Column(db.String(500), nullable=True)

    fair = db.relationship("Fair")
    user = db.relationship("User", foreign_keys=[user_id])
    creator = db.relationship("User", foreign_keys=[created_by])

    def to_dict(self):
        return {
            "id": self.id,
            "fair_id": self.fair_id,
            "fair_name": self.fair.nom if self.fair else "",
            "register_code": self.register_code or "",
            "user_id": self.user_id,
            "user_name": (
                f"{self.user.prenom} {self.user.nom}".strip() if self.user else ""
            ),
            "role": self.role,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "status": self.status,
            "source": self.source,
            "created_by": self.created_by,
            "notes": self.notes or "",
        }


class FairInventoryBalance(db.Model):
    __tablename__ = "fair_inventory"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_fair_inventory_nonnegative"),
    )

    fair_id = db.Column(
        db.Integer, db.ForeignKey("foires.id", ondelete="RESTRICT"), primary_key=True
    )
    article_ref = db.Column(
        db.String(50), db.ForeignKey("articles.ref", ondelete="RESTRICT"), primary_key=True
    )
    quantity = db.Column(db.Integer, nullable=False, default=0)

    fair = db.relationship("Fair")
    article = db.relationship("Article")


class FairInventoryMovement(db.Model):
    __tablename__ = "fair_inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta != 0", name="ck_fair_inventory_movement_nonzero"),
        CheckConstraint(
            "(movement_type IN ('transfer_in', 'receipt', 'return') AND quantity_delta > 0) "
            "OR (movement_type IN ('transfer_out', 'sale', 'damage') AND quantity_delta < 0)",
            name="ck_fair_inventory_movement_sign",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    fair_id = db.Column(
        db.Integer, db.ForeignKey("foires.id", ondelete="RESTRICT"), nullable=False
    )
    article_ref = db.Column(
        db.String(50), db.ForeignKey("articles.ref", ondelete="RESTRICT"), nullable=False
    )
    movement_type = db.Column(db.String(20), nullable=False)
    quantity_delta = db.Column(db.Integer, nullable=False)
    movement_date = db.Column(db.Date, nullable=False)
    reference = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    fair = db.relationship("Fair")
    article = db.relationship("Article")
    actor = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "fair_id": self.fair_id,
            "fair_name": self.fair.nom if self.fair else "",
            "article_ref": self.article_ref,
            "article_name": self.article.nom if self.article else "",
            "movement_type": self.movement_type,
            "quantity_delta": self.quantity_delta,
            "movement_date": self.movement_date.isoformat(),
            "reference": self.reference or "",
            "notes": self.notes or "",
            "created_by": self.created_by,
            "actor_name": (
                f"{self.actor.prenom} {self.actor.nom}".strip() if self.actor else ""
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class StandType(db.Model):
    __tablename__ = "liste_stands"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(120), nullable=False)
    etat = db.Column(db.String(80), nullable=False, default="disponible")

    def to_dict(self):
        return {"id": self.id, "type": self.type, "etat": self.etat}


class StandInventory(db.Model):
    __tablename__ = "stands"

    id = db.Column(db.Integer, primary_key=True)
    id_stand = db.Column(db.Integer, db.ForeignKey("liste_stands.id"), nullable=False)
    ref_article = db.Column(db.String(50), db.ForeignKey("articles.ref"), nullable=False)
    quantite = db.Column(db.Integer, nullable=False, default=1)
    date_ch = db.Column(db.String(10), nullable=False)

    stand_type = db.relationship("StandType")
    article = db.relationship("Article")

    def to_dict(self):
        return {
            "id": self.id,
            "id_stand": self.id_stand,
            "stand_type": self.stand_type.type if self.stand_type else "",
            "ref_article": self.ref_article,
            "article_nom": self.article.nom if self.article else "",
            "quantite": self.quantite,
            "date_ch": self.date_ch,
        }


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)
    id_agent = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    id_foire = db.Column(db.Integer, db.ForeignKey("foires.id"), nullable=False)
    taille_stand = db.Column(db.String(80), nullable=False)
    logement = db.Column(db.String(120), nullable=False, default="")
    date_d = db.Column(db.String(10), nullable=False)
    date_f = db.Column(db.String(10), nullable=False)
    etat = db.Column(db.Integer, nullable=True)
    date_c = db.Column(db.String(10), nullable=True)

    agent = db.relationship("User")
    foire = db.relationship("Fair")

    def to_dict(self):
        return {
            "id": self.id,
            "id_agent": self.id_agent,
            "agent_nom": f"{self.agent.prenom} {self.agent.nom}" if self.agent else "",
            "id_foire": self.id_foire,
            "foire_nom": self.foire.nom if self.foire else "",
            "taille_stand": self.taille_stand,
            "logement": self.logement,
            "date_d": self.date_d,
            "date_f": self.date_f,
            "etat": self.etat if self.etat is not None else 0,
            "date_c": self.date_c or "",
        }


class Work(db.Model):
    __tablename__ = "works"

    id = db.Column(db.Integer, primary_key=True)
    date_d = db.Column(db.String(10), nullable=False)
    date_f = db.Column(db.String(10), nullable=False)
    id_foire = db.Column(db.Integer, db.ForeignKey("foires.id"), nullable=False)
    id_stand = db.Column(db.Integer, db.ForeignKey("liste_stands.id"), nullable=False)
    id_vendeur = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    id_deco = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    id_chauffeur = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    id_voiture = db.Column(db.Integer, db.ForeignKey("voitures.id"), nullable=False)
    flow = db.Column(db.String(40), nullable=False, default="en attente")
    foire = db.relationship("Fair")
    stand_type = db.relationship("StandType")
    vendeur = db.relationship("User", foreign_keys=[id_vendeur])
    decorateur = db.relationship("User", foreign_keys=[id_deco])
    chauffeur = db.relationship("User", foreign_keys=[id_chauffeur])
    voiture = db.relationship("Vehicle")
    confirmation = db.relationship(
        "Confirmation",
        uselist=False,
        cascade="all, delete-orphan",
        back_populates="work",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "date_d": self.date_d,
            "date_f": self.date_f,
            "id_foire": self.id_foire,
            "id_stand": self.id_stand,
            "id_vendeur": self.id_vendeur,
            "id_deco": self.id_deco,
            "id_chauffeur": self.id_chauffeur,
            "id_voiture": self.id_voiture,
            "flow": self.flow,
            "foire_nom": self.foire.nom if self.foire else "",
            "stand_type": self.stand_type.type if self.stand_type else "",
            "vendeur_nom": (
                f"{self.vendeur.prenom} {self.vendeur.nom}".strip()
                if self.vendeur
                else ""
            ),
            "deco_nom": (
                f"{self.decorateur.prenom} {self.decorateur.nom}".strip()
                if self.decorateur
                else ""
            ),
            "chauffeur_nom": (
                f"{self.chauffeur.prenom} {self.chauffeur.nom}".strip()
                if self.chauffeur
                else ""
            ),
            "voiture_nom": (
                f"{self.voiture.model} — {self.voiture.immatricule}"
                if self.voiture
                else ""
            ),
            "confirmations": self.confirmation.to_dict() if self.confirmation else {
                "c_vendeur": False,
                "c_chauffeur": False,
                "c_deco": False,
            },
        }


class Confirmation(db.Model):
    __tablename__ = "Confirmations"

    id = db.Column(db.Integer, db.ForeignKey("works.id", ondelete="CASCADE"), primary_key=True)
    c_vendeur = db.Column(db.Boolean, nullable=False, default=False)
    c_chauffeur = db.Column(db.Boolean, nullable=False, default=False)
    c_deco = db.Column(db.Boolean, nullable=False, default=False)
    work = db.relationship("Work", back_populates="confirmation")

    def to_dict(self):
        return {
            "id": self.id,
            "c_vendeur": self.c_vendeur,
            "c_chauffeur": self.c_chauffeur,
            "c_deco": self.c_deco,
        }


class Permission(db.Model):
    __tablename__ = "droits"

    type_user = db.Column(db.String(50), primary_key=True)
    foire = db.Column(db.Boolean, nullable=False, default=False)
    stand = db.Column(db.Boolean, nullable=False, default=False)
    liste_stand = db.Column(db.Boolean, nullable=False, default=False)
    article = db.Column(db.Boolean, nullable=False, default=False)
    work = db.Column(db.Boolean, nullable=False, default=False)
    fournisseur = db.Column(db.Boolean, nullable=False, default=False)
    client = db.Column(db.Boolean, nullable=False, default=False)
    reservation = db.Column(db.Boolean, nullable=False, default=False)
    empl = db.Column(db.Boolean, nullable=False, default=False)
    voiture = db.Column(db.Boolean, nullable=False, default=False)
    mouvement = db.Column(db.Boolean, nullable=False, default=False)
    livraison = db.Column(db.Boolean, nullable=False, default=False)
    reception = db.Column(db.Boolean, nullable=False, default=False)
    vente = db.Column(db.Boolean, nullable=False, default=False)
    achat = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {
            "type_user": self.type_user,
            "foire": self.foire,
            "stand": self.stand,
            "liste_stand": self.liste_stand,
            "article": self.article,
            "work": self.work,
            "fournisseur": self.fournisseur,
            "client": self.client,
            "reservation": self.reservation,
            "empl": self.empl,
            "voiture": self.voiture,
            "mouvement": self.mouvement,
            "livraison": self.livraison,
            "reception": self.reception,
            "vente": self.vente,
            "achat": self.achat,
        }


class PosCustomer(db.Model):
    __tablename__ = "pos_customers"

    customer_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    name_key = db.Column(db.String(160), nullable=False, unique=True)
    phone = db.Column(db.String(40), nullable=False, default="")
    email = db.Column(db.String(254), nullable=False, default="")
    address = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    sales = db.relationship("PosSale", back_populates="customer")

    def to_dict(self):
        return {
            "customer_id": self.customer_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "created_at": self.created_at.isoformat(),
        }


class PosSupplier(db.Model):
    __tablename__ = "pos_suppliers"

    supplier_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    name_key = db.Column(db.String(160), nullable=False, unique=True)
    phone = db.Column(db.String(40), nullable=False, default="")
    email = db.Column(db.String(254), nullable=False, default="")
    address = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    purchases = db.relationship("PosPurchase", back_populates="supplier_record")

    def to_dict(self):
        return {
            "supplier_id": self.supplier_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "created_at": self.created_at.isoformat(),
        }


class PosProduct(db.Model):
    __tablename__ = "pos_products"

    product_id = db.Column(db.Integer, primary_key=True)
    article_ref = db.Column(
        db.String(50),
        db.ForeignKey("articles.ref", ondelete="RESTRICT"),
        nullable=True,
    )
    product_code = db.Column(db.String(120), nullable=False, unique=True)
    gen_name = db.Column(db.String(160), nullable=False)
    product_name = db.Column(db.String(255), nullable=False, default="")
    supplier = db.Column(db.String(160), nullable=False, default="")
    date_arrival = db.Column(db.String(10), nullable=False, default="")
    expiry_date = db.Column(db.String(10), nullable=False, default="")
    price = db.Column(db.Numeric(12, 2), nullable=False)
    o_price = db.Column(db.Numeric(12, 2), nullable=False)
    pricing_configured = db.Column(db.Boolean, nullable=False, default=True)
    qty = db.Column(db.Integer, nullable=False, default=0)
    qty_sold = db.Column(db.Integer, nullable=False, default=0)
    barcode = db.Column(db.String(120), nullable=True, index=True)
    article = db.relationship("Article")
    stock_movements = db.relationship(
        "PosStockMovement",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="PosStockMovement.movement_id.asc()",
    )

    def to_dict(self, include_cost=True):
        result = {
            "product_id": self.product_id,
            "article_ref": self.article_ref or "",
            "article_name": self.article.nom if self.article else "",
            "product_code": self.product_code,
            "gen_name": self.gen_name,
            "product_name": self.product_name,
            "supplier": self.supplier,
            "date_arrival": self.date_arrival,
            "expiry_date": self.expiry_date,
            "price": money_value(self.price),
            "pricing_configured": self.pricing_configured,
            "qty": self.qty,
            "qty_sold": self.qty_sold,
            "barcode": self.barcode or (self.article.barcode if self.article and self.article.barcode else (self.product_code or "")),
        }
        if include_cost:
            result["o_price"] = money_value(self.o_price)
            result["profit"] = money_value(self.price - self.o_price)
        return result


class PosSale(db.Model):
    __tablename__ = "pos_sales"

    transaction_id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(32), nullable=False, unique=True)
    cashier = db.Column(db.String(160), nullable=False)
    date = db.Column(db.Date, nullable=False)
    type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    profit = db.Column(db.Numeric(12, 2), nullable=False)
    paid_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    customer_name = db.Column(db.String(160), nullable=False, default="Client comptoir")
    customer_id = db.Column(
        db.Integer, db.ForeignKey("pos_customers.customer_id"), nullable=True
    )
    fair_id = db.Column(
        db.Integer, db.ForeignKey("foires.id", ondelete="RESTRICT"), nullable=True
    )
    seller_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    cashier_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    register_code = db.Column(db.String(64), nullable=True)
    cash_received = db.Column(db.Numeric(12, 2))
    due_date = db.Column(db.Date)
    customer = db.relationship("PosCustomer", back_populates="sales")
    fair = db.relationship("Fair")
    seller = db.relationship("User", foreign_keys=[seller_id])
    cashier_user = db.relationship("User", foreign_keys=[cashier_user_id])
    items = db.relationship(
        "PosSaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="PosSaleItem.transaction_id.asc()",
    )
    collections = db.relationship(
        "PosCollection",
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="PosCollection.collection_id.asc()",
    )

    def to_dict(self, include_items=False, include_profit=True, include_collections=False):
        paid_amount = self.paid_amount or self.amount * 0
        result = {
            "transaction_id": self.transaction_id,
            "invoice_number": self.invoice_number,
            "cashier": self.cashier,
            "date": self.date.isoformat(),
            "type": self.type,
            "amount": money_value(self.amount),
            "paid_amount": money_value(paid_amount),
            "balance": money_value(max(self.amount - paid_amount, self.amount * 0))
            if self.type == "credit"
            else 0,
            "customer_name": self.customer_name,
            "customer_id": self.customer_id,
            "fair_id": self.fair_id,
            "fair_name": self.fair.nom if self.fair else "",
            "seller_id": self.seller_id,
            "seller_name": (
                f"{self.seller.prenom} {self.seller.nom}".strip()
                if self.seller
                else ""
            ),
            "cashier_user_id": self.cashier_user_id,
            "cashier_user_name": (
                f"{self.cashier_user.prenom} {self.cashier_user.nom}".strip()
                if self.cashier_user
                else ""
            ),
            "cash_received": (
                money_value(self.cash_received) if self.cash_received is not None else None
            ),
            "change": (
                money_value(self.cash_received - self.amount)
                if self.cash_received is not None
                else None
            ),
            "due_date": self.due_date.isoformat() if self.due_date else None,
        }
        if include_profit:
            result["profit"] = money_value(self.profit)
        if include_items:
            result["items"] = [
                item.to_dict(include_profit=include_profit) for item in self.items
            ]
        if include_collections:
            result["collections"] = [payment.to_dict() for payment in self.collections]
        return result


class PosSaleItem(db.Model):
    __tablename__ = "pos_sale_items"

    transaction_id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(
        db.Integer, db.ForeignKey("pos_sales.transaction_id"), nullable=False
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("pos_products.product_id"), nullable=False
    )
    product_code = db.Column(db.String(120), nullable=False)
    gen_name = db.Column(db.String(160), nullable=False)
    product_name = db.Column(db.String(255), nullable=False, default="")
    qty = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    profit = db.Column(db.Numeric(12, 2), nullable=False)

    sale = db.relationship("PosSale", back_populates="items")

    def to_dict(self, include_profit=True):
        result = {
            "transaction_id": self.transaction_id,
            "product_id": self.product_id,
            "product_code": self.product_code,
            "gen_name": self.gen_name,
            "product_name": self.product_name,
            "qty": self.qty,
            "price": money_value(self.price),
            "amount": money_value(self.amount),
        }
        if include_profit:
            result["profit"] = money_value(self.profit)
        return result


class PosPurchase(db.Model):
    __tablename__ = "pos_purchases"

    purchase_id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(120), nullable=False, unique=True)
    date = db.Column(db.Date, nullable=False)
    supplier = db.Column(db.String(160), nullable=False)
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("pos_suppliers.supplier_id"), nullable=True
    )
    remarks = db.Column(db.String(500), nullable=False, default="")
    total = db.Column(db.Numeric(12, 2), nullable=False)
    supplier_record = db.relationship("PosSupplier", back_populates="purchases")
    items = db.relationship(
        "PosPurchaseItem",
        back_populates="purchase",
        cascade="all, delete-orphan",
        order_by="PosPurchaseItem.purchase_item_id.asc()",
    )

    def to_dict(self, include_items=False):
        result = {
            "purchase_id": self.purchase_id,
            "invoice_number": self.invoice_number,
            "date": self.date.isoformat(),
            "supplier": self.supplier,
            "supplier_id": self.supplier_id,
            "remarks": self.remarks,
            "total": money_value(self.total),
        }
        if include_items:
            result["items"] = [item.to_dict() for item in self.items]
        return result


class PosPurchaseItem(db.Model):
    __tablename__ = "pos_purchase_items"

    purchase_item_id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(
        db.Integer, db.ForeignKey("pos_purchases.purchase_id"), nullable=False
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("pos_products.product_id"), nullable=False
    )
    product_code = db.Column(db.String(120), nullable=False)
    gen_name = db.Column(db.String(160), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False)
    total_cost = db.Column(db.Numeric(12, 2), nullable=False)

    purchase = db.relationship("PosPurchase", back_populates="items")

    def to_dict(self):
        return {
            "purchase_item_id": self.purchase_item_id,
            "product_id": self.product_id,
            "product_code": self.product_code,
            "gen_name": self.gen_name,
            "qty": self.qty,
            "unit_cost": money_value(self.unit_cost),
            "total_cost": money_value(self.total_cost),
        }


class PosCollection(db.Model):
    __tablename__ = "pos_collections"

    collection_id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(
        db.Integer, db.ForeignKey("pos_sales.transaction_id"), nullable=False
    )
    date = db.Column(db.Date, nullable=False)
    invoice_number = db.Column(db.String(32), nullable=False, unique=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    remarks = db.Column(db.String(500), nullable=False, default="")
    sale = db.relationship("PosSale", back_populates="collections")

    def to_dict(self):
        return {
            "collection_id": self.collection_id,
            "sale_id": self.sale_id,
            "sale_invoice": self.sale.invoice_number if self.sale else "",
            "date": self.date.isoformat(),
            "invoice_number": self.invoice_number,
            "customer_name": self.sale.customer_name if self.sale else "",
            "amount": money_value(self.amount),
            "remarks": self.remarks,
        }


class PosStockMovement(db.Model):
    __tablename__ = "pos_stock_movements"

    movement_id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("pos_products.product_id"), nullable=False,
        index=True,
    )
    movement_type = db.Column(db.String(24), nullable=False)
    quantity_delta = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    reference_type = db.Column(db.String(24), nullable=False)
    reference_id = db.Column(db.Integer, nullable=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    product = db.relationship("PosProduct", back_populates="stock_movements")
    recorded_by = db.relationship("User")

    def to_dict(self, include_cost=True):
        result = {
            "movement_id": self.movement_id,
            "product_id": self.product_id,
            "product_code": self.product.product_code if self.product else "",
            "product_name": self.product.gen_name if self.product else "",
            "movement_type": self.movement_type,
            "quantity_delta": self.quantity_delta,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "recorded_by": (
                f"{self.recorded_by.prenom} {self.recorded_by.nom}".strip()
                if self.recorded_by
                else ""
            ),
            "created_at": self.created_at.isoformat(),
        }
        if include_cost:
            result["unit_cost"] = money_value(self.unit_cost)
        return result

class PosRegister(db.Model):
    __tablename__ = "pos_registers"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    nom = db.Column(db.String(160), nullable=False)
    fair_id = db.Column(db.Integer, db.ForeignKey("foires.id", ondelete="CASCADE"), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    fair = db.relationship("Fair")
    seller = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "nom": self.nom,
            "fair_id": self.fair_id,
            "fair_name": self.fair.nom if self.fair else "",
            "seller_id": self.seller_id,
            "seller_name": (
                f"{self.seller.prenom} {self.seller.nom}".strip()
                if self.seller
                else ""
            ),
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

