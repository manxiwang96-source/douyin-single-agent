from __future__ import annotations

from pathlib import Path

import pytest

from app.config import project_root
from app.media_paths import (
    MediaPathError,
    allocate_media_path,
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
