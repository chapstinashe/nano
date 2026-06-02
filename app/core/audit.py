import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import g, has_request_context, request

logger = logging.getLogger("security.audit")

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "refresh_token",
        "access_token",
        "connection_string",
        "token",
        "secret",
        "authorization",
    }
)


def _client_ip() -> str:
    if not has_request_context():
        return ""
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.remote_addr or ""


def get_request_id() -> str:
    if not has_request_context():
        return str(uuid.uuid4())
    existing = getattr(g, "request_id", None)
    if existing:
        return existing
    incoming = (request.headers.get("X-Request-Id") or "").strip()
    g.request_id = incoming or str(uuid.uuid4())
    return g.request_id


def _mask_email(value: str) -> str:
    email = (value or "").strip().lower()
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _sanitize_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered in SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, str):
        if lowered.endswith("email") or lowered == "email":
            return _mask_email(value)
        if lowered in {"query", "answer", "text"}:
            return _truncate_text(value)
        if EMAIL_PATTERN.fullmatch(value.strip()):
            return _mask_email(value)
    if isinstance(value, dict):
        return _sanitize_details(value)
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value[:20]]
    return value


def _truncate_text(text: str, limit: int = 120) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "…"


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        sanitized[key] = _sanitize_value(key, value)
    return sanitized


def _http_context(*, status_code: int | None = None) -> dict[str, Any]:
    if not has_request_context():
        return {}
    return {
        "method": request.method,
        "path": request.path,
        "status_code": status_code,
        "ip": _client_ip(),
        "user_agent": (request.headers.get("User-Agent") or "")[:200],
        "origin": request.headers.get("Origin") or "",
        "referer": (request.headers.get("Referer") or "")[:200],
    }


def log_security_event(
    event: str,
    *,
    category: str = "security",
    severity: str = "info",
    user_id: str = "",
    outcome: str = "success",
    status_code: int | None = None,
    duration_ms: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema": "nano.audit.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": get_request_id(),
        "event": event,
        "category": category,
        "severity": severity,
        "outcome": outcome,
        "user_id": user_id or "",
        "http": _http_context(status_code=status_code),
        "details": _sanitize_details(details or {}),
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms

    line = json.dumps(payload, default=str, ensure_ascii=True)
    if severity == "critical":
        logger.critical(line)
    elif severity == "warning":
        logger.warning(line)
    else:
        logger.info(line)


def audit_actor(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user.get("user_id", ""),
        "role": user.get("role", ""),
        "authenticated": bool(user.get("is_authenticated")),
        "session_id": user.get("session_id", ""),
        "email": _mask_email(user.get("email", "")),
    }


def audit_action(
    event: str,
    user: dict[str, Any],
    *,
    category: str = "security",
    severity: str = "info",
    outcome: str = "success",
    status_code: int | None = None,
    duration_ms: int | None = None,
    **details: Any,
) -> None:
    merged = {"actor": audit_actor(user), **details}
    log_security_event(
        event,
        category=category,
        severity=severity,
        user_id=user.get("user_id", ""),
        outcome=outcome,
        status_code=status_code,
        duration_ms=duration_ms,
        details=merged,
    )


def audit_failure(
    event: str,
    *,
    category: str = "security",
    severity: str = "warning",
    user_id: str = "",
    reason: str = "",
    status_code: int | None = None,
    **details: Any,
) -> None:
    merged = {"reason": reason, **details}
    log_security_event(
        event,
        category=category,
        severity=severity,
        user_id=user_id,
        outcome="failure",
        status_code=status_code,
        details=merged,
    )


def setup_audit_logging() -> None:
    audit_logger = logging.getLogger("security.audit")
    if any(isinstance(handler, logging.StreamHandler) for handler in audit_logger.handlers):
        return

    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(handler)
