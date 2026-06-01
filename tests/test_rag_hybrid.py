from app.retrieval import rrf_fuse, tokenize


def test_tokenize_keeps_english_words_and_chinese_terms():
    assert tokenize("Deposit 规则 / SKU black_l") == [
        "deposit",
        "规",
        "则",
        "sku",
        "black_l",
    ]


def test_rrf_fuse_deduplicates_and_combines_rank_signals():
    dense = ["deposit rules", "return window", "cleaning fee"]
    bm25 = ["return window", "deposit rules", "late fee"]

    fused = rrf_fuse([dense, bm25], limit=3)

    assert fused == ["deposit rules", "return window", "cleaning fee"]


def test_rrf_fuse_respects_limit():
    fused = rrf_fuse([["a", "b"], ["c", "d"]], limit=2)

    assert fused == ["a", "c"]
