from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Sequence

from langchain_openai import OpenAIEmbeddings

from app.config import Settings

EmbedFn = Callable[[list[str]], list[list[float]]]


def wrap_embed_documents(embed_documents: Callable[[list[str]], list[list[float]]]) -> EmbedFn:
    def _embed(texts: list[str], *args, **kwargs) -> list[list[float]]:
        return embed_documents(texts)

    return _embed


def hashing_embed_documents(texts: Sequence[str], dims: int = 1024) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        values = [0.0] * dims
        blob = (text or "").lower()

        def add(token: str, weight: float) -> None:
            if not token:
                return
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % dims
            values[index] += weight

        add(blob, 4.0)
        for token in re.findall(r"[\w\u4e00-\u9fff]+", blob):
            add(token, 2.0)
        for token in re.findall(r"\d+[:xX]\d+(?:[:xX]\d+)?", blob):
            add(token, 5.0)
        for n in (2, 3, 4):
            for i in range(max(0, len(blob) - n + 1)):
                add(blob[i : i + n], 1.0)
        norm = math.sqrt(sum(item * item for item in values)) or 1.0
        vectors.append([item / norm for item in values])
    return vectors


def make_openai_embeddings(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        check_embedding_ctx_length=False,
    )


class EmbeddingsAdapter:
    def __init__(self, embed_documents: Callable[[list[str]], list[list[float]]]):
        self._embed_documents = embed_documents

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed_documents([text])[0]
