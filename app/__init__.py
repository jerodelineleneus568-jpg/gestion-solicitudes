from flask import Flask
from flask_wtf.csrf import CSRFProtect
from app.config import Config
from app.models.solicitud_model import SolicitudModel

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # A01 & A08 - Validación global de tokens CSRF
    csrf.init_app(app)

    with app.app_context():
        SolicitudModel.init_db()

    from app.controllers.solicitud_controller import solicitud_bp
    from app.controllers.export_controller import export_bp
    app.register_blueprint(solicitud_bp)
    app.register_blueprint(export_bp)

    # A05 - Security Misconfiguration: Cabeceras defensivas estrictas
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # HSTS (Strict-Transport-Security): Forzar HTTPS por 1 año
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        # CSP restrictiva
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:;"
        )
        return response

    return app