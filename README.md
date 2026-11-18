# OKBA Inter — version React et Flask

Cette copie contient le frontend React et le backend Flask migrés. Les fichiers
PHP ne sont pas inclus. La base SQLite est copiée dans `backend/database/app.db`;
elle est séparée de celle du projet d’origine.

## Prérequis

- Python 3.10 ou plus récent
- Une connexion Internet pour charger React 18 depuis unpkg

## Démarrer le backend

Dans PowerShell, depuis ce dossier :

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Le backend écoute sur `http://localhost:5100`.

Pour lancer les tests de l’API, dans un autre terminal depuis `backend` :

```powershell
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -v
```

## Importer l’ancienne base MySQL

Le fichier SQL historique est importé sans exécuter ses instructions DDL : seuls
les enregistrements des tables connues sont convertis. Commencer par afficher
le résumé, sans modifier la base :

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python .\import_legacy_sql.py "C:\chemin\vers\okba6.sql"
```

Après vérification du résumé, appliquer l’import :

```powershell
python .\import_legacy_sql.py "C:\chemin\vers\okba6.sql" --apply
```

L’import est destiné à une base migrée vide (à l’exception du compte
administrateur initial) ; les autres données déjà présentes bloquent
l’opération. Une copie datée de la base SQLite est créée avant l’import. Les
mots de passe hérités sont hachés. Les champs historiques repris par
l’application (ville, spécialité, location des véhicules, type de commerce et
état/date de confirmation des réservations) sont conservés dans les tables
métier. Les autres champs et les enregistrements dont les références sont
invalides sont conservés dans `legacy_import_extras` pour vérification, au lieu
d’être silencieusement supprimés.

La base fournie `backend/database/app.db` a été importée depuis `okba6.sql`.
Elle contient notamment 692 articles, 10 utilisateurs, 3 foires, 3 réservations,
5 missions et 3 réceptions. L’export contenait aussi 2 confirmations de missions
absentes et 1 réception liée à un article introuvable ; ces 3 enregistrements
ont été archivés. Trois réceptions sont importées sans lien fournisseur, car
leurs références fournisseur n’existent pas dans l’export.
Les tables historiques de ventes, achats et livraisons ne contenaient pas de
lignes. Le dump ne contient pas non plus les tables de l’ancien POS (produits,
clients/fournisseurs POS, ventes, achats et encaissements) : les écrans POS
migrés sont fonctionnels, mais leurs anciennes données ne peuvent pas être
importées depuis ce fichier.

La base POS est créée dans le même fichier `backend/database/app.db` pour
partager l’authentification et les sauvegardes de l’application. Elle comprend
les tables `pos_products`, `pos_customers`, `pos_suppliers`, `pos_sales`,
`pos_sale_items`, `pos_purchases`, `pos_purchase_items`, `pos_collections` et
`pos_stock_movements`. Les ventes, achats, paiements partiels, contacts et
mouvements de stock sont liés entre eux. Le journal conserve les entrées
initiales, achats, ventes et ajustements manuels ; les coûts unitaires du
journal ne sont visibles que pour l’administrateur.

Un produit POS peut être associé à un article du stock général à partir de
l’onglet Produits de la caisse. Au moment de l’association, les stocks doivent
être égaux ; la caisse reprend alors la référence, le nom et la quantité de
l’article. Ensuite, ventes, achats, ajustements POS et mouvements du stock
général mettent à jour les deux vues de ce stock partagé. Un article lié ne
peut pas être supprimé ni changer de référence. Les prix de vente et de revient
restent spécifiques au POS.

## Migrations du schéma

Les nouvelles évolutions de schéma sont enregistrées dans
`backend/app/schema_migrations.py` et suivies dans `schema_migrations`. Au
démarrage, une migration manquante est précédée d’une copie SQLite créée avec
l’API de sauvegarde SQLite, puis vérifiée avec `integrity_check` et
`foreign_key_check`. La copie est conservée à côté de la base sous le nom
`app.before-schema-<horodatage>.bak`. Si la copie échoue ou est invalide, le
démarrage s’arrête avant la modification du schéma.

Les migrations sont transactionnelles et vérifient les colonnes existantes
avant de les ajouter ; elles peuvent donc être relancées sans dupliquer les
colonnes ni les versions appliquées. Les anciennes valeurs des foires restent
inchangées : les nouvelles dates et le statut ne sont pas déduits des champs
historiques.

L’administration peut définir la devise générale depuis **Paramètres**. Le
code ISO 4217 est utilisé pour formater les montants du POS ; la valeur par
défaut est `TND`. Les dates de début/fin et d’envoi des produits, l’organisateur,
le statut et les notes de gestion se modifient dans **Foires**. La fin ne peut
pas précéder le début, la date d’envoi doit être au plus tard le début de la
foire et une justification est exigée si l’envoi tardif est autorisé.

Les affectations d’équipe se gèrent depuis **Équipe des foires**. La recherche
de disponibilité propose les membres du rôle choisi sans créer d’affectation ;
un responsable confirme explicitement chaque choix. Les chevauchements avec
une affectation confirmée, une réservation ou une mission existante sont
signalés et bloquent l’enregistrement. Les affectations sont conservées dans
`fair_assignments` et leur migration est sauvegardée et versionnée.

À la création d’une foire, l’option **Affecter automatiquement** est activée
par défaut : les dates sont obligatoires et un vendeur, un chauffeur et un
véhicule disponibles sont affectés pour toute la période. Le véhicule peut
être choisi comme préférence ; s’il n’est pas disponible, un autre véhicule
libre est retenu. Les réservations, missions, affectations confirmées et
périodes de location sont prises en compte. Si l’équipe ou le véhicule requis
manque, la foire n’est pas créée ; l’option peut être désactivée pour préparer
la foire et faire les affectations manuellement. Le vendeur affecté crée le
contexte de POS de la foire ; celui-ci est utilisable pendant ses dates.
L’affectation du décorateur reste manuelle.

Le module **Stock des foires** sépare les quantités de chaque foire. Il permet
de transférer du stock général vers la foire ou de le retourner, ainsi que de
consigner les réceptions, ventes, retours clients et pertes. Un transfert met
à jour les deux stocks et le stock POS lié dans une même transaction ; un stock
insuffisant annule l’opération. Les mouvements de foire sont append-only : une
correction doit être enregistrée par un mouvement compensatoire, jamais par la
modification ou la suppression de l’historique.

Chaque compte de type vendeur ne voit que les ventes et encaissements qui lui
sont attribués, et ne peut ouvrir une caisse de foire que lorsqu’il y est
affecté. Il ne peut pas enregistrer une vente pour un autre vendeur. Le
responsable conserve l’accès à l’ensemble des caisses et à leurs rapports.

La caisse permet aussi de choisir une foire active et un vendeur qui y est
affecté aujourd’hui. Une vente de foire exige des produits liés à des articles
et disponibles dans le stock de cette foire ; elle diminue ce stock et ajoute
un mouvement de vente sans diminuer une seconde fois le stock général. La
vente conserve la foire et le vendeur ; chaque nouvelle vente enregistre aussi
le compte opérateur connecté. L’historique, les reçus et le rapport affichent
le contexte de foire ; le rapport peut être filtré par foire et vendeur. Les
ventes antérieures gardent leurs champs de contexte à `NULL` : aucune foire,
aucun vendeur ni compte opérateur n’est déduit rétroactivement.
L’onglet administrateur **Rapport des foires** récapitule le nombre de ventes,
le chiffre d’affaires et la marge par foire et par vendeur, avec filtres de
dates. Toutes les nouvelles ventes POS doivent être rattachées à une foire ;
les éventuelles ventes historiques sans contexte sont affichées séparément.

Dans **Caisse > Produits**, l’administrateur peut créer les produits POS
manquants à partir des articles existants. Chaque produit reprend sa référence,
son nom, sa description et son stock courant, sans modifier le stock général.
Les prix de revient et de vente sont initialisés à zéro ; le produit reste
invendable jusqu’à leur configuration et à l’activation explicite de l’option
**Prix configurés**. L’import est idempotent et ignore les articles déjà liés.

Le démarrage du backend crée/complète le schéma POS de manière additive et
enregistre le stock initial des produits POS déjà présents. Aucun produit,
prix ou lien n’est inventé à partir de l’ancienne base : vérifiez et associez
les produits depuis l’interface d’administration. Les 3 réceptions historiques
restent disponibles dans le module Stock général. Les mots de passe des comptes
importés sont hachés ; il est recommandé à l’administrateur de les renouveler
après la première connexion.

## Démarrer le frontend

Dans un deuxième terminal PowerShell, depuis ce dossier :

```powershell
cd frontend
python -m http.server 8000
```

Ouvrir ensuite `http://localhost:8000`.

