from types import SimpleNamespace

from irodori_client.chunker import DEFAULT_BOUNDARY_CHARS, iter_chunks, split_text


def test_split_text_disabled_returns_original():
    assert split_text("あ" * 500, max_chars=0) == ["あ" * 500]
    assert split_text("", max_chars=10) == []


def test_split_text_short_text_is_stripped():
    assert split_text("  hello  ", max_chars=10) == ["hello"]


def test_split_text_prefers_higher_priority_boundary():
    # 。 has higher priority than ！ even though ！ appears later in the window.
    text = "あいう。えおか！きく"
    chunks = split_text(text, max_chars=8, boundary_chars=DEFAULT_BOUNDARY_CHARS)
    assert chunks[0] == "あいう。"


def test_split_text_hard_cuts_without_boundary():
    chunks = split_text("あ" * 25, max_chars=10)
    assert [len(c) for c in chunks] == [10, 10, 5]


def test_split_text_strips_chunk_edges():
    chunks = split_text("  あ  \n  い  ", max_chars=5)
    assert all(c == c.strip() for c in chunks)


def test_iter_chunks_indexes_from_one():
    items = [SimpleNamespace(text="あ。い。う。")]
    out = list(iter_chunks(items, max_chars=2, boundary_chars=DEFAULT_BOUNDARY_CHARS))
    assert [ci for _, ci, _ in out] == [1, 2, 3]
    assert [t for _, _, t in out] == ["あ。", "い。", "う。"]
