from flask import request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.core.config import Config
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _rate_limit_key() -> str:
    if Config.AUTH_ENABLED:
        try:
            verify_jwt_in_request(optional=True)
            identity = get_jwt_identity()
            if identity:
                return f"user:{identity}"
        except Exception:
            pass
    session_id = (request.cookies.get("nano_session_id") or request.headers.get("X-Session-Id") or "").strip()
    if session_id:
        return f"session:{session_id}"
    return get_remote_address()


limiter = Limiter(key_func=_rate_limit_key, default_limits=[])


def init_limiter(app) -> None:
    if not Config.RATE_LIMIT_ENABLED:
        return
    storage_uri = Config.RATE_LIMIT_STORAGE_URI or "memory://"
    app.config["RATELIMIT_STORAGE_URI"] = storage_uri
    limiter.init_app(app)
