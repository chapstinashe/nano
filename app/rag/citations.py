import re
from difflib import SequenceMatcher

from app.models.schemas import SearchResult
from app.rag.retrieval_scoring import answer_pattern_score
from app.repositories.document_repository import DocumentRepository

document_repo = DocumentRepository()

_CITATION_RE = re.compile(r"\[(\d+)\]")
_STOPWORDS = {
    "about", "after", "also", "been", "being", "both", "could", "from",
    "have", "into", "more", "only", "other", "shall", "such", "than",
    "that", "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "very", "were", "what", "when", "where", "which",
    "while", "will", "with", "would", "your",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {word for word in words if len(word) > 2 and word not in _STOPWORDS}


def _split_sentences(text: str) -> list[str]:
    text = _normalize(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if len(part.strip()) > 12]


def _sentence_overlap(answer: str, sentence: str) -> float:
    answer_tokens = _tokenize(answer)
    sentence_tokens = _tokenize(sentence)
    if not answer_tokens or not sentence_tokens:
        return 0.0

    overlap = len(answer_tokens & sentence_tokens) / len(sentence_tokens)
    fuzzy = SequenceMatcher(None, answer.lower(), sentence.lower()).ratio()
    return round((overlap * 0.65) + (fuzzy * 0.35), 4)


def _chunk_relevance(answer: str, chunk_text: str) -> float:
    sentences = _split_sentences(chunk_text)
    if not sentences:
        return 0.0

    sentence_scores = [_sentence_overlap(answer, sentence) for sentence in sentences]
    top_sentence = max(sentence_scores)
    avg_top = sum(sorted(sentence_scores, reverse=True)[:2]) / min(2, len(sentence_scores))
    token_overlap = len(_tokenize(answer) & _tokenize(chunk_text)) / max(len(_tokenize(chunk_text)), 1)

    return round((top_sentence * 0.5) + (avg_top * 0.3) + (min(token_overlap, 1.0) * 0.2), 4)


def extract_cited_refs(answer: str) -> set[int]:
    if not answer:
        return set()
    return {int(match) for match in _CITATION_RE.findall(answer)}


def _infer_used_refs(answer: str, results: list[SearchResult]) -> set[int]:
    used: set[int] = set()
    for index, result in enumerate(results, start=1):
        relevance = _chunk_relevance(answer, result.text)
        retrieval = result.score
        combined = (relevance * 0.7) + (retrieval * 0.3)
        if relevance >= 0.28 and combined >= 0.35:
            used.add(index)
    return used


def _rank_sentences(answer: str, sentences: list[str], limit: int = 3) -> list[dict]:
    ranked = []
    for sentence in sentences:
        score = _sentence_overlap(answer, sentence)
        if score >= 0.12:
            ranked.append({"text": sentence, "score": score})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def _build_excerpt(sentences: list[dict], fallback: str, max_len: int = 280) -> str:
    if not sentences:
        text = _normalize(fallback)
        return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"

    excerpt = sentences[0]["text"]
    if len(excerpt) < max_len and len(sentences) > 1:
        extra = sentences[1]["text"]
        combined = f"{excerpt} {extra}"
        if len(combined) <= max_len:
            excerpt = combined
    if len(excerpt) > max_len:
        excerpt = excerpt[: max_len - 1].rstrip() + "…"
    return excerpt


def _section_label(chunk_index: int, source_type: str) -> str:
    label = source_type.upper() if source_type else "DOC"
    return f"{label} - Part {chunk_index + 1}"


def _load_document_metadata(owner_user_id: str, document_id: str) -> dict:
    if not document_id or not owner_user_id:
        return {}
    return document_repo.get_by_id(owner_user_id, document_id) or {}


def _source_label(source: str, table: str = "") -> str:
    if source == "database":
        return f"Database table: {table}" if table else "Database"
    return "Uploaded file"


def _chunk_position(chunk_index: int, chunk_total: int | None) -> str:
    chunk_number = chunk_index + 1
    if chunk_total and chunk_total > 0:
        return f"Chunk {chunk_number} of {chunk_total}"
    return f"Chunk {chunk_number}"


def _resolve_cited_result(
    index: int,
    results: list[SearchResult],
    answer: str,
    query: str,
) -> SearchResult:
    return results[index - 1]


def _sentence_document_span(
    text: str,
    answer: str,
    query: str,
    chunk_start,
    chunk_end,
) -> tuple:
    if chunk_start is None:
        return chunk_start, chunk_end

    try:
        base_start = int(chunk_start)
    except (TypeError, ValueError):
        return chunk_start, chunk_end

    sentences = _split_sentences(text)
    if not sentences:
        return chunk_start, chunk_end

    best_span = None
    best_score = -1.0
    cursor = 0
    for sentence in sentences:
        pos = text.find(sentence, cursor)
        if pos < 0:
            pos = text.find(sentence)
        if pos < 0:
            continue
        end_pos = pos + len(sentence)
        score = (_chunk_relevance(answer, sentence) * 0.65) + (answer_pattern_score(query, sentence) * 0.35)
        if score > best_score:
            best_score = score
            best_span = (base_start + pos, base_start + end_pos)
        cursor = max(cursor, end_pos)

    if best_span and best_score >= 0.15:
        return best_span
    return chunk_start, chunk_end


def _build_citation_entry(
    index: int,
    result: SearchResult,
    answer: str,
    query: str = "",
) -> dict:
    meta = result.metadata or {}
    chunk_index = int(meta.get("chunk_index", 0))
    document_id = meta.get("document_id", "")
    owner_user_id = meta.get("owner_user_id", "")
    doc_meta = _load_document_metadata(owner_user_id, document_id)
    chunk_total = int(doc_meta.get("chunk_count", 0) or 0) or None
    text = _normalize(result.text)
    sentences = _split_sentences(text)
    ranked_sentences = _rank_sentences(answer, sentences)
    answer_relevance = _chunk_relevance(answer, text)
    combined_score = (answer_relevance * 0.65) + (result.score * 0.35)
    source = meta.get("source", doc_meta.get("source", "file"))
    table = meta.get("table", "")
    chunk_start, chunk_end = _sentence_document_span(
        text,
        answer,
        query,
        meta.get("chunk_start"),
        meta.get("chunk_end"),
    )

    return {
        "source_ref": index,
        "ref": index,
        "chunk_id": result.id,
        "document": meta.get("filename", doc_meta.get("filename", "Unknown document")),
        "document_id": document_id,
        "source_type": meta.get("source_type", doc_meta.get("source_type", "")),
        "source": source,
        "source_label": _source_label(source, table),
        "table": table,
        "db_type": meta.get("db_type", doc_meta.get("extra", {}).get("db_type", "")),
        "chunk_index": chunk_index,
        "chunk_start": chunk_start,
        "chunk_end": chunk_end,
        "chunk_number": chunk_index + 1,
        "chunk_total": chunk_total,
        "chunk_position": _chunk_position(chunk_index, chunk_total),
        "section": _section_label(chunk_index, meta.get("source_type", "")),
        "indexed_at": meta.get("created_at", doc_meta.get("created_at", "")),
        "word_count": len(text.split()),
        "char_count": len(text),
        "sentence_count": len(sentences),
        "excerpt": _build_excerpt(ranked_sentences, text),
        "paragraph": text,
        "sentences": [entry["text"] for entry in ranked_sentences],
        "score": round(combined_score, 4),
    }


def format_citations(
    results: list[SearchResult],
    answer: str = "",
    query: str = "",
) -> list[dict]:
    if not results or not answer.strip():
        return []

    cited_refs = extract_cited_refs(answer)
    used_refs = cited_refs or _infer_used_refs(answer, results)
    if not used_refs:
        return []

    citations: list[dict] = []

    if cited_refs:
        # LLM cited [N] matching [Source N] in the prompt — use the exact chunk it referenced.
        for index in sorted(cited_refs):
            if 1 <= index <= len(results):
                result = _resolve_cited_result(index, results, answer, query)
                citations.append(_build_citation_entry(index, result, answer, query=query))
        return citations

    top_score = results[0].score
    min_retrieval = max(0.32, top_score - 0.18)

    candidates: list[dict] = []
    for index, result in enumerate(results, start=1):
        if index not in used_refs or result.score < min_retrieval:
            continue

        answer_relevance = _chunk_relevance(answer, _normalize(result.text))
        if answer_relevance < 0.25:
            continue

        candidates.append(_build_citation_entry(index, result, answer, query=query))

    candidates.sort(key=lambda item: item["score"], reverse=True)

    seen: set[tuple[str, str]] = set()
    for candidate in candidates[:5]:
        dedupe_key = (candidate["document_id"], candidate["excerpt"][:120])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        citations.append(candidate)

    citations.sort(key=lambda item: item["source_ref"])
    return citations
