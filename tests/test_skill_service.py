from __future__ import annotations

import io
import stat
import urllib.request
import zipfile
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.skills import (
    InMemorySkillRepository,
    ConfiguredWebSearchProvider,
    MockSearchProvider,
    SearchCandidate,
    SkillImportStateError,
    SkillScanner,
    SkillSecurityError,
    SkillService,
    RemoteSkillDownloader,
    _SafeRedirectHandler,
    normalize_source_reference,
)


def _candidate(source: Path, *, candidate_id: str = "candidate-1", source_ref: str | None = "abc123") -> SearchCandidate:
    return SearchCandidate(
        candidate_id=candidate_id,
        name="External Research Skill",
        description="external skill for research",
        source_type="github",
        source_uri=f"file://{source}",
        source_ref=source_ref or "",
        license="MIT",
        author="test-author",
        version="1.0.0",
    )


def _write_skill_directory(root: Path, *, with_script: bool = True, with_secret: bool = False) -> None:
    (root / "references").mkdir(parents=True)
    (root / "assets").mkdir()
    (root / "scripts").mkdir()
    (root / "SKILL.md").write_text("# External Skill\nUse the reference files safely.", encoding="utf-8")
    (root / "LICENSE").write_text("MIT License", encoding="utf-8")
    (root / "references" / "guide.md").write_text("Reference content", encoding="utf-8")
    (root / "assets" / "example.txt").write_text("Asset content", encoding="utf-8")
    if with_script:
        script = "print('ok')\n"
        if with_secret:
            script = "token = 'super-secret-token-1234'\n"
        (root / "scripts" / "run.py").write_text(script, encoding="utf-8")


def _service(tmp_path: Path, source: Path, *, source_ref: str | None = "abc123"):
    provider = MockSearchProvider([_candidate(source, source_ref=source_ref)])
    repository = InMemorySkillRepository()
    service = SkillService(repository, search_provider=provider, quarantine_root=tmp_path / "quarantine")
    return service, repository, provider


def test_mock_search_provider_and_search_cache_are_deterministic(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source, with_script=False)
    service, repository, provider = _service(tmp_path, source)

    candidates = service.search("research")
    assert [item.candidate_id for item in candidates] == ["candidate-1"]
    provider._candidates.clear()
    item = service.start_import(uuid4(), uuid4(), "candidate-1")
    assert item.status == "awaiting_confirmation"
    assert repository.get_import(item.import_id).content_digest == item.scan_report["content_digest"]


def test_full_directory_is_copied_to_quarantine_with_report_and_digest(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source)
    service, repository, _ = _service(tmp_path, source)
    user_id = uuid4()
    agent_id = uuid4()

    item = service.start_import(user_id, agent_id, "candidate-1")
    assert item.status == "awaiting_confirmation"
    quarantine = Path(item.quarantine_path or "")
    assert quarantine.is_dir()
    assert (quarantine / "SKILL.md").is_file()
    assert (quarantine / "references" / "guide.md").is_file()
    assert (quarantine / "assets" / "example.txt").is_file()
    assert (quarantine / "scripts" / "run.py").is_file()
    assert item.source_ref == "abc123"
    assert item.scan_report["manifest"]["license"] == "MIT License"
    assert item.scan_report["manifest"]["scripts"] == ["scripts/run.py"]
    assert item.scan_report["risk_level"] == "high"
    assert len(item.content_digest or "") == 64


def test_fixed_ref_is_required_before_download(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source, with_script=False)
    service, _, _ = _service(tmp_path, source, source_ref=None)

    with pytest.raises(SkillSecurityError, match="fixed commit"):
        service.start_import(uuid4(), uuid4(), "candidate-1")


def test_missing_skill_md_is_quarantined_as_failed(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    (source / "README.md").write_text("not a skill", encoding="utf-8")
    service, _, _ = _service(tmp_path, source)

    item = service.start_import(uuid4(), uuid4(), "candidate-1")
    assert item.status == "failed"
    assert "SKILL.md" in item.failure_reason
    assert Path(item.quarantine_path or "").is_dir()


def test_ssrf_url_is_rejected_without_network_access(tmp_path: Path):
    provider = MockSearchProvider([SearchCandidate(
        candidate_id="remote",
        name="Remote Skill",
        description="remote",
        source_type="web",
        source_uri="http://127.0.0.1:9/skill.zip",
        source_ref="immutable-ref",
    )])
    service = SkillService(InMemorySkillRepository(), search_provider=provider, quarantine_root=tmp_path / "quarantine")

    item = service.start_import(uuid4(), uuid4(), "remote")
    assert item.status == "failed"
    assert "remote URL" in item.failure_reason


def test_zip_path_traversal_and_symlink_are_rejected(tmp_path: Path):
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape.txt", "escape")
    symlink = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink, "w") as archive:
        archive.writestr(link, "SKILL.md")

    for index, archive_path in enumerate((traversal, symlink)):
        service, _, _ = _service(tmp_path / f"case-{index}", archive_path)
        item = service.start_import(uuid4(), uuid4(), "candidate-1")
        assert item.status == "failed"
        assert "unsafe archive path" in item.failure_reason or "symlink" in item.failure_reason


