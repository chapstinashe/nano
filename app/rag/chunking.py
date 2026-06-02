import re
from typing import Optional

from app.core.config import Config


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def split_text(
    text: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> list[str]:
    chunk_size = chunk_size or Config.CHUNK_SIZE
    chunk_overlap = chunk_overlap or Config.CHUNK_OVERLAP

    if not (text or "").strip():
        return []

    # Scene breaks (---) stay as separate paragraphs so naming passages are not merged with battle scenes.
    prepared = re.sub(r"\s*---\s*", "\n\n", text)
    paragraphs = [normalize_text(part) for part in prepared.split("\n\n") if normalize_text(part)]
    if not paragraphs:
        return []

    separators = ["\n\n", "\n", ". ", " ", ""]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            chunks.append(paragraph)
        else:
            chunks.extend(_recursive_split(paragraph, separators, chunk_size, chunk_overlap))

    return chunks


def split_text_with_spans(
    text: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> list[dict]:
    """
    Split text into chunks and attach character spans (start/end) into the
    normalized full-document text.

    Spans are best-effort and are robust to overlap by searching slightly
    before the previous chunk end.
    """
    normalized = normalize_text(text)
    chunks = split_text(normalized, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return []

    overlap = chunk_overlap or Config.CHUNK_OVERLAP
    spans: list[dict] = []
    search_from = 0
    prev_end = 0

    for chunk in chunks:
        start_search = max(0, prev_end - overlap - 25)
        idx = normalized.find(chunk, start_search)
        if idx < 0 and search_from:
            idx = normalized.find(chunk, max(0, search_from - 50))
        if idx < 0:
            idx = normalized.find(chunk)

        if idx < 0:
            # Worst case: fall back to a monotonic span guess.
            idx = min(search_from, max(0, len(normalized) - len(chunk)))

        start = idx
        end = min(len(normalized), idx + len(chunk))
        spans.append({"text": chunk, "start": start, "end": end})
        search_from = max(search_from, end)
        prev_end = end

    return spans


def _recursive_split(
    text: str,
    separators: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    if not separators:
        return _split_by_size(text, chunk_size, chunk_overlap)

    separator = separators[0]
    remaining_separators = separators[1:]

    if separator:
        splits = text.split(separator)
    else:
        splits = list(text)

    chunks: list[str] = []
    current = ""

    for i, split in enumerate(splits):
        piece = split if not separator else split + (separator if i < len(splits) - 1 else "")

        if len(piece) > chunk_size and remaining_separators:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_recursive_split(piece, remaining_separators, chunk_size, chunk_overlap))
            continue

        candidate = (current + piece).strip()
        if len(candidate) <= chunk_size:
            current = candidate + (" " if current and piece else "")
        else:
            if current.strip():
                chunks.append(current.strip())
            current = piece

    if current.strip():
        chunks.append(current.strip())

    return _merge_with_overlap(chunks, chunk_overlap)


def _split_by_size(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - chunk_overlap
        if start < 0:
            start = 0
        if end >= len(text):
            break
    return chunks


def _merge_with_overlap(chunks: list[str], chunk_overlap: int) -> list[str]:
    if chunk_overlap <= 0 or len(chunks) <= 1:
        return chunks

    merged = [chunks[0]]
    for chunk in chunks[1:]:
        prev = merged[-1]
        if len(prev) > chunk_overlap:
            overlap = prev[-chunk_overlap:]
            merged.append(overlap + chunk)
        else:
            merged.append(chunk)
    return merged
