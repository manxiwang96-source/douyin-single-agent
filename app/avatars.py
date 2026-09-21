from __future__ import annotations

import base64
import binascii
from pathlib import Path
from uuid import UUID, uuid4

from app.config import project_root


class AvatarError(ValueError):
    """Avatar payload could not be stored."""


MAX_AVATAR_BYTES = 1024 * 1024


def avatar_root(media_root: Path | None = None) -> Path:
    if media_root is not None:
        return media_root.parent / "avatars"
    return project_root() / "avatars"


def decode_avatar_payload(raw: str) -> tuple[bytes, str]:
    if not isinstance(raw, str) or not raw.strip():
        raise AvatarError("avatar is empty")
    payload = raw.strip()
    suffix = ".png"
    if payload.startswith("data:") and "," in payload:
        header, payload = payload.split(",", 1)
        header = header.lower()
        if "jpeg" in header or "jpg" in header:
            suffix = ".jpg"
        elif "webp" in header:
            suffix = ".webp"
        elif "gif" in header:
            suffix = ".gif"
        else:
            suffix = ".png"
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AvatarError("avatar must be base64") from exc
    if not data:
        raise AvatarError("avatar is empty")
    if len(data) > MAX_AVATAR_BYTES:
        raise AvatarError("avatar is too large")
    return data, suffix


def save_avatar(root: Path, user_id: UUID, raw: str) -> str:
    data, suffix = decode_avatar_payload(raw)
    directory = root / str(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{suffix}"
    path = directory / filename
    path.write_bytes(data)
    return f"avatars/{user_id}/{filename}"


def resolve_avatar_file(root: Path, avatar_uri: str | None) -> Path:
    if not avatar_uri:
        raise FileNotFoundError("avatar not found")
    relative = Path(str(avatar_uri).replace("\\", "/"))
    if relative.parts[:1] != ("avatars",) or ".." in relative.parts:
        raise FileNotFoundError("avatar not found")
    base = root.resolve()
    candidate = (base / Path(*relative.parts[1:])).resolve()
    if base not in candidate.parents and candidate.parent != base:
        raise FileNotFoundError("avatar not found")
    if not candidate.is_file():
        raise FileNotFoundError("avatar not found")
    return candidate