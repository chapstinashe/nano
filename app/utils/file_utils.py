import os
import shutil

from werkzeug.datastructures import FileStorage

from app.core.config import Config


def get_text_file_path(document_id: str) -> str:
    Config.ensure_storage_dirs()
    return os.path.join(Config.TEXT_PATH, f"{document_id}.txt")


def save_extracted_text(document_id: str, text: str) -> str:
    path = get_text_file_path(document_id)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def delete_text_file(document_id: str) -> None:
    path = get_text_file_path(document_id)
    if os.path.isfile(path):
        os.remove(path)


def load_extracted_text(document_id: str) -> str | None:
    path = get_text_file_path(document_id)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def save_upload(file: FileStorage, document_id: str, filename: str) -> str:
    Config.ensure_storage_dirs()
    doc_dir = os.path.join(Config.UPLOAD_PATH, document_id)
    os.makedirs(doc_dir, exist_ok=True)
    dest = os.path.join(doc_dir, filename)
    file.save(dest)
    return dest


def delete_upload(document_id: str) -> None:
    doc_dir = os.path.join(Config.UPLOAD_PATH, document_id)
    if os.path.isdir(doc_dir):
        shutil.rmtree(doc_dir)


def delete_metadata_file(document_id: str) -> None:
    path = os.path.join(Config.METADATA_PATH, f"{document_id}.json")
    if os.path.isfile(path):
        os.remove(path)


def get_upload_file_path(document_id: str, filename: str) -> str | None:
    path = os.path.join(Config.UPLOAD_PATH, document_id, filename)
    if os.path.isfile(path):
        return path
    return None
