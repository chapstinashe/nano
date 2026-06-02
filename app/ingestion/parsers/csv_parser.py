import pandas as pd


def parse_csv(file_path: str) -> str:
    df = pd.read_csv(file_path)
    return _dataframe_to_text(df)


def _dataframe_to_text(df: pd.DataFrame) -> str:
    rows = []
    for _, row in df.iterrows():
        parts = [f"{col}: {row[col]}" for col in df.columns]
        rows.append(" | ".join(str(p) for p in parts))
    return "\n".join(rows).strip()
