import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in {"1", "true"}
    app.run(host="0.0.0.0", port=5100, debug=debug)
