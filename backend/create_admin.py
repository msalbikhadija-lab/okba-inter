import getpass
import os


def main():
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Définissez DATABASE_URL vers la base de démonstration avant de continuer.")
    if not os.environ.get("APP_ENV") == "production":
        raise SystemExit("Définissez APP_ENV=production avant de créer le compte serveur.")
    if not os.environ.get("SECRET_KEY"):
        raise SystemExit("Définissez SECRET_KEY dans l’environnement du serveur.")

    from app import create_app, db
    from app.models import User
    from werkzeug.security import generate_password_hash

    app = create_app()
    with app.app_context():
        if User.query.first() is not None:
            raise SystemExit("Un compte existe déjà ; aucun administrateur n’a été modifié.")

        nom = input("Nom de l’administrateur : ").strip()
        prenom = input("Prénom de l’administrateur : ").strip()
        login = input("Identifiant de connexion : ").strip()
        password = getpass.getpass("Mot de passe (8 caractères minimum) : ")
        confirmation = getpass.getpass("Confirmer le mot de passe : ")
        if not nom or not prenom or not login:
            raise SystemExit("Le nom, le prénom et l’identifiant sont obligatoires.")
        if len(password) < 8:
            raise SystemExit("Le mot de passe doit contenir au moins 8 caractères.")
        if password != confirmation:
            raise SystemExit("Les mots de passe ne correspondent pas.")
        if User.query.filter_by(login=login).first():
            raise SystemExit("Cet identifiant est déjà utilisé.")

        db.session.add(
            User(
                nom=nom,
                prenom=prenom,
                login=login,
                pw=generate_password_hash(password),
                type="admin",
                lpp=8,
            )
        )
        db.session.commit()
        print("Compte administrateur créé. Le mot de passe n’a pas été affiché.")


if __name__ == "__main__":
    main()
