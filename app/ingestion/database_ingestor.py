import logging
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, inspect

from app.ingestion.connectors.postgres_connector import build_postgres_url
from app.ingestion.connectors.mysql_connector import build_mysql_url
from app.ingestion.connectors.mssql_connector import build_mssql_url
from app.ingestion.connectors.sqlite_connector import build_sqlite_url

logger = logging.getLogger(__name__)

BUILDERS = {
    "postgresql": build_postgres_url,
    "mysql": build_mysql_url,
    "mssql": build_mssql_url,
    "sqlite": build_sqlite_url,
}


class DatabaseIngestor:
    def read_tables(
        self,
        connection_string: str,
        tables: list[str],
        db_type: str = "postgresql",
    ) -> list[dict[str, Any]]:
        engine = create_engine(connection_string)
        documents: list[dict[str, Any]] = []

        inspector = inspect(engine)
        available = set(inspector.get_table_names())
        for table in tables:
            if table not in available:
                logger.warning("Table not found: %s", table)
                continue
            df = pd.read_sql_table(table, engine)
            for _, row in df.iterrows():
                text_content = " | ".join(f"{col}: {row[col]}" for col in df.columns)
                documents.append(
                    {
                        "text": text_content,
                        "metadata": {
                            "table": table,
                            "source_type": "database",
                            "db_type": db_type,
                        },
                    }
                )
        return documents

    def build_connection_string(
        self,
        db_type: str,
        host: str = "",
        port: int = 0,
        database: str = "",
        username: str = "",
        password: str = "",
        connection_string: str = "",
    ) -> str:
        if connection_string:
            return connection_string
        builder = BUILDERS.get(db_type)
        if not builder:
            raise ValueError(f"Unsupported database type: {db_type}")
        return builder(host, port, database, username, password)
