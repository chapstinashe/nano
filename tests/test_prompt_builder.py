from app.rag.prompt_builder import build_prompt, format_context


def test_format_context_joins_chunks():
    result = format_context(["chunk one", "chunk two"])
    assert "chunk one" in result
    assert "---" in result


def test_build_prompt_separates_question_from_system():
    messages = build_prompt("What is RAG?", "Some context here.")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "What is RAG?" not in messages[0]["content"]
    assert "untrusted data" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "[RETRIEVED CONTEXT]" in messages[1]["content"]
    assert "[USER QUESTION]" in messages[1]["content"]
    assert "What is RAG?" in messages[1]["content"]
    assert "Some context here." in messages[1]["content"]
