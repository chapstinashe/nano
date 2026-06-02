GENERIC_500 = "Internal server error"
GENERIC_503 = "Service temporarily unavailable"


def client_error(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, RuntimeError):
        return str(exc)
    return GENERIC_500