def test_zip_bomb_size_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    archive_path = tmp_path / "large.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("SKILL.md", "12345678901")
    monkeypatch.setattr(SkillScanner, "MAX_FILE_BYTES", 10)
    service, _, _ = _service(tmp_path, archive_path)

    item = service.start_import(uuid4(), uuid4(), "candidate-1")
    assert item.status == "failed"
    assert "too large" in item.failure_reason


def test_secret_scan_raises_risk_without_exposing_secret(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source, with_secret=True)
    service, _, _ = _service(tmp_path, source)

    item = service.start_import(uuid4(), uuid4(), "candidate-1")
    assert item.status == "awaiting_confirmation"
    assert item.scan_report["manifest"]["warnings"] == ["possible secret: scripts/run.py"]
    assert "super-secret-token-1234" not in str(item.scan_report)
    assert item.scan_report["risk_level"] == "high"


def test_directory_symlink_is_rejected_when_platform_allows_symlinks(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source, with_script=False)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (source / "escape.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this Windows test host")
    service, _, _ = _service(tmp_path, source)

    item = service.start_import(uuid4(), uuid4(), "candidate-1")
    assert item.status == "failed"
    assert "symlink" in item.failure_reason


def test_confirm_import_enters_private_registry_and_binds_only_target_agent(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source, with_script=False)
    service, repository, _ = _service(tmp_path, source)
    user_a = uuid4()
    user_b = uuid4()
    agent_a = uuid4()
    agent_b = uuid4()
    item = service.start_import(user_a, agent_a, "candidate-1")

    assert service.list_private_registry(user_a) == []
    skill = service.confirm_import(user_a, item.import_id)
    assert skill.owner_scope == "user"
    assert skill.owner_user_id == user_a
    assert service.list_private_registry(user_a) == [skill]
    assert service.list_private_registry(user_b) == []
    assert service.load_skill(user_a, agent_a, skill.skill_id) == skill
    with pytest.raises(SkillSecurityError):
        service.load_skill(user_a, agent_b, skill.skill_id)
    with pytest.raises(SkillSecurityError):
        service.load_skill(user_b, agent_a, skill.skill_id)
    with pytest.raises(SkillImportStateError):
        service.confirm_import(user_a, item.import_id)
    assert len(repository.list_bindings(service.ensure_config(user_a, agent_a)["config_version_id"])) == 1
    assert service.list_catalog(user_b) and all(item.owner_scope == "platform" for item in service.list_catalog(user_b))


def test_platform_skill_requires_explicit_binding_before_it_is_loadable(tmp_path: Path):
    service = SkillService(InMemorySkillRepository(), quarantine_root=tmp_path / "quarantine")
    user_id = uuid4()
    agent_a = uuid4()
    agent_b = uuid4()
    platform_skill = next(item for item in service.list_catalog() if item.owner_scope == "platform")

    with pytest.raises(SkillSecurityError):
        service.load_skill(user_id, agent_a, platform_skill.skill_id)
    service.bind_platform_skill(user_id, agent_a, platform_skill.skill_id)
    assert service.load_skill(user_id, agent_a, platform_skill.skill_id) == platform_skill
    with pytest.raises(SkillSecurityError):
        service.load_skill(user_id, agent_b, platform_skill.skill_id)


def test_repository_config_drafts_are_isolated_by_user_and_agent(tmp_path: Path):
    service = SkillService(InMemorySkillRepository(), quarantine_root=tmp_path / "quarantine")
    user_a = uuid4()
    user_b = uuid4()
    agent = uuid4()
    first = service.ensure_config(user_a, agent)
    second = service.ensure_config(user_b, agent)
    third = service.ensure_config(user_a, uuid4())

    assert first["config_version_id"] != second["config_version_id"]
    assert first["config_version_id"] != third["config_version_id"]
    assert first["user_id"] == user_a
    assert second["user_id"] == user_b



