import os
import secrets

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    DATABASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'solicitudes.db')
    
    # Parámetros de seguridad en cookies de sesión
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False  # Cambiar a True en producción con HTTPS