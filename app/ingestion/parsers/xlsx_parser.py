import pandas as pd

from app.ingestion.parsers.csv_parser import _dataframe_to_text


def parse_xlsx(file_path: str) -> str:
    sheets = pd.read_excel(file_path, sheet_name=None)
    parts: list[str] = []
    for sheet_name, df in sheets.items():
        parts.append(f"Sheet: {sheet_name}\n{_dataframe_to_text(df)}")
    return "\n\n".join(parts).strip()
