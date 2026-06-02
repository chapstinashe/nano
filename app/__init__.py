from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import timedelta

from app.api.routes_auth import bp as auth_bp
from app.api.routes_chat import bp as chat_bp
from app.api.routes_chats import bp as chats_bp
from app.api.routes_documents import bp as documents_bp
from app.api.routes_health import bp as health_bp
from app.api.routes_ingest import bp as ingest_bp
from app.api.routes_preferences import bp as preferences_bp
from app.api.routes_embed import bp as embed_bp
from app.api.routes_retrieval import bp as retrieval_bp
from app.api.routes_search import bp as search_bp
from app.api.routes_session import bp as session_bp
from app.api.routes_ui import bp as ui_bp
from app.core.config import Config
from app.core.logging import setup_logging
from app.core.request_audit import register_audit_hooks
from app.core.rate_limit import init_limiter
from app.db.blob_storage import require_blob_storage
from app.db.cosmos import ensure_all_containers, require_cosmos


def create_app() -> Flask:
    setup_logging()
    Config.ensure_storage_dirs()

    if Config.AUTH_ENABLED and not Config.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY must be set when AUTH_ENABLED=1")

    if Config.AUTH_ENABLED:
        require_cosmos()
        require_blob_storage()

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_UPLOAD_BYTES
    app.config["JWT_SECRET_KEY"] = Config.JWT_SECRET_KEY
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=Config.JWT_ACCESS_EXPIRES_MIN)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=Config.JWT_REFRESH_EXPIRES_DAYS)
    app.config["JWT_TOKEN_LOCATION"] = ["cookies", "headers"]
    app.config["JWT_COOKIE_SECURE"] = Config.COOKIE_SECURE
    app.config["JWT_COOKIE_HTTPONLY"] = True
    app.config["JWT_COOKIE_SAMESITE"] = Config.COOKIE_SAMESITE
    app.config["JWT_ACCESS_COOKIE_NAME"] = Config.JWT_ACCESS_COOKIE_NAME
    app.config["JWT_REFRESH_COOKIE_NAME"] = Config.JWT_REFRESH_COOKIE_NAME
    app.config["JWT_COOKIE_CSRF_PROTECT"] = Config.AUTH_ENABLED
    app.config["JWT_CSRF_IN_COOKIES"] = True
    app.config["JWT_ACCESS_CSRF_COOKIE_NAME"] = Config.JWT_CSRF_ACCESS_COOKIE_NAME
    app.config["JWT_REFRESH_CSRF_COOKIE_NAME"] = Config.JWT_CSRF_REFRESH_COOKIE_NAME
    app.config["JWT_ACCESS_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"
    app.config["JWT_REFRESH_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"
    JWTManager(app)

    if Config.ALLOWED_ORIGINS:
        CORS(app, origins=Config.ALLOWED_ORIGINS, supports_credentials=True)
    elif Config.FLASK_DEBUG:
        CORS(
            app,
            origins=[
                f"http://localhost:{Config.FLASK_PORT}",
                f"http://127.0.0.1:{Config.FLASK_PORT}",
            ],
            supports_credentials=True,
        )

    init_limiter(app)
    register_audit_hooks(app)

    from app.core.audit import log_security_event

    log_security_event(
        "app.started",
        category="system",
        details={
            "auth_enabled": Config.AUTH_ENABLED,
            "rate_limit_enabled": Config.RATE_LIMIT_ENABLED,
            "debug": Config.FLASK_DEBUG,
        },
    )

    app.register_blueprint(ui_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(chats_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(retrieval_bp)
    app.register_blueprint(embed_bp)
    app.register_blueprint(session_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(preferences_bp)

    try:
        ensure_all_containers()
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Cosmos DB initialization failed. Check COSMOS_* settings, enable Vector Search "
            "for NoSQL on the account, and ensure database '%s' is accessible.",
            Config.COSMOS_DATABASE,
        )
        raise

    _last_cleanup_at = {"value": 0.0}

    @app.before_request
    def run_periodic_cleanup():
        import time

        from app.services.document_ttl_service import cleanup_expired_documents
        from app.services.guest_session_service import cleanup_expired_sessions

        now = time.time()
        if now - _last_cleanup_at["value"] < 900:
            return
        _last_cleanup_at["value"] = now
        try:
            cleanup_expired_sessions()
            cleanup_expired_documents()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Periodic data cleanup failed")

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if Config.COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.errorhandler(413)
    def request_too_large(error):
        return {"error": "Upload exceeds maximum allowed size"}, 413

    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Not found"}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {"error": "Internal server error"}, 500

    return app
