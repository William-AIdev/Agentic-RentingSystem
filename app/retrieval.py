from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]", re.IGNORECASE)
RRF_K = 60


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def rrf_fuse(result_lists: list[list[str]], limit: int, rrf_k: int = RRF_K) -> list[str]:
    scores: dict[str, float] = {}
    for results in result_lists:
        for rank, text in enumerate(results):
            scores[text] = scores.get(text, 0.0) + 1.0 / (rrf_k + rank + 1)
    return [text for text, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)][
        :limit
    ]
