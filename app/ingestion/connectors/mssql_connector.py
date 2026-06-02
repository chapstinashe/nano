def build_mssql_url(host: str, port: int, database: str, username: str, password: str) -> str:
    return (
        f"mssql+pyodbc://{username}:{password}@{host}:{port or 1433}/{database}"
        "?driver=ODBC+Driver+17+for+SQL+Server"
    )
