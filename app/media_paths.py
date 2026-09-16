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


def ensure_media_dirs(media_root: Path) -> dict[str, Path]:
    images = media_root / "images"
    videos = media_root / "videos"
    images.mkdir(parents=True, exist_ok=True)
    videos.mkdir(parents=True, exist_ok=True)
    return {"images": images, "videos": videos}


def new_media_filename(suffix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return f"{timestamp}-{short_id}{suffix}"


def allocate_media_path(media_root: Path, kind: str, suffix: str) -> Path:
    dirs = ensure_media_dirs(media_root)
    if kind not in dirs:
        raise MediaPathError(f"Unknown media kind: {kind}")
    return dirs[kind] / new_media_filename(suffix)


def media_url_for(path: Path, media_root: Path) -> str:
    relative = path.resolve().relative_to(media_root.resolve()).as_posix()
    return f"/v1/media/{relative}"


def safe_media_file(media_root: Path, kind: str, file_name: str) -> Path:
    if kind not in {"images", "videos"}:
        raise FileNotFoundError(kind)
    if not file_name or "/" in file_name or "\\" in file_name or ".." in file_name:
        raise FileNotFoundError(file_name)
    directory = (media_root / kind).resolve()
    candidate = (directory / file_name).resolve()
    if directory not in candidate.parents and candidate.parent != directory:
        raise FileNotFoundError(file_name)
    if not candidate.is_file():
        raise FileNotFoundError(file_name)
    return candidate