from app.models.schemas import SearchResult
from app.rag.citations import format_citations
from app.rag.retrieval_engine import _apply_mmr, _filter_by_relevance, rank_search_results
from app.rag.retrieval_scoring import (
    answer_pattern_score,
    build_query_variants,
    distance_to_similarity,
    normalize_query,
    score_result,
)


def test_build_query_variants_includes_keywords():
    variants = build_query_variants("What is Claim-AI about?")
    assert "What is Claim-AI about?" in variants
    assert any("claim" in variant.lower() for variant in variants)


def test_normalize_query_fixes_mane_typo():
    assert normalize_query("What is the dragon mane") == "What is the dragon name"


def test_build_query_variants_includes_focus_terms_for_name_questions():
    variants = build_query_variants("What is the name of the dragon?")
    assert any("dragon" in variant.lower() for variant in variants)


def test_distance_to_similarity():
    assert distance_to_similarity(0.0) == 1.0
    assert distance_to_similarity(2.0) == 0.0


def test_score_result_prefers_lexical_match():
    vector_only, _ = score_result("claim insurance assessor", 0.9, "unrelated finance markets")
    lexical, _ = score_result(
        "claim insurance assessor",
        0.7,
        "insurance claim assessor triage verification dashboard",
    )
    assert lexical > vector_only


def test_answer_pattern_prefers_naming_passage_over_battle_scene():
    query = "What is the name of the dragon?"
    naming = (
        "The dragon's name was Kaelreth, last of the Skyfire dragons. "
        "For weeks, Lyra returned in secret."
    )
    battle = (
        "Kaelreth erupted from the peak like a living storm. The dragon's wings blotting out "
        "the stars as soldiers fled."
    )
    naming_score, naming_breakdown = score_result(query, 0.55, naming)
    battle_score, battle_breakdown = score_result(query, 0.82, battle)
    assert naming_breakdown["answer_pattern"] > battle_breakdown["answer_pattern"]
    assert naming_score > battle_score


def test_typo_mane_question_prefers_naming_passage():
    query = "What is the dragon mane"
    naming = "The dragon's name was Kaelreth, last of the Skyfire dragons."
    battle = (
        "Kaelreth erupted from the peak like a living storm, wings blotting out the stars. "
        "Arrows darkened the sky as soldiers fled screaming."
    )
    naming_score, _ = score_result(query, 0.55, naming)
    battle_score, _ = score_result(query, 0.85, battle)
    assert naming_score > battle_score


def test_format_citations_remaps_battle_ref_to_naming_chunk():
    naming = SearchResult(
        id="naming",
        text="The dragon's name was Kaelreth, last of the Skyfire dragons.",
        score=0.92,
        metadata={"chunk_start": 100, "chunk_end": 180, "chunk_index": 2},
    )
    battle = SearchResult(
        id="battle",
        text="Kaelreth erupted from the peak like a living storm as arrows darkened the sky.",
        score=0.88,
        metadata={"chunk_start": 500, "chunk_end": 620, "chunk_index": 6},
    )
    results = [naming, battle]
    answer = "The dragon's name is Kaelreth, last of the Skyfire dragons [2]."
    citations = format_citations(results, answer, query="What is the dragon mane")
    assert len(citations) == 1
    assert citations[0]["ref"] == 2
    assert "name was Kaelreth" in citations[0]["paragraph"]
    assert citations[0]["chunk_start"] == 100


def test_filter_by_relevance_keeps_top_matches():
    results = [
        SearchResult(id="1", text="a", score=0.9, metadata={}),
        SearchResult(id="2", text="b", score=0.8, metadata={}),
        SearchResult(id="3", text="c", score=0.2, metadata={}),
    ]
    filtered = _filter_by_relevance(results)
    assert len(filtered) >= 2
    assert all(item.score >= 0.2 for item in filtered)


def test_mmr_reduces_redundant_chunks():
    results = [
        SearchResult(id="1", text="Claim-AI helps insurance assessors triage claims.", score=0.95, metadata={}),
        SearchResult(id="2", text="Claim-AI helps insurance assessors triage claims quickly.", score=0.94, metadata={}),
        SearchResult(id="3", text="Policy coverage is determined by the product disclosure statement.", score=0.7, metadata={}),
    ]
    selected = _apply_mmr(results, limit=2, query="How does Claim-AI help assessors?")
    assert len(selected) == 2
    texts = {item.text for item in selected}
    assert any("Policy coverage" in text for text in texts)


def test_rank_search_results_skips_mmr_for_factual_name_question():
    query = "What is the name of the dragon?"
    naming = SearchResult(
        id="1",
        text="The dragon's name was Kaelreth, and the mountain fell silent.",
        score=0.91,
        metadata={},
    )
    battle = SearchResult(
        id="2",
        text="Kaelreth crashed beside her, bleeding molten fire from wounds across his scales.",
        score=0.89,
        metadata={},
    )
    other = SearchResult(
        id="3",
        text="Lyra climbed the pass alone through snow and ash.",
        score=0.4,
        metadata={},
    )
    ranked = rank_search_results(query, [battle, naming, other], top_k=2)
    assert ranked[0].id == "1"
    assert answer_pattern_score(query, ranked[0].text) >= 0.35