def test_configured_search_provider_uses_server_endpoint_without_leaking_credentials(monkeypatch):
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"items":[{"id":"candidate-1","title":"External Skill","description":"safe","source_type":"github","source_uri":"https://github.com/example/skill","source_ref":"commit-1","repository":"example/skill","license":"MIT"}]}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("app.skills.urllib.request.urlopen", fake_urlopen)
    provider = ConfiguredWebSearchProvider(
        "internal", endpoint="https://search.example.test/api",
        api_key="server-secret", github_token="github-secret", timeout_s=3,
    )
    items = provider.search("external", limit=4)
    assert items[0].candidate_id == "candidate-1"
    assert items[0].metadata["repository"] == "example/skill"
    assert captured["timeout"] == 3
    assert captured["request"].full_url == "https://search.example.test/api"
    assert captured["request"].get_header("Authorization") == "Bearer server-secret"
    assert captured["request"].get_header("X-github-token") == "github-secret"



def test_reject_cleans_quarantine_and_retry_reimports_same_record(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source, with_script=False)
    service, repository, _ = _service(tmp_path, source)
    user_id, agent_id = uuid4(), uuid4()

    item = service.start_import(user_id, agent_id, "candidate-1")
    original_path = Path(item.quarantine_path or "")
    assert original_path.is_dir()
    rejected = service.reject_import(user_id, item.import_id)
    assert rejected.status == "rejected"
    assert rejected.quarantine_path is None
    assert not original_path.exists()

    retried = service.retry_import(user_id, item.import_id)
    assert retried.import_id == item.import_id
    assert retried.status == "awaiting_confirmation"
    assert Path(retried.quarantine_path or "").is_dir()
    assert retried.expires_at is not None
    assert repository.get_import(item.import_id).status == "awaiting_confirmation"


def test_expired_import_is_not_confirmable_and_cleans_quarantine(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source, with_script=False)
    service, repository, _ = _service(tmp_path, source)
    user_id, agent_id = uuid4(), uuid4()

    item = service.start_import(user_id, agent_id, "candidate-1")
    expired = replace(item, expires_at=item.requested_at + timedelta(seconds=1))
    repository.save_import(expired)
    result = service.get_import_for_user(user_id, item.import_id)
    assert result.status == "awaiting_confirmation"
    with pytest.raises(SkillImportStateError, match="not expired"):
        service.expire_import(user_id, item.import_id, now=item.requested_at)
    expired = replace(expired, expires_at=item.requested_at)
    repository.save_import(expired)
    result = service.expire_import(user_id, item.import_id, now=item.requested_at + timedelta(seconds=1))
    assert result.status == "expired"
    assert result.quarantine_path is None
    assert not Path(item.quarantine_path or "").exists()
    with pytest.raises(SkillImportStateError, match="state expired"):
        service.confirm_import(user_id, item.import_id)


def test_revoke_removes_skill_from_catalog_and_agent_visibility(tmp_path: Path):
    source = tmp_path / "skill"
    source.mkdir()
    _write_skill_directory(source, with_script=False)
    service, _, _ = _service(tmp_path, source)
    user_id, agent_id = uuid4(), uuid4()

    item = service.start_import(user_id, agent_id, "candidate-1")
    skill = service.confirm_import(user_id, item.import_id)
    assert skill in service.list_available(user_id, agent_id)
    revoked = service.revoke_skill(user_id, skill.skill_id)
    assert revoked.status == "revoked"
    assert all(record.skill_id != skill.skill_id for record in service.list_catalog(user_id))
    assert service.list_available(user_id, agent_id) == []
    with pytest.raises(SkillSecurityError, match="not active"):
        service.load_skill(user_id, agent_id, skill.skill_id)


def test_github_source_adapter_extracts_repository_and_immutable_ref():
    source_type, source_uri, source_ref, repository, metadata = normalize_source_reference(
        source_type="web",
        source_uri="https://github.com/acme/research-skill/tree/release/v1",
        source_ref="",
        metadata={},
    )

    assert source_type == "github"
    assert source_uri == "https://github.com/acme/research-skill"
    assert source_ref == "release/v1"
    assert repository == "acme/research-skill"
    assert metadata["source_adapter"] == "github"


def test_github_source_adapter_prefers_commit_metadata_over_mutable_url():
    normalized = normalize_source_reference(
        source_type="github",
        source_uri="https://github.com/acme/research-skill",
        source_ref="",
        metadata={"sha": "0123456789abcdef0123456789abcdef01234567"},
    )

    assert normalized[2] == "0123456789abcdef0123456789abcdef01234567"
    assert normalized[3] == "acme/research-skill"


