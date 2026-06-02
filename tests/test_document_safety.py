import pytest

from app.core.security import allowed_file, validate_upload_magic, validate_uuid


def test_allowed_file_rejects_missing_extension():
    assert allowed_file("README") is False


def test_allowed_file_rejects_unsupported_extension():
    assert allowed_file("payload.exe") is False
    assert allowed_file("page.html") is False


def test_allowed_file_accepts_supported_extensions():
    for name in ("report.pdf", "notes.docx", "data.csv", "readme.txt", "sheet.xlsx"):
        assert allowed_file(name) is True


def test_allowed_file_is_case_insensitive():
    assert allowed_file("Report.PDF") is True


def test_validate_upload_magic_accepts_pdf_header(tmp_path):
    path = tmp_path / "ok.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    validate_upload_magic(str(path), "pdf")


def test_validate_upload_magic_accepts_zip_based_office_files(tmp_path):
    for ext in ("docx", "xlsx"):
        path = tmp_path / f"file.{ext}"
        path.write_bytes(b"PK\x03\x04" + b"\x00" * 8)
        validate_upload_magic(str(path), ext)


def test_validate_upload_magic_rejects_binary_text_upload(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_bytes(b"hello\x00world")
    with pytest.raises(ValueError, match="binary data"):
        validate_upload_magic(str(path), "txt")


def test_validate_uuid_rejects_invalid_value():
    with pytest.raises(ValueError, match="Invalid id"):
        validate_uuid("not-a-uuid")