Si la base ne contient aucun utilisateur, créer le compte initial en envoyant
une requête `POST` à `http://localhost:5100/api/seed`, puis modifier son mot de
passe dès la première connexion.

## Tester gratuitement sur PythonAnywhere

Le backend sert aussi l’interface React à `/` et ses fichiers sous `/src/`.
L’URL de l’API est remplacée par `/api`, ainsi l’interface et l’API restent sur
la même origine. `backend/wsgi.py` expose l’application Flask à l’hébergeur.
React est chargé depuis un CDN par le navigateur.

### Créer une base de démonstration sans données privées

Depuis PowerShell, dans `backend/` :

```powershell
.\.venv\Scripts\Activate.ps1
python .\create_demo_database.py
```

Cette commande crée `backend/database/app.demo.db`, qui contient seulement
trois produits fictifs liés à des articles fictifs, avec un stock de test.
Elle refuse d’écraser une base existante et ne touche pas à `app.db`. Aucun
compte n’est inclus dans la base de démonstration.

### Publier l’application

1. Créer un compte PythonAnywhere gratuit et une application Web avec
   **Manual configuration**, pour une version de Python compatible avec
   `requirements.txt`.
2. Téléverser le dossier du projet et la base `backend/database/app.demo.db`
   dans l’espace de fichiers du compte. Ne pas téléverser `app.db`, les fichiers
   `*.bak`, ni un fichier contenant les vraies données de l’entreprise.