def test_skills_sh_source_adapter_preserves_explicit_fixed_version():
    source_type, source_uri, source_ref, repository, metadata = normalize_source_reference(
        source_type="skills.sh",
        source_uri="https://skills.sh/acme/research-skill?ref=v2.1.0",
        source_ref="",
        metadata={},
    )

    assert source_type == "skills.sh"
    assert source_uri == "https://skills.sh/acme/research-skill?ref=v2.1.0"
    assert source_ref == "v2.1.0"
    assert repository == "acme/research-skill"
    assert metadata["source_adapter"] == "skills.sh"


def test_source_adapter_does_not_invent_ref_for_generic_web_url():
    normalized = normalize_source_reference(
        source_type="web",
        source_uri="https://docs.example.test/skill.zip",
        source_ref="",
        metadata={},
    )

    assert normalized[0] == "web"
    assert normalized[2] == ""
    assert normalized[4]["source_adapter"] == "generic"


class _FakeRemoteOpener:
    def __init__(self, response):
        self.response = response

    def open(self, request, timeout):
        return self.response


class _FakeRemoteResponse:
    def __init__(self, payload: bytes, final_url: str):
        self._stream = io.BytesIO(payload)
        self._final_url = final_url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self._final_url

    def read(self, size=-1):
        return self._stream.read(size)


def _skill_zip_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("SKILL.md", "# Remote Skill\nSafe instructions.")
        archive.writestr("references/guide.md", "reference")
    return output.getvalue()


def test_github_remote_archive_download_uses_fixed_ref_and_scans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    payload = _skill_zip_bytes()

    monkeypatch.setattr(
        "app.skills.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    response = _FakeRemoteResponse(payload, "https://codeload.github.com/acme/research-skill/zip/0123456789abcdef")
    opener = _FakeRemoteOpener(response)
    candidate = SearchCandidate(
        candidate_id="github-remote",
        name="Remote GitHub Skill",
        description="remote",
        source_type="github",
        source_uri="https://github.com/acme/research-skill",
        source_ref="0123456789abcdef",
        repository="acme/research-skill",
        license="MIT",
    )
    service = SkillService(
        InMemorySkillRepository(),
        search_provider=MockSearchProvider([candidate]),
        quarantine_root=tmp_path / "quarantine",
        downloader=RemoteSkillDownloader(opener=opener),
    )

    item = service.start_import(uuid4(), uuid4(), "github-remote")

    assert item.status == "awaiting_confirmation"
    assert response is opener.response
    assert set(item.scan_report["manifest"]["files"]) == {"SKILL.md", "references/guide.md"}


def test_skills_sh_remote_download_requires_allowed_public_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "app.skills.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.0.0.8", 443))],
    )
    candidate = SearchCandidate(
        candidate_id="skills-sh-private",
        name="Private Resolution Skill",
        description="remote",
        source_type="skills.sh",
        source_uri="https://skills.sh/acme/research-skill?ref=v1",
        source_ref="v1",
        metadata={"download_uri": "https://skills.sh/download/acme/research-skill/v1.zip"},
    )
    service = SkillService(
        InMemorySkillRepository(),
        search_provider=MockSearchProvider([candidate]),
        quarantine_root=tmp_path / "quarantine",
    )

    item = service.start_import(uuid4(), uuid4(), "skills-sh-private")

    assert item.status == "failed"
    assert "private or reserved" in item.failure_reason


def test_remote_download_rejects_redirect_to_unapproved_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "app.skills.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    opener = _FakeRemoteOpener(
        _FakeRemoteResponse(_skill_zip_bytes(), "https://evil.example.test/skill.zip")
    )
    candidate = SearchCandidate(
        candidate_id="redirected",
        name="Redirected Skill",
        description="remote",
        source_type="github",
        source_uri="https://github.com/acme/research-skill",
        source_ref="immutable-ref",
        repository="acme/research-skill",
    )
    service = SkillService(
        InMemorySkillRepository(),
        search_provider=MockSearchProvider([candidate]),
        quarantine_root=tmp_path / "quarantine",
        downloader=RemoteSkillDownloader(opener=opener),
    )

    item = service.start_import(uuid4(), uuid4(), "redirected")

    assert item.status == "failed"
    assert "domain is not allowed" in item.failure_reason



def test_remote_redirect_handler_validates_each_target_and_limits_hops(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.skills.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    handler = _SafeRedirectHandler(RemoteSkillDownloader._validate_url, 1)

    with pytest.raises(SkillSecurityError, match="domain is not allowed"):
        handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example.test/skill.zip")

    limited = _SafeRedirectHandler(lambda url: None, 1)
    request = urllib.request.Request("https://github.com/acme/original")
    limited.redirect_request(request, None, 302, "Found", {}, "https://github.com/acme/skill")
    with pytest.raises(SkillSecurityError, match="redirect limit"):
        limited.redirect_request(request, None, 302, "Found", {}, "https://github.com/acme/skill")
