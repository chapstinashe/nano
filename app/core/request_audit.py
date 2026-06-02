import time

from flask import g, request

from app.core.audit import audit_failure, get_request_id, log_security_event, setup_audit_logging
from app.core.auth import get_current_user_context

SKIP_ACCESS_PATHS = frozenset({"/api/health"})


def register_audit_hooks(app) -> None:
    setup_audit_logging()

    @app.before_request
    def start_request_timer():
        g.request_started_at = time.time()
        get_request_id()

    @app.after_request
    def audit_api_access(response):
        if not request.path.startswith("/api/"):
            return response
        if request.path in SKIP_ACCESS_PATHS:
            return response

        duration_ms = None
        started = getattr(g, "request_started_at", None)
        if started is not None:
            duration_ms = int((time.time() - started) * 1000)

        status_code = response.status_code
        outcome = "success" if status_code < 400 else "failure"
        severity = "info"
        event = "api.access"

        if status_code == 429:
            event = "rate_limit.exceeded"
            severity = "warning"
        elif status_code >= 500:
            severity = "critical"
        elif status_code >= 400:
            severity = "warning"

        user_id = ""
        actor = {}
        try:
            user = get_current_user_context(touch_guest_session=False)
            user_id = user.get("user_id", "")
            actor = {
                "role": user.get("role", ""),
                "authenticated": bool(user.get("is_authenticated")),
                "session_id": user.get("session_id", ""),
            }
        except Exception:
            pass

        log_security_event(
            event,
            category="access",
            severity=severity,
            user_id=user_id,
            outcome=outcome,
            status_code=status_code,
            duration_ms=duration_ms,
            details={"actor": actor},
        )
        return response

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        audit_failure(
            "rate_limit.exceeded",
            category="security",
            severity="warning",
            status_code=429,
            reason="Too many requests",
            path=request.path,
        )
        return {"error": "Rate limit exceeded. Please try again later."}, 429
