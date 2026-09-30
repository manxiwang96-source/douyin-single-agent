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
ALLOWED_KNOWLEDGE_UPLOAD_SUFFIXES = frozenset({".md", ".txt"})
MAX_KNOWLEDGE_UPLOAD_BYTES = 1 * 1024 * 1024


class KnowledgeUploadError(ValueError):
    """Raised when an uploaded knowledge file is rejected."""


def validate_knowledge_upload_filename(filename: str) -> str:
    name = Path(str(filename or "")).name.strip()
    if not name or name in {".", ".."}:
        raise KnowledgeUploadError("invalid knowledge filename")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_KNOWLEDGE_UPLOAD_SUFFIXES:
        raise KnowledgeUploadError("only .md and .txt files are supported")
    return name


def decode_knowledge_upload(content: bytes) -> str:
    data = content or b""
    if len(data) > MAX_KNOWLEDGE_UPLOAD_BYTES:
        raise KnowledgeUploadError("knowledge file is too large")
    if not data.strip():
        raise KnowledgeUploadError("knowledge file is empty")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeUploadError("knowledge file must be utf-8 text") from exc
    if not text.strip():
        raise KnowledgeUploadError("knowledge file is empty")
    return text


def kb_namespace(user_id, agent_instance_id) -> tuple[str, str, str]:
    return (str(user_id), str(agent_instance_id), "kb")


def profile_namespace(user_id, agent_instance_id) -> tuple[str, str, str]:
    return (str(user_id), str(agent_instance_id), "profile")


def index_knowledge_text(
    store,
    namespace,
    text: str,
    source: str,
    *,
    key_prefix: str | None = None,
) -> int:
    count = 0
    for chunk in split_markdown(text, source):
        chunk_id = chunk["chunk_id"]
        if key_prefix:
            chunk_id = f"{key_prefix}:{chunk_id}"
            chunk = {**chunk, "chunk_id": chunk_id}
        store.put(namespace, chunk_id, chunk)
        count += 1
    if count == 0:
        raise RuntimeError(f"no knowledge chunks indexed from {source}")
    return count


def index_markdown_file(store, namespace, path: Path) -> int:
    return index_knowledge_text(
        store,
        namespace,
        path.read_text(encoding="utf-8"),
        path.name,
    )


def index_instance_knowledge_text(
    store,
    *,
    user_id,
    agent_instance_id,
    text: str,
    source: str,
    key_prefix: str | None = None,
) -> int:
    return index_knowledge_text(
        store,
        kb_namespace(user_id, agent_instance_id),
        text,
        source,
        key_prefix=key_prefix,
    )


def save_knowledge_upload(
    media_root: Path,
    *,
    user_id,
    agent_instance_id,
    stored_name: str,
    content: bytes,
) -> str:
    directory = Path(media_root) / str(user_id) / str(agent_instance_id) / "knowledge"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / stored_name
    path.write_bytes(content)
    return path.relative_to(Path(media_root)).as_posix()


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


def selected_document_filenames(documents, selected_ids) -> list[str]:
    allowed_ids = {str(value) for value in (selected_ids or [])}
    names: list[str] = []
    seen: set[str] = set()
    for item in documents or []:
        if str(getattr(item, "document_id", "")) not in allowed_ids:
            continue
        name = str(getattr(item, "filename", "") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _allowed_source_set(allowed_sources) -> set[str] | None:
    if allowed_sources is None:
        return None
    return {str(item) for item in allowed_sources if str(item)}


def search_kb(
    store,
    query: str,
    k: int = 4,
    namespace=KB_NAMESPACE,
    allowed_sources=None,
) -> list[dict[str, Any]]:
    allowed = _allowed_source_set(allowed_sources)
    if allowed is not None and not allowed:
        return []
    limit = max(1, int(k or 4))
    fetch_limit = max(limit * 4, 16) if allowed is not None else limit
    hits = store.search(namespace, query=query, limit=fetch_limit)
    results: list[dict[str, Any]] = []
    for hit in hits:
        score = getattr(hit, "score", None)
        if score is not None and score <= 0:
            continue
        value = hit.value or {}
        source = str(value.get("source", "") or "")
        if allowed is not None and source not in allowed:
            continue
        results.append(
            {
                "source": source,
                "text": value.get("text", ""),
                "score": score,
            }
        )
        if len(results) >= limit:
            break
    return results


def format_kb_hits(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "NO_HITS"
    parts = []
    for hit in hits:
        parts.append(f"source={hit.get('source', '')}\n{hit.get('text', '')}")
    return "\n\n".join(parts)
