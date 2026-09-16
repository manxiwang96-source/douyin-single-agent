from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langgraph.store.memory import InMemoryStore

from app.embeddings import wrap_embed_documents

PRIMARY_SPLIT = re.compile(r"(?m)^##\s+")
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 80
KB_NAMESPACE = ("kb",)


def split_markdown(text: str, source: str) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    parts = PRIMARY_SPLIT.split(text or "")
    heading_iter = PRIMARY_SPLIT.finditer(text or "")
    titles = ["intro"]
    titles.extend(match.group(0).strip() for match in heading_iter)
    if len(parts) == 1:
        sections = [("intro", parts[0])]
    else:
        sections = []
        if parts[0].strip():
            sections.append(("intro", parts[0]))
        for title, body in zip(titles[1:], parts[1:]):
            sections.append((title, f"## {body}" if not body.startswith("##") else body))
    for title, body in sections:
        for index, piece in enumerate(secondary_chunks(body)):
            chunks.append(
                {
                    "source": source,
                    "section": title,
                    "text": piece.strip(),
                    "chunk_id": f"{source}:{title}:{index}",
                }
            )
    return [item for item in chunks if item["text"]]


def secondary_chunks(
    text: str,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    pieces: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        pieces.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return pieces


def make_store(embed_documents, dims: int) -> InMemoryStore:
    return InMemoryStore(
        index={
            "embed": wrap_embed_documents(embed_documents),
            "dims": dims,
            "fields": ["text"],
        }
    )


def index_knowledge_dir(store: InMemoryStore, knowledge_dir: Path) -> int:
    count = 0
    for path in sorted(knowledge_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for chunk in split_markdown(text, path.name):
            store.put(KB_NAMESPACE, chunk["chunk_id"], chunk)
            count += 1
    return count


def search_kb(store: InMemoryStore, query: str, k: int = 4) -> list[dict[str, Any]]:
    hits = store.search(KB_NAMESPACE, query=query, limit=k)
    results: list[dict[str, Any]] = []
    for hit in hits:
        score = getattr(hit, "score", None)
        if score is not None and score <= 0:
            continue
        value = hit.value or {}
        results.append(
            {
                "source": value.get("source", ""),
                "text": value.get("text", ""),
                "score": score,
            }
        )
    return results


def format_kb_hits(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "NO_HITS"
    parts = []
    for hit in hits:
        parts.append(f"source={hit.get('source', '')}\n{hit.get('text', '')}")
    return "\n\n".join(parts)