3. Dans une console Bash de PythonAnywhere, créer un environnement virtuel et
   installer les dépendances :

   ```bash
   cd ~/okba2new-migre/backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Dans le fichier WSGI donné par l’onglet **Web**, ajouter le chemin du dossier
   `backend`, puis définir les variables d’environnement avant d’importer
   `wsgi`. Remplacer `USERNAME` par le nom de compte PythonAnywhere et générer
   une clé secrète privée avec `python -c "import secrets; print(secrets.token_hex(32))"`.
   Ne pas publier cette clé dans le dépôt ou dans une capture d’écran :

   ```python
   import os
   import sys

   backend = "/home/USERNAME/okba2new-migre/backend"
   if backend not in sys.path:
       sys.path.insert(0, backend)

   os.environ["APP_ENV"] = "production"
   os.environ["SECRET_KEY"] = "REMPLACER_PAR_UNE_CLE_ALEATOIRE_PRIVEE"
   os.environ["DATABASE_URL"] = (
       "sqlite:////home/USERNAME/okba2new-migre/"
       "backend/database/app.demo.db"
   )
   from wsgi import application
   ```

5. Dans la console Bash, créer le premier administrateur interactif. Utiliser
   les mêmes valeurs privées pour `SECRET_KEY` et `DATABASE_URL` que dans la
   configuration WSGI :

   ```bash
   cd ~/okba2new-migre/backend
   source .venv/bin/activate
   export APP_ENV=production
   export SECRET_KEY='LA_MEME_CLE_PRIVEE_QUE_DANS_LE_FICHIER_WSGI'
   export DATABASE_URL='sqlite:////home/USERNAME/okba2new-migre/backend/database/app.demo.db'
   python create_admin.py
   ```

   Le mot de passe est demandé de manière masquée et n’est pas affiché. En
   production, `/api/seed` est désactivé pour empêcher la création publique
   d’un compte par défaut.
6. Recharger l’application Web depuis l’onglet **Web**, puis ouvrir l’adresse
   `https://USERNAME.pythonanywhere.com`.

L’offre gratuite convient à une démonstration seulement : vérifier les limites
actuelles de l’hébergeur et faire des sauvegardes. Garder SQLite dans l’espace
de fichiers persistant du compte, sauvegarder ce fichier séparément et ne pas
utiliser la base de démonstration pour de vraies ventes. Aucun hébergement n’est
créé automatiquement et aucun fichier n’est téléversé depuis cette session.

## Contenu

- `frontend/` : interface React
- `backend/` : API Flask, modèles SQLAlchemy et base SQLite
- Les modules migrés comprennent les clients, articles, fournisseurs, stock,
  caisse, foires, réservations, véhicules, stands, missions et droits par rôle.

L’environnement virtuel Python n’est pas copié. Il est recréé dans `backend/`
avec les commandes ci-dessus.


## Nouvelles Fonctionnalités & Améliorations (Version enrichie)

1. **Tableau de bord Direction (`/api/dashboard`)** :
   - Cartes d'indicateurs clés (KPIs) : Total articles, clients, fournisseurs, utilisateurs, foires actives/à venir.
   - Suivi financier du jour, de la semaine, du mois et total des créances en cours.
   - Top 5 des produits les plus vendus et 5 dernières ventes en temps réel.
   - Alertes sur articles en rupture/stock faible et produits sans prix configuré.

2. **Centre d'alertes & notifications (`/api/alerts`)** :
   - Badge dynamique avec compteur d'alertes dans la barre supérieure.
   - Vue dédiée récapitulant les stocks critiques (seuil < 10), créances échues et foires prévues dans les 7 prochains jours.

3. **Exports CSV & Reçus de caisse** :
   - Boutons « Exporter CSV » sur les catalogues Articles, Clients, Fournisseurs et Historique des ventes.
   - Reçu imprimable dédié (`/api/pos/sales/<id>/receipt`) optimisé pour imprimante thermique ou standard, en plus de l'impression directe.

4. **Pagination & Ergonomie** :
   - Composant de pagination réutilisable intégré aux listes (Articles, Clients, Fournisseurs).
   - Prise en compte automatique de la préférence utilisateur `lpp` (lignes par page).
   - Raccourcis caisse (F2 pour la recherche produit immédiate, Échap pour annuler).

5. **Sécurité & Traçabilité** :
   - Protection contre les attaques par force brute (Rate Limiting sur `/api/login` : 5 tentatives max / 5 min par IP).
   - Durcissement des cookies de session (`HTTPOnly`, `SameSite=Lax`).
   - Journal d'audit (`audit_logger`) enregistrant les connexions, déconnexions, suppressions sensibles et exports CSV.
   - Fichier `.gitignore` protégeant les bases, fichiers `.bak`, environnements virtuels et variables secrètes.
