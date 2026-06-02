def build_mysql_url(host: str, port: int, database: str, username: str, password: str) -> str:
    return f"mysql+pymysql://{username}:{password}@{host}:{port or 3306}/{database}"
