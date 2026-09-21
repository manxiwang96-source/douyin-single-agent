from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from app.config import project_root


class MediaPathError(ValueError):
    """Raised when MEDIA_OUTPUT_DIR resolves to a forbidden location."""


def is_drive_root(path: Path) -> bool:
    resolved = path.resolve()
    return resolved.parent == resolved


def resolve_media_root(media_output_dir: str, root: Path | None = None) -> Path:
    root = (root or project_root()).resolve()
    raw = Path(media_output_dir)
    resolved = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if is_drive_root(resolved):
        raise MediaPathError("MEDIA_OUTPUT_DIR must not be a drive root")
    if resolved == root:
        raise MediaPathError("MEDIA_OUTPUT_DIR must not be the project root")
    return resolved


def _is_unsafe_segment(value: str) -> bool:
    text = str(value or "")
    return (not text) or "/" in text or "\\" in text or ".." in text


def ensure_media_dirs(
    media_root: Path,
    *,
    user_id: str | None = None,
    agent_instance_id: str | None = None,
) -> dict[str, Path]:
    base = media_root
    if user_id and agent_instance_id:
        if _is_unsafe_segment(str(user_id)) or _is_unsafe_segment(str(agent_instance_id)):
            raise MediaPathError("invalid media owner")
        base = media_root / str(user_id) / str(agent_instance_id)
    images = base / "images"
    videos = base / "videos"
    images.mkdir(parents=True, exist_ok=True)
    videos.mkdir(parents=True, exist_ok=True)
    return {"images": images, "videos": videos}


def new_media_filename(suffix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return f"{timestamp}-{short_id}{suffix}"


def allocate_media_path(
    media_root: Path,
    kind: str,
    suffix: str,
    *,
    user_id: str | None = None,
    agent_instance_id: str | None = None,
) -> Path:
    dirs = ensure_media_dirs(
        media_root,
        user_id=user_id,
        agent_instance_id=agent_instance_id,
    )
    if kind not in dirs:
        raise MediaPathError(f"Unknown media kind: {kind}")
    return dirs[kind] / new_media_filename(suffix)


def media_url_for(path: Path, media_root: Path) -> str:
    relative = path.resolve().relative_to(media_root.resolve()).as_posix()
    parts = relative.split("/")
    if len(parts) == 4:
        user_id, agent_instance_id, kind, file_name = parts
        return f"/v1/media/{user_id}/{agent_instance_id}/{kind}/{file_name}"
    return f"/v1/media/{relative}"


def safe_media_file(
    media_root: Path,
    kind: str,
    file_name: str,
    *,
    user_id: str | None = None,
    agent_instance_id: str | None = None,
) -> Path:
    if kind not in {"images", "videos"}:
        raise FileNotFoundError(kind)
    if _is_unsafe_segment(file_name):
        raise FileNotFoundError(file_name)
    if user_id is not None and agent_instance_id is not None:
        if _is_unsafe_segment(str(user_id)) or _is_unsafe_segment(str(agent_instance_id)):
            raise FileNotFoundError(file_name)
        directory = (media_root / str(user_id) / str(agent_instance_id) / kind).resolve()
    else:
        directory = (media_root / kind).resolve()
    candidate = (directory / file_name).resolve()
    if directory not in candidate.parents and candidate.parent != directory:
        raise FileNotFoundError(file_name)
    if not candidate.is_file():
        raise FileNotFoundError(file_name)
    return candidate
