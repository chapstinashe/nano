import uuid

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "csv", "xlsx"}


def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_uuid(value: str, field_name: str = "id") -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    try:
        uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}") from exc
    return value


def validate_upload_magic(path: str, extension: str) -> None:
    ext = extension.lower()
    with open(path, "rb") as handle:
        header = handle.read(8)

    if ext == "pdf" and not header.startswith(b"%PDF"):
        raise ValueError("File content does not match PDF format")
    if ext in {"docx", "xlsx"} and not header.startswith(b"PK\x03\x04"):
        raise ValueError(f"File content does not match {ext.upper()} format")
    if ext in {"txt", "csv"}:
        with open(path, "rb") as handle:
            sample = handle.read(8192)
        if b"\x00" in sample:
            raise ValueError("Text uploads must not contain binary data")
