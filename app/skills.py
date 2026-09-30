from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import shutil
import socket
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, Sequence
from uuid import UUID, uuid4

from app.repository import NotFoundError, RepositoryError, utcnow
from app.tool_catalog import resolve_tool_code, unknown_tool_codes


class SkillError(RepositoryError):
    """Base error for Skill discovery, import, and execution policy failures."""


class SkillNotFoundError(SkillError):
    pass


class SkillImportStateError(SkillError):
    pass


class SkillSecurityError(SkillError):
    pass


class PublishedConfigNotFound(SkillError):
    """Raised when prefer_draft=False but no published config exists."""


class SearchProviderUnavailable(SkillError):
    pass


@dataclass(frozen=True)
class SearchCandidate:
    candidate_id: str
    name: str
    description: str
    source_type: str
    source_uri: str
    source_ref: str
    license: str = "unknown"
    author: str = "unknown"
    version: str = "unknown"
    repository: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class WebSearchProvider(Protocol):
    def search(self, query: str, *, limit: int = 10) -> list[SearchCandidate]: ...

    def resolve(self, candidate_id: str) -> SearchCandidate: ...


class MockSearchProvider:
    """Deterministic provider used by tests and local development.

    Real providers can implement the same protocol and be selected by server
    configuration. No vendor, API key, or public download URL is embedded here.
    """

    def __init__(self, candidates: list[SearchCandidate] | None = None):
        self._candidates = {item.candidate_id: item for item in candidates or []}

    def register(self, candidate: SearchCandidate) -> None:
        self._candidates[candidate.candidate_id] = candidate

    def search(self, query: str, *, limit: int = 10) -> list[SearchCandidate]:
        needle = (query or "").strip().lower()
        items = list(self._candidates.values())
        if needle:
            items = [
                item
                for item in items
                if needle in f"{item.name} {item.description} {item.source_type}".lower()
            ]
        return items[: max(0, min(limit, 50))]

    def resolve(self, candidate_id: str) -> SearchCandidate:
        try:
            return self._candidates[candidate_id]
        except KeyError as exc:
            raise SkillNotFoundError(f"search candidate not found: {candidate_id}") from exc


class ConfiguredWebSearchProvider:
    """HTTP adapter for a configured server-side search provider.

    The provider is deliberately generic: deployments can point it at an
    internal search gateway without changing Skill records, import states, or
    the LangGraph ToolNode. Credentials are kept in this object and are never
    included in candidate metadata or error messages.
    """

    def __init__(
        self,
        provider_name: str = "",
        *,
        endpoint: str = "",
        api_key: str = "",
        github_token: str = "",
        timeout_s: float = 10.0,
    ):
        self.provider_name = provider_name
        self.endpoint = (endpoint or "").rstrip("/")
        self._api_key = api_key or ""
        self._github_token = github_token or ""
        self.timeout_s = timeout_s
        self._candidates: dict[str, SearchCandidate] = {}

    def _unavailable(self) -> SearchProviderUnavailable:
        if not self.endpoint:
            reason = "endpoint is not configured"
        else:
            reason = "provider is disabled or unavailable"
        return SearchProviderUnavailable(
            f"web search service is not configured: {self.provider_name or 'default'} ({reason})"
        )

    def _request(self, payload: dict[str, Any]) -> Any:
        if not self.endpoint:
            raise self._unavailable()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._github_token:
            headers["X-GitHub-Token"] = self._github_token
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            raise SearchProviderUnavailable("web search service is unavailable") from exc

    @staticmethod
    def _candidate_from_payload(item: dict[str, Any]) -> SearchCandidate:
        candidate_id = str(item.get("candidate_id") or item.get("id") or "").strip()
        name = str(item.get("name") or item.get("title") or "").strip()
        if not candidate_id or not name:
            raise SearchProviderUnavailable("web search service returned an invalid candidate")
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        source_uri = str(item.get("source_uri") or item.get("sourceUri") or item.get("url") or "").strip()
        source_type = str(item.get("source_type") or item.get("sourceType") or "web").strip().lower() or "web"
        source_ref = str(item.get("source_ref") or item.get("sourceRef") or "").strip()
        repository = str(item.get("repository") or metadata.get("repository") or "").strip()
        version = str(item.get("version") or metadata.get("version") or "unknown").strip() or "unknown"
        source_type, source_uri, source_ref, repository, source_metadata = normalize_source_reference(
            source_type=source_type,
            source_uri=source_uri,
            source_ref=source_ref,
            repository=repository,
            metadata=metadata,
        )
        return SearchCandidate(
            candidate_id=candidate_id,
            name=name,
            description=str(item.get("description") or ""),
            source_type=source_type,
            source_uri=source_uri,
            source_ref=source_ref,
            license=str(item.get("license") or metadata.get("license") or "unknown"),
            author=str(item.get("author") or metadata.get("author") or "unknown"),
            version=version,
            repository=repository,
            metadata={**metadata, **source_metadata},
        )

    def search(self, query: str, *, limit: int = 10) -> list[SearchCandidate]:
        payload = self._request({"query": (query or "").strip(), "limit": max(0, min(int(limit), 50))})
        raw_items = payload.get("items", payload.get("results", [])) if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            raise SearchProviderUnavailable("web search service returned an invalid response")
        items = [self._candidate_from_payload(item) for item in raw_items if isinstance(item, dict)]
        self._candidates.update({item.candidate_id: item for item in items})
        return items[: max(0, min(int(limit), 50))]

    def resolve(self, candidate_id: str) -> SearchCandidate:
        try:
            return self._candidates[candidate_id]
        except KeyError as exc:
            raise SkillNotFoundError(f"search candidate not found: {candidate_id}") from exc


