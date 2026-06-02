from app.models.schemas import SearchResult
from app.rag.llm import chat_completion, stream_chat_completion
from app.rag.prompt_builder import build_prompt, format_context
from app.rag.retrieval_engine import retrieve


def results_from_context_chunks(chunks: list[dict]) -> list[SearchResult]:
    return [
        SearchResult(
            id=str(chunk.get("id", index)),
            text=str(chunk.get("text", "")),
            score=float(chunk.get("score", 0.0)),
            metadata=chunk.get("metadata", {}) or {},
        )
        for index, chunk in enumerate(chunks)
    ]


def prepare_chat(
    query: str,
    owner_user_id: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
    context_results: list[SearchResult] | None = None,
):
    if context_results is not None:
        results = context_results
    else:
        results = retrieve(
            query=query,
            owner_user_id=owner_user_id,
            top_k=top_k,
            document_ids=document_ids,
        )
    context = format_context(results)
    messages = build_prompt(query, context)
    return messages, results


def run_chat_pipeline(
    query: str,
    owner_user_id: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
    context_results: list[SearchResult] | None = None,
):
    messages, results = prepare_chat(
        query=query,
        owner_user_id=owner_user_id,
        top_k=top_k,
        document_ids=document_ids,
        context_results=context_results,
    )
    return stream_chat_completion(messages), results


def run_chat_completion(
    query: str,
    owner_user_id: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
    context_results: list[SearchResult] | None = None,
) -> tuple[str, list[SearchResult]]:
    messages, results = prepare_chat(
        query=query,
        owner_user_id=owner_user_id,
        top_k=top_k,
        document_ids=document_ids,
        context_results=context_results,
    )
    return chat_completion(messages), results


def run_search_pipeline(
    query: str,
    owner_user_id: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
) -> list[SearchResult]:
    return retrieve(
        query=query,
        owner_user_id=owner_user_id,
        top_k=top_k,
        document_ids=document_ids,
    )
