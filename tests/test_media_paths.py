from __future__ import annotations

from pathlib import Path

import pytest

from app.config import project_root
from app.media_paths import (
    MediaPathError,
    allocate_media_path,
    media_url_for,
    new_media_filename,
    resolve_media_root,
    safe_media_file,
)


def test_resolve_rejects_drive_root():
    with pytest.raises(MediaPathError):
        resolve_media_root("D:\\", project_root())


def test_resolve_rejects_project_root():
    root = project_root()
    with pytest.raises(MediaPathError):
        resolve_media_root(str(root), root)
    with pytest.raises(MediaPathError):
        resolve_media_root(".", root)


def test_allocate_under_outputs_subdirs(tmp_path: Path):
    media_root = tmp_path / "outputs"
    image_path = allocate_media_path(media_root, "images", ".png")
    video_path = allocate_media_path(media_root, "videos", ".mp4")
    assert image_path.parent == media_root / "images"
    assert video_path.parent == media_root / "videos"
    assert image_path.name.endswith(".png")
    assert video_path.name.endswith(".mp4")


def test_filename_pattern():
    name = new_media_filename(".png")
    date, rest = name.split("-", 1)
    assert len(date) == 15
    assert "T" in date
    assert rest.endswith(".png")
    assert len(rest.split(".")[0]) == 8


def test_safe_media_file_rejects_escape(tmp_path: Path):
    media_root = tmp_path / "outputs"
    allocate_media_path(media_root, "images", ".png")
    with pytest.raises(FileNotFoundError):
        safe_media_file(media_root, "images", "../secrets.txt")
    with pytest.raises(FileNotFoundError):
        safe_media_file(media_root, "other", "a.png")

def test_allocate_isolates_user_and_instance(tmp_path: Path):
    media_root = tmp_path / "outputs"
    user_id = "11111111-1111-4111-8111-111111111111"
    agent_instance_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    image_path = allocate_media_path(
        media_root,
        "images",
        ".png",
        user_id=user_id,
        agent_instance_id=agent_instance_id,
    )
    assert image_path.parent == media_root / user_id / agent_instance_id / "images"
    url = media_url_for(image_path, media_root)
    assert url == f"/v1/media/{user_id}/{agent_instance_id}/images/{image_path.name}"
    image_path.write_bytes(b"png")
    found = safe_media_file(
        media_root,
        "images",
        image_path.name,
        user_id=user_id,
        agent_instance_id=agent_instance_id,
    )
    assert found == image_path.resolve()
    with pytest.raises(FileNotFoundError):
        safe_media_file(
            media_root,
            "images",
            image_path.name,
            user_id="22222222-2222-4222-8222-222222222222",
            agent_instance_id=agent_instance_id,
        )


def test_allocate_without_ids_keeps_legacy_layout(tmp_path: Path):
    media_root = tmp_path / "outputs"
    path = allocate_media_path(media_root, "videos", ".mp4")
    assert path.parent == media_root / "videos"
    assert media_url_for(path, media_root) == f"/v1/media/videos/{path.name}"