def normalize_source_reference(
    *,
    source_type: str,
    source_uri: str,
    source_ref: str,
    repository: str = "",
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str, str, str, dict[str, Any]]:
    """Normalize supported external-source references without contacting them.

    Search providers may use different field names, but imports need one stable
    representation. GitHub URLs are reduced to the repository root while refs
    from ``tree``, ``commit`` and ``releases/tag`` URLs are retained.
    ``skills.sh`` refs are accepted from explicit metadata or URL query/fragment;
    a mutable path is never silently treated as an immutable version.
    """
    metadata = dict(metadata or {})
    parsed = urllib.parse.urlparse((source_uri or "").strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    normalized_type = (source_type or "web").strip().lower() or "web"
    if host == "github.com" or host == "raw.githubusercontent.com" or normalized_type == "github":
        normalized_type = "github"
        parts = [part for part in parsed.path.split("/") if part]
        if host == "github.com" and len(parts) >= 2:
            repository = repository or "/".join(parts[:2])
            if len(parts) >= 4 and parts[2] in {"tree", "commit"}:
                source_ref = source_ref or "/".join(parts[3:])
            elif len(parts) >= 5 and parts[2] == "releases" and parts[3] == "tag":
                source_ref = source_ref or "/".join(parts[4:])
            source_uri = f"https://github.com/{repository}"
        source_ref = source_ref or str(
            metadata.get("commit") or metadata.get("sha") or metadata.get("tag")
            or metadata.get("branch") or metadata.get("ref") or ""
        ).strip()
        metadata["repository"] = repository
        metadata["source_adapter"] = "github"
    elif host == "skills.sh" or normalized_type in {"skills.sh", "skills_sh", "skillssh"}:
        normalized_type = "skills.sh"
        source_ref = source_ref or str(
            metadata.get("commit") or metadata.get("sha") or metadata.get("tag")
            or metadata.get("version") or metadata.get("ref")
            or urllib.parse.parse_qs(parsed.query).get("ref", [""])[0]
            or (parsed.fragment if parsed.fragment and "=" not in parsed.fragment else "")
        ).strip()
        if not repository:
            repository = "/".join(part for part in parsed.path.split("/") if part)
        metadata["repository"] = repository
        metadata["source_adapter"] = "skills.sh"
    else:
        metadata.setdefault("source_adapter", "generic")
    return normalized_type, source_uri, source_ref, repository, metadata


def make_search_provider(settings) -> WebSearchProvider:
    """Build the configured provider without exposing server-side secrets."""
    provider_name = settings.web_search_provider
    if provider_name == "mock":
        return MockSearchProvider()
    if not settings.external_skill_discovery_enabled:
        return ConfiguredWebSearchProvider(provider_name)
    return ConfiguredWebSearchProvider(
        provider_name,
        endpoint=settings.web_search_endpoint,
        api_key=settings.web_search_api_key,
        github_token=settings.github_token,
    )


@dataclass(frozen=True)
class SkillRecord:
    skill_id: UUID
    owner_scope: str
    owner_user_id: UUID | None
    source_type: str
    code: str
    name: str
    description: str
    trigger_description: str
    instructions: str
    source_uri: str | None
    source_ref: str | None
    content_digest: str
    risk_level: str
    approval_mode: str
    execution_policy: dict[str, Any]
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SkillArtifactRecord:
    artifact_id: UUID
    skill_id: UUID
    content_digest: str
    storage_key: str
    manifest: dict[str, Any]
    file_count: int
    total_bytes: int
    created_at: datetime


@dataclass(frozen=True)
class SkillImportRecord:
    import_id: UUID
    user_id: UUID
    target_agent_instance_id: UUID
    source_uri: str
    source_ref: str | None
    skill_path: str | None
    status: str
    source_metadata: dict[str, Any]
    scan_report: dict[str, Any]
    content_digest: str | None
    imported_skill_id: UUID | None
    requested_at: datetime
    completed_at: datetime | None
    confirmed_by: UUID | None
    failure_reason: str
    quarantine_path: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class SkillBindingRecord:
    config_version_id: UUID
    agent_instance_id: UUID
    user_id: UUID
    skill_id: UUID
    priority: int
    enabled: bool


@dataclass(frozen=True)
class AgentConfigToolRecord:
    config_version_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    tool_code: str
    enabled: bool
    created_at: datetime


@dataclass(frozen=True)
class AgentConfigKnowledgeDocumentRecord:
    config_version_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    document_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class AgentSkillRecord:
    skill_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    name: str
    description: str
    instructions: str
    risk_level: str
    approval_mode: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    name: str
    description: str
    prompt: str
    variables: tuple[str, ...]
    tool_codes: tuple[str, ...]
    skill_codes: tuple[str, ...]


REQUIRED_CONFIG_TOOL_CODE = "get_current_datetime"
AGENT_SKILL_RISK_LEVELS = frozenset({"low", "medium", "high"})
AGENT_SKILL_APPROVAL_MODES = frozenset({"auto", "once", "session", "always"})
AGENT_SKILL_STATUSES = frozenset({"active", "archived"})


def normalize_enabled_tool_codes(
    tool_codes: Sequence[Any] | None,
    *,
    require_datetime: bool = False,
) -> list[str]:
    codes: list[str] = []
    for raw in tool_codes or []:
        code = str(raw).strip()
        if not code or code in codes:
            continue
        codes.append(code)
    if require_datetime and REQUIRED_CONFIG_TOOL_CODE not in codes:
        codes.insert(0, REQUIRED_CONFIG_TOOL_CODE)
    return codes


def prefer_required_config_tool(tool_codes: Sequence[Any] | None, *, require_datetime: bool = False) -> list[str]:
    codes = normalize_enabled_tool_codes(tool_codes, require_datetime=require_datetime)
    if REQUIRED_CONFIG_TOOL_CODE not in codes:
        return codes
    return [REQUIRED_CONFIG_TOOL_CODE] + [code for code in codes if code != REQUIRED_CONFIG_TOOL_CODE]


def normalize_knowledge_document_ids(document_ids: Sequence[Any] | None) -> list[UUID]:
    ids: list[UUID] = []
    for raw in document_ids or []:
        document_id = raw if isinstance(raw, UUID) else UUID(str(raw))
        if document_id not in ids:
            ids.append(document_id)
    return ids


class UnknownToolCodeError(SkillError):
    """Raised when a draft config references a tool not in the selectable catalog."""

    def __init__(self, unknown_codes: Sequence[str] | None = None) -> None:
        self.unknown_codes = [str(code) for code in (unknown_codes or [])]
        super().__init__("unknown tool code")


class KnowledgeDocumentNotOwnedError(SkillError):
    """Raised when a draft config selects a document outside the instance."""

    def __init__(self) -> None:
        super().__init__("knowledge document is not owned by this agent instance")


PROMPT_OPTIMIZE_LOCKED_FIELDS = frozenset(
    {
        "enabled_tool_codes",
        "workflow_codes",
        "knowledge_document_ids",
        "skill_ids",
        "risk_level",
        "approval_mode",
    }
)


def validate_draft_tool_codes(tool_codes: Sequence[Any] | None) -> list[str]:
    requested = [str(raw).strip() for raw in (tool_codes or []) if str(raw).strip()]
    unknown = unknown_tool_codes(requested)
    if unknown:
        raise UnknownToolCodeError(unknown)
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in requested:
        code = resolve_tool_code(raw)
        if not code or code in seen:
            continue
        seen.add(code)
        resolved.append(code)
    return prefer_required_config_tool(resolved, require_datetime=True)


def validate_draft_knowledge_document_ids(
    document_ids: Sequence[Any] | None,
    *,
    allowed_document_ids: Sequence[Any],
) -> list[str]:
    requested = [str(item) for item in (document_ids or [])]
    allowed = {str(item) for item in allowed_document_ids}
    if not set(requested).issubset(allowed):
        raise KnowledgeDocumentNotOwnedError()
    return requested


def build_prompt_optimize_result(prompt: str) -> dict[str, str]:
    original = prompt or ""
    stripped = original.strip()
    suffix = (
        "\n\n执行要求：先澄清目标和边界；只使用当前配置允许的知识、Skill 与工具；"
        "无法确认时明确说明；涉及外部副作用时先请求用户审批。"
    )
    optimized = stripped if stripped.endswith(suffix) else (stripped + suffix).strip()
    return {
        "original_prompt": original,
        "optimized_prompt": optimized,
        "change_summary": "补充目标、边界、失败处理和审批前置要求；未修改任何工具、Skill、工作流或服务端安全策略。",
        "risk_notice": "优化结果只返回给草稿编辑器，用户确认保存前不会改变 draft。",
    }


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class InMemorySkillRepository:
    """Business repository for Skill/config state used by tests and local runtime."""

    def __init__(self):
        self.skills: dict[UUID, SkillRecord] = {}
        self.artifacts: dict[UUID, SkillArtifactRecord] = {}
        self.imports: dict[UUID, SkillImportRecord] = {}
        self.bindings: dict[tuple[UUID, UUID], SkillBindingRecord] = {}
        self.config_versions: dict[UUID, dict[str, Any]] = {}
        self.config_tools: dict[tuple[UUID, str], AgentConfigToolRecord] = {}
        self.config_knowledge_documents: dict[tuple[UUID, UUID], AgentConfigKnowledgeDocumentRecord] = {}
        self.agent_skills: dict[UUID, AgentSkillRecord] = {}
        self._seed_platform_skills()

    def _seed_platform_skills(self) -> None:
        seeds = [
            (
                "brand-customer-support",
                "品牌客服 Skill",
                "基于当前配置知识库回答售前、订单和售后问题。",
                "只依据当前实例已启用知识库回答，不承诺未核实的售后结果。",
                "low",
                "auto",
            ),
            (
                "short-video-content",
                "短视频内容创作 Skill",
                "生成选题、分镜、口播稿和风险提示。",
                "不得虚构功效、销量、评价或资质；不确定数据必须标记待核实。",
                "low",
                "auto",
            ),
            (
                "lead-operations",
                "线索运营 Skill",
                "对线索去重、分层并生成跟进建议。",
                "真实触达必须调用已授权工具并通过独立工具审批。",
                "medium",
                "once",
            ),
            (
                "enterprise-knowledge-qna",
                "企业知识库问答 Skill",
                "基于当前实例启用文档回答企业知识问题。",
                "不得跨实例读取知识文档；没有依据时明确说明无法确认。",
                "low",
                "auto",
            ),
        ]
        now = utcnow()
        for code, name, description, instructions, risk, approval in seeds:
            record = SkillRecord(
                skill_id=uuid4(), owner_scope="platform", owner_user_id=None,
                source_type="builtin", code=code, name=name,
                description=description, trigger_description=description,
                instructions=instructions, source_uri=None, source_ref="builtin",
                content_digest=_digest_text(instructions), risk_level=risk,
                approval_mode=approval, execution_policy={"scripts": [], "network": False},
                status="active", version=1, created_at=now, updated_at=now,
            )
            self.skills[record.skill_id] = record

    def list_skills(self, *, user_id: UUID | None = None, include_platform: bool = True) -> list[SkillRecord]:
        return sorted(
            [
                item for item in self.skills.values()
                if item.status == "active"
                and ((include_platform and item.owner_scope == "platform")
                     or (item.owner_scope == "user" and item.owner_user_id == user_id))
            ],
            key=lambda item: (item.owner_scope, item.name),
        )

    def get_skill(self, skill_id: UUID) -> SkillRecord:
        record = self.skills.get(skill_id)
        if record is None:
            raise SkillNotFoundError(f"skill not found: {skill_id}")
        return record

    def save_skill(self, record: SkillRecord) -> SkillRecord:
        self.skills[record.skill_id] = record
        return record

    def find_skill_by_code(self, code: str, *, user_id: UUID | None = None) -> SkillRecord | None:
        for skill in self.skills.values():
            if skill.status == "active" and skill.code == code and (skill.owner_scope == "platform" or skill.owner_user_id == user_id):
                return skill
        return None

    def save_artifact(self, record: SkillArtifactRecord) -> SkillArtifactRecord:
        self.artifacts[record.artifact_id] = record
        return record

    def get_artifact(self, artifact_id: UUID) -> SkillArtifactRecord:
        try:
            return self.artifacts[artifact_id]
        except KeyError as exc:
            raise SkillNotFoundError(f"skill artifact not found: {artifact_id}") from exc

    def get_artifact_for_skill(self, skill_id: UUID) -> SkillArtifactRecord:
        for artifact in self.artifacts.values():
            if artifact.skill_id == skill_id:
                return artifact
        raise SkillNotFoundError(f"skill artifact not found: {skill_id}")

    def save_import(self, record: SkillImportRecord) -> SkillImportRecord:
        self.imports[record.import_id] = record
        return record

    def get_import(self, import_id: UUID) -> SkillImportRecord:
        try:
            return self.imports[import_id]
        except KeyError as exc:
            raise SkillNotFoundError(f"skill import not found: {import_id}") from exc

    def list_imports(self, *, user_id: UUID | None = None) -> list[SkillImportRecord]:
        items = list(self.imports.values())
        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        return sorted(items, key=lambda item: item.requested_at, reverse=True)

    def bind_skill(self, record: SkillBindingRecord) -> SkillBindingRecord:
        self.bindings[(record.config_version_id, record.skill_id)] = record
        return record

    def unbind_skill(self, config_version_id: UUID, skill_id: UUID) -> None:
        self.bindings.pop((config_version_id, skill_id), None)

    def list_bindings(self, config_version_id: UUID) -> list[SkillBindingRecord]:
        return sorted(
            [item for (version_id, _), item in self.bindings.items() if version_id == config_version_id and item.enabled],
            key=lambda item: item.priority,
        )

    def ensure_draft(self, user_id: UUID, agent_instance_id: UUID) -> dict[str, Any]:
        candidates = [
            item for item in self.config_versions.values()
            if item["user_id"] == user_id and item["agent_instance_id"] == agent_instance_id and item["status"] == "draft"
        ]
        if candidates:
            return self._hydrate_config(candidates[0])
        now = utcnow()
        version = {
            "config_version_id": uuid4(), "user_id": user_id,
            "agent_instance_id": agent_instance_id, "version_no": 1,
            "status": "draft", "system_prompt": "", "welcome_message": "",
            "example_questions": [], "enabled_tool_codes": [REQUIRED_CONFIG_TOOL_CODE],
            "workflow_codes": [], "knowledge_document_ids": [], "created_at": now, "updated_at": now,
        }
        self.config_versions[version["config_version_id"]] = version
        self._replace_config_tools(version, [REQUIRED_CONFIG_TOOL_CODE])
        self._replace_config_knowledge_documents(version, [])
        return self._hydrate_config(version)

    def list_config_versions(self, user_id: UUID, agent_instance_id: UUID) -> list[dict[str, Any]]:
        return sorted(
            [self._hydrate_config(item) for item in self.config_versions.values()
             if item["user_id"] == user_id and item["agent_instance_id"] == agent_instance_id],
            key=lambda item: item["version_no"], reverse=True,
        )

    def get_config(self, config_version_id: UUID) -> dict[str, Any]:
        return self._hydrate_config(self._get_config_row(config_version_id))

    def get_draft(self, user_id: UUID, agent_instance_id: UUID) -> dict[str, Any]:
        return self.ensure_draft(user_id, agent_instance_id)

    def get_effective_config(self, user_id: UUID, agent_instance_id: UUID, *, prefer_draft: bool = False) -> dict[str, Any]:
        candidates = [
            item for item in self.config_versions.values()
            if item["user_id"] == user_id and item["agent_instance_id"] == agent_instance_id
        ]
        if prefer_draft:
            matching = [item for item in candidates if item["status"] == "draft"]
            if not matching:
                return self.ensure_draft(user_id, agent_instance_id)
            return self._hydrate_config(max(matching, key=lambda item: item["version_no"]))
        matching = [item for item in candidates if item["status"] == "published"]
        if not matching:
            raise PublishedConfigNotFound(f"published config not found for agent instance {agent_instance_id}")
        return self._hydrate_config(max(matching, key=lambda item: item["version_no"]))

    def update_config(self, config_version_id: UUID, **fields: Any) -> dict[str, Any]:
        config = self._get_config_row(config_version_id)
        tool_codes = fields.pop("enabled_tool_codes", None)
        document_ids = fields.pop("knowledge_document_ids", None)
        config.update(fields)
        if tool_codes is not None:
            self._replace_config_tools(config, tool_codes)
        if document_ids is not None:
            self._replace_config_knowledge_documents(config, document_ids)
        config["updated_at"] = utcnow()
        return self._hydrate_config(config)

    def publish_config(self, user_id: UUID, agent_instance_id: UUID) -> dict[str, Any]:
        draft = self._hydrate_config(self.get_draft(user_id, agent_instance_id))
        draft["status"] = "published"
        draft["updated_at"] = utcnow()
        published_id = draft["config_version_id"]
        new_draft = dict(draft)
        new_draft.update({
            "config_version_id": uuid4(),
            "version_no": draft["version_no"] + 1,
            "status": "draft",
            "created_at": utcnow(),
            "updated_at": utcnow(),
            "example_questions": list(draft.get("example_questions") or []),
            "enabled_tool_codes": list(draft.get("enabled_tool_codes") or []),
            "workflow_codes": list(draft.get("workflow_codes") or []),
            "knowledge_document_ids": list(draft.get("knowledge_document_ids") or []),
        })
        self.config_versions[new_draft["config_version_id"]] = new_draft
        self._copy_config_relations(published_id, new_draft)
        return self._hydrate_config(draft)

    def _get_config_row(self, config_version_id: UUID) -> dict[str, Any]:
        try:
            return self.config_versions[config_version_id]
        except KeyError as exc:
            raise NotFoundError(f"config version not found: {config_version_id}") from exc

    def _hydrate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        version_id = config["config_version_id"]
        tool_rows = [item for (item_version, _), item in self.config_tools.items() if item_version == version_id]
        if not tool_rows:
            jsonb_tools = normalize_enabled_tool_codes(config.get("enabled_tool_codes"))
            if jsonb_tools:
                self._replace_config_tools(config, jsonb_tools)
                tool_rows = [item for (item_version, _), item in self.config_tools.items() if item_version == version_id]
        if tool_rows:
            enabled = []
            for item in tool_rows:
                if item.enabled and item.tool_code not in enabled:
                    enabled.append(item.tool_code)
            if REQUIRED_CONFIG_TOOL_CODE not in enabled:
                self._replace_config_tools(config, enabled)
                enabled = prefer_required_config_tool(enabled, require_datetime=True)
            config["enabled_tool_codes"] = prefer_required_config_tool(enabled)
        else:
            config["enabled_tool_codes"] = []

        knowledge_rows = [
            item for (item_version, _), item in self.config_knowledge_documents.items() if item_version == version_id
        ]
        if not knowledge_rows:
            jsonb_docs = list(config.get("knowledge_document_ids") or [])
            if jsonb_docs:
                self._replace_config_knowledge_documents(config, jsonb_docs)
                knowledge_rows = [
                    item for (item_version, _), item in self.config_knowledge_documents.items() if item_version == version_id
                ]
        config["knowledge_document_ids"] = [item.document_id for item in knowledge_rows]
        return config

    def _replace_config_tools(self, config: dict[str, Any], tool_codes: Sequence[Any] | None) -> None:
        version_id = config["config_version_id"]
        codes = normalize_enabled_tool_codes(tool_codes, require_datetime=True)
        for key in [item for item in self.config_tools if item[0] == version_id]:
            del self.config_tools[key]
        now = utcnow()
        for code in codes:
            self.config_tools[(version_id, code)] = AgentConfigToolRecord(
                config_version_id=version_id,
                user_id=config["user_id"],
                agent_instance_id=config["agent_instance_id"],
                tool_code=code,
                enabled=True,
                created_at=now,
            )
        config["enabled_tool_codes"] = list(codes)

    def _replace_config_knowledge_documents(self, config: dict[str, Any], document_ids: Sequence[Any] | None) -> None:
        version_id = config["config_version_id"]
        ids = normalize_knowledge_document_ids(document_ids)
        for key in [item for item in self.config_knowledge_documents if item[0] == version_id]:
            del self.config_knowledge_documents[key]
        now = utcnow()
        for document_id in ids:
            self.config_knowledge_documents[(version_id, document_id)] = AgentConfigKnowledgeDocumentRecord(
                config_version_id=version_id,
                user_id=config["user_id"],
                agent_instance_id=config["agent_instance_id"],
                document_id=document_id,
                created_at=now,
            )
        config["knowledge_document_ids"] = list(ids)

    def _copy_config_relations(self, source_version_id: UUID, target: dict[str, Any]) -> None:
        target_id = target["config_version_id"]
        now = utcnow()
        for item in [row for (version_id, _), row in self.config_tools.items() if version_id == source_version_id]:
            self.config_tools[(target_id, item.tool_code)] = AgentConfigToolRecord(
                config_version_id=target_id,
                user_id=target["user_id"],
                agent_instance_id=target["agent_instance_id"],
                tool_code=item.tool_code,
                enabled=item.enabled,
                created_at=now,
            )
        for item in [row for (version_id, _), row in self.config_knowledge_documents.items() if version_id == source_version_id]:
            self.config_knowledge_documents[(target_id, item.document_id)] = AgentConfigKnowledgeDocumentRecord(
                config_version_id=target_id,
                user_id=target["user_id"],
                agent_instance_id=target["agent_instance_id"],
                document_id=item.document_id,
                created_at=now,
            )

    def save_agent_skill(self, record: AgentSkillRecord) -> AgentSkillRecord:
        validated = _validate_agent_skill(record)
        self.agent_skills[validated.skill_id] = validated
        return validated

    def get_agent_skill(self, skill_id: UUID) -> AgentSkillRecord:
        try:
            return self.agent_skills[skill_id]
        except KeyError as exc:
            raise SkillNotFoundError(f"agent skill not found: {skill_id}") from exc

    def list_agent_skills(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        include_archived: bool = False,
    ) -> list[AgentSkillRecord]:
        items = [
            item for item in self.agent_skills.values()
            if item.user_id == user_id and item.agent_instance_id == agent_instance_id
        ]
        if not include_archived:
            items = [item for item in items if item.status == "active"]
        return sorted(items, key=lambda item: item.created_at)

    def update_agent_skill(self, skill_id: UUID, **fields: Any) -> AgentSkillRecord:
        current = self.get_agent_skill(skill_id)
        allowed = {"name", "description", "instructions", "risk_level", "approval_mode", "status"}
        values = {key: value for key, value in fields.items() if key in allowed and value is not None}
        updated = AgentSkillRecord(
            skill_id=current.skill_id,
            user_id=current.user_id,
            agent_instance_id=current.agent_instance_id,
            name=values.get("name", current.name),
            description=values.get("description", current.description),
            instructions=values.get("instructions", current.instructions),
            risk_level=values.get("risk_level", current.risk_level),
            approval_mode=values.get("approval_mode", current.approval_mode),
            status=values.get("status", current.status),
            created_at=current.created_at,
            updated_at=utcnow(),
        )
        return self.save_agent_skill(updated)

    def archive_agent_skill(self, skill_id: UUID) -> AgentSkillRecord:
        return self.update_agent_skill(skill_id, status="archived")


def _validate_agent_skill(record: AgentSkillRecord) -> AgentSkillRecord:
    name = record.name.strip()
    if not name:
        raise SkillError("agent skill name is required")
    if record.risk_level not in AGENT_SKILL_RISK_LEVELS:
        raise SkillError(f"invalid risk_level: {record.risk_level}")
    if record.approval_mode not in AGENT_SKILL_APPROVAL_MODES:
        raise SkillError(f"invalid approval_mode: {record.approval_mode}")
    if record.status not in AGENT_SKILL_STATUSES:
        raise SkillError(f"invalid status: {record.status}")
    return AgentSkillRecord(
        skill_id=record.skill_id,
        user_id=record.user_id,
        agent_instance_id=record.agent_instance_id,
        name=name,
        description=record.description,
        instructions=record.instructions,
        risk_level=record.risk_level,
        approval_mode=record.approval_mode,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )



class SkillScanner:
    MAX_FILES = 2_000
    MAX_TOTAL_BYTES = 20 * 1024 * 1024
    MAX_FILE_BYTES = 5 * 1024 * 1024
    SECRET_PATTERNS = (
        re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
    )

    def scan(self, root: Path) -> dict[str, Any]:
        root = root.resolve()
        if not root.is_dir():
            raise SkillSecurityError("quarantine root is not a directory")
        files: list[str] = []
        scripts: list[str] = []
        warnings: list[str] = []
        total = 0
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise SkillSecurityError(f"symlink is not allowed: {path.relative_to(root)}")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative.startswith("../") or "\x00" in relative:
                raise SkillSecurityError(f"unsafe path: {relative}")
            size = path.stat().st_size
            if size > self.MAX_FILE_BYTES:
                raise SkillSecurityError(f"file too large: {relative}")
            total += size
            if total > self.MAX_TOTAL_BYTES:
                raise SkillSecurityError("skill package is too large")
            files.append(relative)
            suffix = path.suffix.lower()
            if suffix in {".py", ".js", ".ts", ".sh", ".bash"}:
                scripts.append(relative)
            content = path.read_bytes()
            digest.update(relative.encode("utf-8"))
            digest.update(content)
            if suffix in {".md", ".txt", ".py", ".js", ".ts", ".sh", ".bash", ".json", ".yaml", ".yml"}:
                text = content.decode("utf-8", errors="replace")
                if any(pattern.search(text) for pattern in self.SECRET_PATTERNS):
                    warnings.append(f"possible secret: {relative}")
        if len(files) > self.MAX_FILES:
            raise SkillSecurityError("skill package contains too many files")
        skill_md = root / "SKILL.md"
        if not skill_md.is_file():
            raise SkillSecurityError("SKILL.md is required")
        manifest = {
            "files": files, "scripts": scripts, "has_network": False,
            "has_write": bool(scripts), "warnings": warnings,
            "license": _read_license(root),
        }
        risk = "high" if scripts or warnings else "medium"
        return {
            "manifest": manifest, "file_count": len(files), "total_bytes": total,
            "content_digest": digest.hexdigest(), "risk_level": risk,
            "script_types": sorted({Path(item).suffix.lower() for item in scripts}),
        }


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, validator, max_redirects: int):
        super().__init__()
        self._validator = validator
        self._max_redirects = max_redirects
        self._redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl, method=None):
        self._redirect_count += 1
        if self._redirect_count > self._max_redirects:
            raise SkillSecurityError("remote Skill download exceeded redirect limit")
        self._validator(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class RemoteSkillDownloader:
    """Download only approved public Skill source archives into quarantine.

    The downloader is intentionally narrower than a general HTTP client: it
    accepts HTTPS from GitHub/skills.sh only, derives GitHub archives from the
    immutable candidate ref, rejects private/reserved DNS targets, validates
    the final redirect target, and bounds the compressed response size.
    """

    ALLOWED_HOSTS = {
        "github.com",
        "codeload.github.com",
        "raw.githubusercontent.com",
        "skills.sh",
    }
    MAX_ARCHIVE_BYTES = SkillScanner.MAX_TOTAL_BYTES
    MAX_REDIRECTS = 3

    def __init__(self, *, timeout_s: float = 15.0, opener: Any | None = None):
        self.timeout_s = timeout_s
        self.opener = opener

    @classmethod
    def _validate_url(cls, url: str) -> urllib.parse.ParseResult:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https":
            raise SkillSecurityError("remote Skill download requires HTTPS")
        if not host or host not in cls.ALLOWED_HOSTS:
            raise SkillSecurityError("remote Skill source domain is not allowed")
        try:
            port = parsed.port
        except ValueError as exc:
            raise SkillSecurityError("remote Skill source URL has unsafe authority") from exc
        if parsed.username or parsed.password or port not in (None, 443):
            raise SkillSecurityError("remote Skill source URL has unsafe authority")
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError) as exc:
            raise SkillSecurityError("remote Skill source host cannot be resolved safely") from exc
        if not addresses or any(
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
            for address in addresses
        ):
            raise SkillSecurityError("remote Skill source resolves to a private or reserved address")
        return parsed

    @classmethod
    def _download_url(cls, candidate: SearchCandidate) -> str:
        source_uri = candidate.source_uri.strip()
        parsed = urllib.parse.urlparse(source_uri)
        host = (parsed.hostname or "").lower().rstrip(".")
        if candidate.source_type == "github" or host == "github.com":
            repository = candidate.repository or str(candidate.metadata.get("repository") or "")
            if not repository or not candidate.source_ref:
                raise SkillSecurityError("GitHub Skill requires repository and fixed source ref")
            safe_repository = urllib.parse.quote(repository.strip("/"), safe="/")
            safe_ref = urllib.parse.quote(candidate.source_ref, safe="")
            return f"https://codeload.github.com/{safe_repository}/zip/{safe_ref}"
        if candidate.source_type == "skills.sh" or host == "skills.sh":
            download_uri = str(candidate.metadata.get("download_uri") or source_uri).strip()
            cls._validate_url(download_uri)
            return download_uri
        raise SkillSecurityError("remote URL download is disabled for this Skill source")

    def download(self, candidate: SearchCandidate, destination: Path) -> None:
        url = self._download_url(candidate)
        self._validate_url(url)
        destination.mkdir(parents=True, exist_ok=False)
        archive_path = destination.parent / f".{destination.name}.download"
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/zip"}, method="GET")
            opener = self.opener or urllib.request.build_opener(
                _SafeRedirectHandler(self._validate_url, self.MAX_REDIRECTS)
            )
            with opener.open(request, timeout=self.timeout_s) as response:
                final_url = response.geturl() if hasattr(response, "geturl") else url
                self._validate_url(final_url)
                total = 0
                with archive_path.open("wb") as target:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.MAX_ARCHIVE_BYTES:
                            raise SkillSecurityError("remote Skill archive is too large")
                        target.write(chunk)
            _extract_zip_safe(archive_path, destination)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SkillSecurityError("remote Skill download failed") from exc
        finally:
            archive_path.unlink(missing_ok=True)
            if not (destination / "SKILL.md").is_file():
                shutil.rmtree(destination, ignore_errors=True)


