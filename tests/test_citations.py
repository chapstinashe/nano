from app.models.schemas import SearchResult
from app.rag.citations import extract_cited_refs, format_citations


def _result(index: int, text: str, score: float = 0.9) -> SearchResult:
    return SearchResult(
        id=f"doc_{index}_0",
        text=text,
        score=score,
        metadata={
            "document_id": f"doc-{index}",
            "filename": f"file-{index}.pdf",
            "chunk_index": 0,
            "chunk_start": 0,
            "chunk_end": len(text),
            "source": "file",
            "source_type": "pdf",
        },
    )


def test_extract_cited_refs():
    answer = "Claim-AI reduces time [1] and shows reasoning [3]."
    assert extract_cited_refs(answer) == {1, 3}


def test_format_citations_includes_every_cited_ref_even_low_score():
    results = [
        _result(1, "Multimodal ingestion and triage for insurance claims."),
        _result(2, "Policy reasoning and coverage determination details."),
        _result(3, "Interactive dashboard with confidence score and reasoning.", score=0.33),
    ]
    answer = (
        "Claim-AI reduces assessment time [1]. "
        "It shows confidence and reasoning on a dashboard [3]."
    )

    citations = format_citations(results, answer)
    refs = {c["ref"] for c in citations}

    assert refs == {1, 3}
    assert all(c["ref"] == c["source_ref"] for c in citations)
