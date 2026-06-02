def build_sqlite_url(host: str, port: int, database: str, username: str, password: str) -> str:
    return f"sqlite:///{database}"