class SkillService:
    def __init__(
        self,
        repository: InMemorySkillRepository,
        *,
        search_provider: WebSearchProvider | None = None,
        quarantine_root: Path | None = None,
        scanner: SkillScanner | None = None,
        downloader: RemoteSkillDownloader | None = None,
    ):
        self.repository = repository
        self.search_provider = search_provider or MockSearchProvider()
        self.quarantine_root = (quarantine_root or Path(tempfile.gettempdir()) / "agentdemo-skill-quarantine").resolve()
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self.scanner = scanner or SkillScanner()
        self.downloader = downloader or RemoteSkillDownloader()
        self._search_cache: dict[str, SearchCandidate] = {}

    def search(self, query: str, *, limit: int = 10) -> list[SearchCandidate]:
        candidates = self.search_provider.search(query, limit=limit)
        self._search_cache.update({item.candidate_id: item for item in candidates})
        return candidates

    def list_catalog(self, user_id: UUID | None = None) -> list[SkillRecord]:
        return self.repository.list_skills(user_id=user_id)

    def list_private_registry(self, user_id: UUID) -> list[SkillRecord]:
        """Return only active Skills owned by the current user's private registry."""
        return [
            skill
            for skill in self.repository.list_skills(user_id=user_id, include_platform=False)
            if skill.owner_scope == "user" and skill.owner_user_id == user_id
        ]

    def ensure_config(self, user_id: UUID, agent_instance_id: UUID) -> dict[str, Any]:
        return self.repository.ensure_draft(user_id, agent_instance_id)

    def get_effective_config(self, user_id: UUID, agent_instance_id: UUID, *, prefer_draft: bool = False) -> dict[str, Any]:
        return self.repository.get_effective_config(user_id, agent_instance_id, prefer_draft=prefer_draft)

    def list_config_versions(self, user_id: UUID, agent_instance_id: UUID) -> list[dict[str, Any]]:
        return self.repository.list_config_versions(user_id, agent_instance_id)

    def get_import_for_user(self, user_id: UUID, import_id: UUID) -> SkillImportRecord:
        record = self.repository.get_import(import_id)
        if record.user_id != user_id:
            raise SkillSecurityError("skill import does not belong to current user")
        return record

    def set_config_skills(self, user_id: UUID, agent_instance_id: UUID, skill_ids: list[UUID]) -> list[SkillRecord]:
        config = self.ensure_config(user_id, agent_instance_id)
        wanted: list[SkillRecord] = []
        seen: set[UUID] = set()
        for skill_id in skill_ids:
            if skill_id in seen:
                continue
            skill = self.repository.get_skill(skill_id)
            if skill.owner_scope == "user" and skill.owner_user_id != user_id:
                raise SkillSecurityError("skill does not belong to current user")
            if skill.status != "active":
                raise SkillSecurityError("skill is not active")
            seen.add(skill_id)
            wanted.append(skill)
        for binding in self.repository.list_bindings(config["config_version_id"]):
            if binding.skill_id not in seen:
                self.repository.unbind_skill(config["config_version_id"], binding.skill_id)
        for priority, skill in enumerate(wanted, start=1):
            self.repository.bind_skill(SkillBindingRecord(config["config_version_id"], agent_instance_id, user_id, skill.skill_id, priority, True))
        return wanted

    def bind_platform_skill(self, user_id: UUID, agent_instance_id: UUID, skill_id: UUID, *, enabled: bool = True, priority: int = 100) -> SkillBindingRecord:
        config = self.ensure_config(user_id, agent_instance_id)
        skill = self.repository.get_skill(skill_id)
        if skill.owner_scope == "user" and skill.owner_user_id != user_id:
            raise SkillSecurityError("skill does not belong to current user")
        if skill.owner_scope not in {"platform", "user"}:
            raise SkillSecurityError("unsupported skill owner scope")
        return self.repository.bind_skill(SkillBindingRecord(config["config_version_id"], agent_instance_id, user_id, skill_id, priority, enabled))

    def create_declarative_skill(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        name: str,
        description: str = "",
        instructions: str = "",
        risk_level: str = "medium",
        approval_mode: str = "once",
    ) -> SkillRecord:
        now = utcnow()
        agent_skill = self.repository.save_agent_skill(
            AgentSkillRecord(
                skill_id=uuid4(),
                user_id=user_id,
                agent_instance_id=agent_instance_id,
                name=name or "",
                description=description or "",
                instructions=instructions or "",
                risk_level=risk_level or "medium",
                approval_mode=approval_mode or "once",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        registry = self._registry_from_agent_skill(agent_skill)
        self.repository.save_skill(registry)
        config = self.ensure_config(user_id, agent_instance_id)
        bindings = self.repository.list_bindings(config["config_version_id"])
        priority = max((item.priority for item in bindings), default=0) + 1
        self.repository.bind_skill(
            SkillBindingRecord(
                config["config_version_id"],
                agent_instance_id,
                user_id,
                agent_skill.skill_id,
                priority,
                True,
            )
        )
        return registry

    def update_declarative_skill(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        skill_id: UUID,
        **fields: Any,
    ) -> SkillRecord:
        current = self.repository.get_agent_skill(skill_id)
        if current.user_id != user_id or current.agent_instance_id != agent_instance_id:
            raise SkillNotFoundError(f"agent skill not found: {skill_id}")
        updated = self.repository.update_agent_skill(skill_id, **fields)
        existing = self.repository.get_skill(skill_id)
        mirrored = self._registry_from_agent_skill(updated, existing=existing)
        return self.repository.save_skill(mirrored)

    def remove_instance_skill(self, user_id: UUID, agent_instance_id: UUID, skill_id: UUID) -> list[SkillRecord]:
        current = self.list_available(user_id, agent_instance_id)
        remaining = [item.skill_id for item in current if item.skill_id != skill_id]
        items = self.set_config_skills(user_id, agent_instance_id, remaining)
        try:
            agent_skill = self.repository.get_agent_skill(skill_id)
        except SkillNotFoundError:
            return items
        if agent_skill.user_id != user_id or agent_skill.agent_instance_id != agent_instance_id:
            return items
        archived = self.repository.archive_agent_skill(skill_id)
        existing = self.repository.get_skill(skill_id)
        self.repository.save_skill(self._registry_from_agent_skill(archived, existing=existing))
        return items

    def _unique_user_skill_code(self, user_id: UUID, name: str) -> str:
        raw = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "").strip().lower()).strip("-")[:80]
        base = raw or "custom-skill"
        code = base
        suffix = 1
        while self.repository.find_skill_by_code(code, user_id=user_id) is not None:
            suffix += 1
            code = f"{base}-{suffix}"
        return code

    def _registry_from_agent_skill(
        self,
        agent_skill: AgentSkillRecord,
        *,
        existing: SkillRecord | None = None,
    ) -> SkillRecord:
        status = "archived" if agent_skill.status == "archived" else "active"
        if existing is not None and existing.status == "revoked":
            status = "revoked"
        if existing is None:
            return SkillRecord(
                skill_id=agent_skill.skill_id,
                owner_scope="user",
                owner_user_id=agent_skill.user_id,
                source_type="custom",
                code=self._unique_user_skill_code(agent_skill.user_id, agent_skill.name),
                name=agent_skill.name,
                description=agent_skill.description,
                trigger_description=agent_skill.description or agent_skill.name,
                instructions=agent_skill.instructions,
                source_uri=None,
                source_ref="custom",
                content_digest=_digest_text(agent_skill.instructions),
                risk_level=agent_skill.risk_level,
                approval_mode=agent_skill.approval_mode,
                execution_policy={"scripts": [], "network": False},
                status=status,
                version=1,
                created_at=agent_skill.created_at,
                updated_at=agent_skill.updated_at,
            )
        return SkillRecord(
            skill_id=existing.skill_id,
            owner_scope="user",
            owner_user_id=agent_skill.user_id,
            source_type="custom",
            code=existing.code,
            name=agent_skill.name,
            description=agent_skill.description,
            trigger_description=agent_skill.description or agent_skill.name,
            instructions=agent_skill.instructions,
            source_uri=existing.source_uri,
            source_ref=existing.source_ref or "custom",
            content_digest=_digest_text(agent_skill.instructions),
            risk_level=agent_skill.risk_level,
            approval_mode=agent_skill.approval_mode,
            execution_policy=dict(existing.execution_policy),
            status=status,
            version=existing.version + 1,
            created_at=existing.created_at,
            updated_at=agent_skill.updated_at,
        )

    def list_available(self, user_id: UUID, agent_instance_id: UUID) -> list[SkillRecord]:
        config = self.ensure_config(user_id, agent_instance_id)
        records: list[SkillRecord] = []
        for binding in self.repository.list_bindings(config["config_version_id"]):
            skill = self.repository.get_skill(binding.skill_id)
            if skill.status == "active" and (skill.owner_scope == "platform" or skill.owner_user_id == user_id):
                records.append(skill)
        return records

    def load_skill_for_scope(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID,
        skill_id: UUID,
        *,
        approvals=None,
        thread_id: str | None = None,
    ) -> SkillRecord:
        """Load only a bound Skill in the caller's exact config/approval scope."""
        config = self.repository.get_config(config_version_id)
        if config["user_id"] != user_id or config["agent_instance_id"] != agent_instance_id:
            raise SkillSecurityError("skill config does not belong to current scope")
        skill = self.repository.get_skill(skill_id)
        if skill.owner_scope == "user" and skill.owner_user_id != user_id:
            raise SkillSecurityError("skill does not belong to current user")
        if skill not in [
            self.repository.get_skill(binding.skill_id)
            for binding in self.repository.list_bindings(config_version_id)
            if binding.skill_id == skill_id
        ]:
            raise SkillSecurityError("skill is not enabled for this agent configuration")
        if skill.owner_scope != "platform" or skill.approval_mode != "auto":
            if approvals is None or not thread_id or not approvals.ensure(
                user_id=user_id, agent_instance_id=agent_instance_id,
                config_version_id=config_version_id, thread_id=thread_id,
                approval_kind="skill", resource_code=skill.code,
            ):
                raise SkillSecurityError("skill approval is required")
        return skill

    def get_artifact_for_skill(self, skill_id: UUID) -> SkillArtifactRecord:
        getter = getattr(self.repository, "get_artifact_for_skill", None)
        if not callable(getter):
            raise SkillNotFoundError(f"skill artifact not found: {skill_id}")
        return getter(skill_id)

    def start_import(self, user_id: UUID, agent_instance_id: UUID, candidate_id: str) -> SkillImportRecord:
        candidate = self._search_cache.get(candidate_id)
        if candidate is None:
            candidate = self.search_provider.resolve(candidate_id)
            self._search_cache[candidate_id] = candidate
        if not candidate.source_ref or not candidate.source_ref.strip():
            raise SkillSecurityError("external Skill must use a fixed commit, tag, or immutable ref")
        import_id = uuid4()
        quarantine = self.quarantine_root / str(import_id)
        record = SkillImportRecord(
            import_id=import_id, user_id=user_id, target_agent_instance_id=agent_instance_id,
            source_uri=candidate.source_uri, source_ref=candidate.source_ref,
            skill_path=None, status="downloading", source_metadata={
                "candidate_id": candidate.candidate_id, "name": candidate.name,
                "source_type": candidate.source_type, "author": candidate.author,
                "license": candidate.license, "version": candidate.version,
            }, scan_report={}, content_digest=None, imported_skill_id=None,
            requested_at=utcnow(), completed_at=None, confirmed_by=None,
            failure_reason="", quarantine_path=str(quarantine), expires_at=utcnow() + timedelta(hours=24),
        )
        self.repository.save_import(record)
        return self._process_import(record, candidate)

    def _process_import(self, record: SkillImportRecord, candidate: SearchCandidate) -> SkillImportRecord:
        quarantine = Path(record.quarantine_path or (self.quarantine_root / str(record.import_id)))
        try:
            self._materialize_candidate(candidate, quarantine)
            report = self.scanner.scan(quarantine)
            record = SkillImportRecord(**{
                **record.__dict__, "status": "awaiting_confirmation", "scan_report": report,
                "content_digest": report["content_digest"], "completed_at": None,
            })
        except Exception as exc:
            record = SkillImportRecord(**{
                **record.__dict__, "status": "failed", "failure_reason": str(exc),
                "completed_at": utcnow(),
            })
        return self.repository.save_import(record)

    def confirm_import(self, user_id: UUID, import_id: UUID) -> SkillRecord:
        item = self._owned_import(user_id, import_id)
        if item.expires_at is not None and item.expires_at <= utcnow():
            self.expire_import(user_id, import_id)
            raise SkillImportStateError("import has expired")
        if item.status != "awaiting_confirmation":
            raise SkillImportStateError(f"import cannot be confirmed from state {item.status}")
        report = item.scan_report
        if not item.quarantine_path or not (Path(item.quarantine_path) / "SKILL.md").is_file():
            raise SkillImportStateError("quarantine package is no longer available; retry the import")
        meta = item.source_metadata
        code = _safe_code(meta.get("name") or "external-skill")
        base = code
        n = 1
        while self.repository.find_skill_by_code(code, user_id=user_id) is not None:
            n += 1
            code = f"{base}-{n}"
        skill_md = Path(item.quarantine_path or "") / "SKILL.md"
        instructions = skill_md.read_text(encoding="utf-8", errors="replace")[:100_000]
        now = utcnow()
        skill = SkillRecord(
            skill_id=uuid4(), owner_scope="user", owner_user_id=user_id,
            source_type="external", code=code, name=meta.get("name") or code,
            description=f"Imported from {item.source_uri}", trigger_description="External Skill",
            instructions=instructions, source_uri=item.source_uri, source_ref=item.source_ref,
            content_digest=item.content_digest or report["content_digest"],
            risk_level=report.get("risk_level", "medium"),
            approval_mode="always" if report.get("risk_level") == "high" else "once",
            execution_policy={"scripts": report["manifest"].get("scripts", []), "network": False, "read_paths": [], "write_paths": ["workspace"]},
            status="active", version=1, created_at=now, updated_at=now,
        )
        self.repository.save_skill(skill)
        artifact = SkillArtifactRecord(
            artifact_id=uuid4(), skill_id=skill.skill_id, content_digest=skill.content_digest,
            storage_key=item.quarantine_path or "", manifest=report["manifest"],
            file_count=report["file_count"], total_bytes=report["total_bytes"], created_at=now,
        )
        self.repository.save_artifact(artifact)
        self.bind_platform_skill(user_id, item.target_agent_instance_id, skill.skill_id, priority=100)
        updated = SkillImportRecord(**{**item.__dict__, "status": "imported", "imported_skill_id": skill.skill_id, "completed_at": utcnow(), "confirmed_by": user_id})
        self.repository.save_import(updated)
        return skill

    def reject_import(self, user_id: UUID, import_id: UUID) -> SkillImportRecord:
        item = self._owned_import(user_id, import_id)
        if item.status not in {"awaiting_confirmation", "failed", "scanning", "downloading", "expired"}:
            raise SkillImportStateError(f"import cannot be rejected from state {item.status}")
        self._cleanup_quarantine(item)
        updated = SkillImportRecord(**{
            **item.__dict__, "status": "rejected", "completed_at": utcnow(),
            "confirmed_by": user_id, "quarantine_path": None,
        })
        return self.repository.save_import(updated)

    def retry_import(self, user_id: UUID, import_id: UUID) -> SkillImportRecord:
        item = self._owned_import(user_id, import_id)
        if item.status not in {"failed", "rejected", "expired"}:
            raise SkillImportStateError(f"import cannot be retried from state {item.status}")
        candidate_id = str(item.source_metadata.get("candidate_id") or "")
        if not candidate_id:
            raise SkillImportStateError("import has no retryable search candidate")
        candidate = self._search_cache.get(candidate_id) or self.search_provider.resolve(candidate_id)
        if not candidate.source_ref or not candidate.source_ref.strip():
            raise SkillSecurityError("external Skill must use a fixed commit, tag, or immutable ref")
        self._cleanup_quarantine(item)
        refreshed = SkillImportRecord(**{
            **item.__dict__, "status": "downloading", "scan_report": {},
            "content_digest": None, "imported_skill_id": None, "completed_at": None,
            "confirmed_by": None, "failure_reason": "", "quarantine_path": str(self.quarantine_root / str(item.import_id)),
            "requested_at": utcnow(), "expires_at": utcnow() + timedelta(hours=24),
        })
        self.repository.save_import(refreshed)
        return self._process_import(refreshed, candidate)

    def revoke_skill(self, user_id: UUID, skill_id: UUID) -> SkillRecord:
        skill = self.repository.get_skill(skill_id)
        if skill.owner_scope != "user" or skill.owner_user_id != user_id:
            raise SkillSecurityError("only the current user's external Skill can be revoked")
        self._unbind_skill_everywhere(skill_id)
        revoked = SkillRecord(**{**skill.__dict__, "status": "revoked", "updated_at": utcnow(), "version": skill.version + 1})
        return self.repository.save_skill(revoked)

    def expire_import(self, user_id: UUID, import_id: UUID, *, now: datetime | None = None) -> SkillImportRecord:
        item = self._owned_import(user_id, import_id)
        current = now or utcnow()
        if item.status != "awaiting_confirmation":
            raise SkillImportStateError(f"import cannot expire from state {item.status}")
        if item.expires_at is not None and item.expires_at > current:
            raise SkillImportStateError("import has not expired")
        self._cleanup_quarantine(item)
        updated = SkillImportRecord(**{
            **item.__dict__, "status": "expired", "completed_at": current,
            "quarantine_path": None,
        })
        return self.repository.save_import(updated)

    def _owned_import(self, user_id: UUID, import_id: UUID) -> SkillImportRecord:
        item = self.repository.get_import(import_id)
        if item.user_id != user_id:
            raise SkillSecurityError("skill import does not belong to current user")
        return item

    def _cleanup_quarantine(self, item: SkillImportRecord) -> None:
        if not item.quarantine_path:
            return
        path = Path(item.quarantine_path)
        if path.exists() or path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)

    def _unbind_skill_everywhere(self, skill_id: UUID) -> None:
        for config in list(self.repository.config_versions.values()) if hasattr(self.repository, "config_versions") else []:
            self.repository.unbind_skill(config["config_version_id"], skill_id)
        cleanup = getattr(self.repository, "unbind_skill_everywhere", None)
        if callable(cleanup):
            cleanup(skill_id)

    def load_skill(self, user_id: UUID, agent_instance_id: UUID, skill_id: UUID) -> SkillRecord:
        skill = self.repository.get_skill(skill_id)
        if skill.status != "active":
            raise SkillSecurityError("skill is not active")
        if skill.owner_scope == "user" and skill.owner_user_id != user_id:
            raise SkillSecurityError("skill does not belong to current user")
        if skill not in self.list_available(user_id, agent_instance_id):
            raise SkillSecurityError("skill is not enabled for this agent configuration")
        return skill

    def _materialize_candidate(self, candidate: SearchCandidate, destination: Path) -> None:
        source = candidate.source_uri.strip()
        if source.startswith(("http://", "https://", "ftp://")):
            self.downloader.download(candidate, destination)
            return
        if source.startswith("file://"):
            source = source[7:]
        source_path = Path(source).expanduser()
        if source_path.is_symlink() or not source_path.exists():
            raise SkillSecurityError("mock candidate source is unavailable or is a symlink")
        destination.mkdir(parents=True, exist_ok=False)
        if source_path.is_dir():
            _copy_tree_safe(source_path, destination)
            return
        if source_path.is_file() and source_path.suffix.lower() == ".zip":
            _extract_zip_safe(source_path, destination)
            return
        raise SkillSecurityError("candidate must resolve to a directory or zip archive")


