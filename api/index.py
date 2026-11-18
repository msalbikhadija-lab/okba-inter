import os
import sys
import shutil

# Adapter le path pour Vercel Serverless
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Gestion de SQLite sur Vercel Serverless (copie dans /tmp pour écriture temporaire)
TMP_DB_DIR = "/tmp/database"
os.makedirs(TMP_DB_DIR, exist_ok=True)
ORIGINAL_DB = os.path.join(BACKEND_DIR, "database", "app.db")
TARGET_DB = os.path.join(TMP_DB_DIR, "app.db")

if os.path.exists(ORIGINAL_DB) and not os.path.exists(TARGET_DB):
    try:
        shutil.copy2(ORIGINAL_DB, TARGET_DB)
    except Exception:
        pass

os.environ["DATABASE_URL"] = f"sqlite:///{TARGET_DB}"
os.environ["APP_ENV"] = "production"
if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "vercel-demo-secret-key-okba"

from wsgi import application

app = application
