import os
import secrets

class Config:
    # A02 - Cryptographic Failures: Generación de clave criptográfica fuerte
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    DATABASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'solicitudes.db')
    
    # A07 - Identification & Authentication / A05 - Security Misconfiguration
    SESSION_COOKIE_HTTPONLY = True          # Impide acceso a cookies vía JavaScript
    SESSION_COOKIE_SECURE = True            # Solo transmite cookies sobre HTTPS/TLS
    SESSION_COOKIE_SAMESITE = 'Strict'      # Protección estricta contra CSRF
    PERMANENT_SESSION_LIFETIME = 1800       # 30 minutos de tiempo de vida