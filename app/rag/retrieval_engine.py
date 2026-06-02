"""
Retrieval pipeline: multi-query search, fusion, reranking, MMR diversity, and relevance filtering.
"""

import logging
from difflib import SequenceMatcher
from typing import Any, Optional

from app.core.config import Config
from app.models.schemas import SearchResult
from app.rag.embeddings import embed_text
from app.rag.retrieval_scoring import (
    answer_pattern_score,
    build_query_variants,
    distance_to_similarity,
    score_result,
)
from app.rag.vector_store import search_similar
from app.utils.guest_guard import is_guest_owner

logger = logging.getLogger(__name__)


def _build_where_filter(owner_user_id: str, document_ids: Optional[list[str]]) -> dict[str, Any]:
    owner_clause: dict[str, Any] = {"owner_user_id": owner_user_id}
    if not document_ids:
        return owner_clause
    if len(document_ids) == 1:
        return {"$and": [owner_clause, {"document_id": document_ids[0]}]}
    return {"$and": [owner_clause, {"document_id": {"$in": document_ids}}]}


def _parse_vector_results(
    raw: dict[str, Any],
    query: str,
    merged: dict[str, SearchResult],
) -> None:
    ids = raw.get("ids", [[]])[0]
    documents = raw.get("documents", [[]])[0]
    distances = raw.get("distances", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]

    for i, chunk_id in enumerate(ids):
        text = documents[i] if i < len(documents) else ""
        if not text.strip():
            continue

        distance = distances[i] if i < len(distances) else 1.0
        vector_score = distance_to_similarity(distance)
        score, breakdown = score_result(query, vector_score, text)

        metadata = dict(metadatas[i] if i < len(metadatas) else {})
        metadata.update(breakdown)

        existing = merged.get(chunk_id)
        if existing is None or score > existing.score:
            merged[chunk_id] = SearchResult(
                id=chunk_id,
                text=text,
                score=score,
                metadata=metadata,
            )


def _text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a[:500], b[:500]).ratio()


def _apply_mmr(results: list[SearchResult], limit: int, query: str = "") -> list[SearchResult]:
    if len(results) <= limit:
        return results

    top_pattern = max((answer_pattern_score(query, result.text) for result in results[:5]), default=0.0)
    if top_pattern >= 0.35:
        return results[:limit]

    lambda_param = Config.RETRIEVAL_MMR_LAMBDA
    selected: list[SearchResult] = []
    pool = list(results)

    while pool and len(selected) < limit:
        if not selected:
            selected.append(pool.pop(0))
            continue

        best_index = 0
        best_mmr = float("-inf")
        for idx, candidate in enumerate(pool):
            redundancy = max(_text_similarity(candidate.text, picked.text) for picked in selected)
            mmr = (lambda_param * candidate.score) - ((1.0 - lambda_param) * redundancy)
            if mmr > best_mmr:
                best_mmr = mmr
                best_index = idx
        selected.append(pool.pop(best_index))

    return selected


def _filter_by_relevance(results: list[SearchResult]) -> list[SearchResult]:
    if not results:
        return results

    min_score = Config.RETRIEVAL_MIN_SCORE
    top_score = results[0].score
    adaptive = max(min_score, top_score - Config.RETRIEVAL_SCORE_GAP)

    filtered = [result for result in results if result.score >= adaptive]
    if not filtered and results:
        filtered = results[: max(1, Config.RETRIEVAL_MIN_RESULTS)]
    return filtered


def _dedupe_near_duplicates(results: list[SearchResult]) -> list[SearchResult]:
    unique: list[SearchResult] = []
    for result in results:
        if any(
            _text_similarity(result.text, kept.text) > Config.RETRIEVAL_DEDUPE_THRESHOLD
            for kept in unique
        ):
            continue
        unique.append(result)
    return unique


def rank_search_results(query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
    ranked = sorted(results, key=lambda item: item.score, reverse=True)
    ranked = _dedupe_near_duplicates(ranked)
    ranked = _filter_by_relevance(ranked)
    return _apply_mmr(ranked, min(top_k, Config.RETRIEVAL_MAX_CONTEXT_CHUNKS), query=query)


def retrieve(
    query: str,
    owner_user_id: str,
    top_k: int = 5,
    document_ids: Optional[list[str]] = None,
) -> list[SearchResult]:
    """
    Retrieve the most relevant chunks for a query.

    1. Multi-query vector search over a wide candidate pool
    2. Fuse and rerank with lexical + answer-pattern signals
    3. Filter weak matches, dedupe, apply MMR for diversity
    """
    query = (query or "").strip()
    if not query:
        return []

    if is_guest_owner(owner_user_id):
        raise ValueError(
            "Guest embeddings are stored locally in the browser. Use client-side retrieval."
        )

    candidate_k = max(Config.RETRIEVAL_CANDIDATE_K, top_k * 3)
    where = _build_where_filter(owner_user_id, document_ids)
    variants = build_query_variants(query) if Config.RETRIEVAL_MULTI_QUERY else [query]

    merged: dict[str, SearchResult] = {}
    for variant in variants:
        embedding = embed_text(variant)
        raw = search_similar(embedding, top_k=candidate_k, where=where)
        _parse_vector_results(raw, query, merged)

    if not merged:
        logger.info("Retrieval returned no candidates for owner=%s", owner_user_id)
        return []

    final = rank_search_results(query, list(merged.values()), top_k)

    logger.info(
        "Retrieval: variants=%d candidates=%d returned=%d top_score=%.3f",
        len(variants),
        len(merged),
        len(final),
        final[0].score if final else 0.0,
    )
    return final
