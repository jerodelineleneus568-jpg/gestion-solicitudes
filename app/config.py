import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")

    DATABASE_PATH = str(BASE_DIR / "app" / "solicitudes.db")
    UPLOAD_FOLDER = str(BASE_DIR / "uploads")

    RAYEN_USUARIO = os.environ.get("RAYEN_USUARIO", "")
    RAYEN_CONTRASENA = os.environ.get("RAYEN_CONTRASENA", "")
    RAYEN_HEADLESS = (
        os.environ.get("RAYEN_HEADLESS", "false").lower() == "true"
    )

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Tu aplicación se ejecuta mediante HTTPS en el puerto 8443.
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"