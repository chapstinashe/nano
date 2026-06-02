import re

DISPOSABLE_EMAIL_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.net",
        "tempmail.com",
        "10minutemail.com",
        "throwaway.email",
        "yopmail.com",
        "sharklasers.com",
        "getnada.com",
        "trashmail.com",
    }
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_registration_request(email: str, password: str, honeypot: str = "") -> str:
    if honeypot:
        raise ValueError("Registration rejected")

    normalized_email = (email or "").strip().lower()
    if not normalized_email or not EMAIL_PATTERN.match(normalized_email):
        raise ValueError("Valid email is required")

    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters")

    domain = normalized_email.rsplit("@", 1)[-1]
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        raise ValueError("Disposable email addresses are not allowed")

    return normalized_email
