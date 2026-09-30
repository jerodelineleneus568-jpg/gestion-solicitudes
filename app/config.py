import os
import secrets

class Config:
    # SECRET_KEY fija para que no invalide las sesiones ni los tokens CSRF
    SECRET_KEY = os.environ.get('SECRET_KEY', 'secreto-fijo-solicitudes-2026-seguro')
    
    # Base de datos SQLite
    DATABASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'solicitudes.db')

    # Seguridad CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Sin límite de tiempo estricto durante pruebas

    # Cookies de sesión HTTPS
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'