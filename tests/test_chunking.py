from app.rag.chunking import split_text


def test_split_short_text():
    text = "Hello world"
    chunks = split_text(text)
    assert chunks == ["Hello world"]


def test_split_long_text():
    text = "word " * 200
    chunks = split_text(text, chunk_size=100, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(len(c) > 0 for c in chunks)


def test_split_empty_text():
    assert split_text("") == []
    assert split_text("   ") == []
