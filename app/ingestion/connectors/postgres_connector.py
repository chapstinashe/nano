def build_postgres_url(host: str, port: int, database: str, username: str, password: str) -> str:
    return f"postgresql+psycopg2://{username}:{password}@{host}:{port or 5432}/{database}"