def _copy_tree_safe(source: Path, destination: Path) -> None:
    source = source.resolve()
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_symlink():
            raise SkillSecurityError(f"symlink is not allowed: {relative}")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def _extract_zip_safe(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if len(infos) > SkillScanner.MAX_FILES:
            raise SkillSecurityError("archive contains too many files")
        total = 0
        seen: set[str] = set()
        for info in infos:
            name = PurePosixPath(info.filename)
            normalized = name.as_posix()
            if name.is_absolute() or ".." in name.parts or "\x00" in info.filename:
                raise SkillSecurityError(f"unsafe archive path: {info.filename}")
            if normalized in seen:
                raise SkillSecurityError(f"duplicate archive path: {info.filename}")
            seen.add(normalized)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise SkillSecurityError(f"symlink is not allowed: {info.filename}")
            if info.is_dir():
                continue
            total += info.file_size
            if info.file_size > SkillScanner.MAX_FILE_BYTES or total > SkillScanner.MAX_TOTAL_BYTES:
                raise SkillSecurityError("archive is too large")
            target = destination.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_code(value: str) -> str:
    code = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return code[:80] or "external-skill"


def _read_license(root: Path) -> str:
    for name in ("LICENSE", "LICENSE.md", "LICENCE", "LICENCE.md"):
        path = root / name
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")[:200]
    return "unknown"


def prompt_templates() -> list[PromptTemplate]:
    return [
        PromptTemplate(
            "brand-customer-support",
            "品牌客服",
            "售前、订单和售后客服",
            """角色：你是 {{brand_name}} 的品牌客服。
目标：准确回答售前、订单、物流和售后问题，优先帮助用户完成下一步。
流程：1）识别问题类型；2）检索当前实例已启用的品牌知识库；3）给出有依据的答复；4）需要人工处理时说明转人工条件。
输入：用户问题={{user_question}}，订单号={{order_id_optional}}。
输出：先给结论，再给操作步骤；引用依据时写出文档标题；未知信息统一写“当前知识库无法确认”。
规则：不得承诺未核实的退款、赔付或发货时间；不得索取密码、完整身份证号或支付密钥；只有服务端已授权的工具才能调用。
预期输出：问题分类、明确答复、下一步操作、依据/未知说明。
适用工具/Skill：search_kb；品牌客服 Skill（仅在当前配置已启用时加载）。""",
            ("brand_name", "user_question", "order_id_optional"),
            ("search_kb",),
            ("brand-customer-support",),
        ),
        PromptTemplate(
            "short-video-content",
            "短视频内容创作",
            "生成选题、分镜和口播稿",
            """角色：你是短视频编导，服务于 {{brand_name}}。
目标：根据产品卖点、目标受众和平台约束，生成可执行且合规的短视频方案。
输入：产品={{product}}，卖点={{selling_points}}，受众={{audience}}，平台={{platform}}，时长={{duration_seconds}}。
流程：先提炼一个核心卖点，再给出 3 个选题；用户选定后输出分镜、口播稿、字幕和拍摄清单。
输出格式：## 选题；## 核心卖点；## 分镜表；## 口播稿；## 字幕；## 风险提示。
规则：不得虚构功效、销量、用户评价或资质；不确定的数据标记为“待核实”；保持口语化、具体、可拍摄。
预期输出：一份带时长分配的 Markdown 脚本和待核实项清单。
适用工具/Skill：短视频内容创作 Skill；必要时使用当前配置允许的知识检索工具。""",
            ("brand_name", "product", "selling_points", "audience", "platform", "duration_seconds"),
            (),
            ("short-video-content",),
        ),
        PromptTemplate(
            "lead-operations",
            "线索运营",
            "线索去重、分层和跟进",
            """角色：你是线索运营助理，负责整理、分层和跟进建议，不代替人工做最终触达决定。
目标：对输入线索去重、补全字段、评估优先级并生成下一步建议。
输入：线索={{lead_records}}，活动={{campaign}}，跟进规则={{follow_up_policy}}。
流程：校验字段 -> 按规则去重 -> 依据可解释条件分为 high/medium/low -> 输出建议 -> 涉及真实发送时先展示内容并等待用户确认。
输出格式：线索摘要、去重结果、分层理由、建议动作、待人工确认事项。
规则：不得编造联系人信息；不得把模型生成的“已发送”当成真实结果；真实发送只能调用服务端已绑定的高风险工具，并经过独立 Tool approval。
预期输出：可审计的分层表和不带副作用的跟进草案。
适用工具/Skill：线索运营 Skill；discover_douyin_leads 仅在实例绑定工作流且通过工具审批时可用。""",
            ("lead_records", "campaign", "follow_up_policy"),
            (),
            ("lead-operations",),
        ),
        PromptTemplate(
            "enterprise-knowledge-qna",
            "企业知识库问答",
            "基于企业文档回答问题",
            """角色：你是企业内部知识库问答助手。
目标：只基于当前用户、当前智能体和当前配置版本启用的文档回答问题。
输入：问题={{question}}，部门={{department_optional}}。
流程：检索相关文档 -> 判断证据是否足够 -> 用简洁语言回答 -> 列出文档标题/章节定位；证据不足时明确拒答或建议联系负责人。
输出格式：结论、依据、适用范围、仍需确认的问题。
规则：不能跨智能体读取知识文档；不能把常识或模型猜测伪装成公司制度；不能泄露文档中与问题无关的个人数据。
预期输出：带来源定位的答案；无命中时输出“当前知识库没有足够依据”。
适用工具/Skill：search_kb；企业知识库问答 Skill。""",
            ("question", "department_optional"),
            ("search_kb",),
            ("enterprise-knowledge-qna",),
        ),
    ]


def serialize_search_candidate(candidate: SearchCandidate) -> dict[str, Any]:
    """Serialize public candidate metadata without provider credentials."""
    data = dict(candidate.__dict__)
    data["title"] = candidate.name
    data["repository"] = candidate.repository or str(candidate.metadata.get("repository") or "")
    return data


def serialize_skill(record: SkillRecord) -> dict[str, Any]:
    data = dict(record.__dict__)
    for key in ("skill_id", "owner_user_id"):
        if data[key] is not None:
            data[key] = str(data[key])
    for key in ("created_at", "updated_at"):
        data[key] = data[key].isoformat()
    return data


def serialize_import(record: SkillImportRecord) -> dict[str, Any]:
    data = dict(record.__dict__)
    for key in ("import_id", "user_id", "target_agent_instance_id", "imported_skill_id", "confirmed_by"):
        if data[key] is not None:
            data[key] = str(data[key])
    for key in ("requested_at", "completed_at"):
        if data[key] is not None:
            data[key] = data[key].isoformat()
    return data
