from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_config
from langgraph.errors import GraphInterrupt
from langgraph.types import Command, interrupt

from app.knowledge import format_kb_hits, kb_namespace, profile_namespace
from app.knowledge import search_kb as kb_search
from app.job_control import run_cancel_job, run_list_jobs
from app.leads import json_tool_result, run_discover_leads
from app.media_paths import media_url_for
from app.repository import NotFoundError
from app.skill_runner import SkillRunnerError, run_python_script
from app.skills import (
    SkillError, SkillSecurityError, serialize_search_candidate, serialize_skill,
)
from mcp_servers.personal import current_datetime_payload, weather_payload

MEDIA_TOOL_NAMES = {"generate_image", "generate_video"}
KB_TOOL_NAMES = {"search_kb"}
PROFILE_NAMESPACE = ("assistant", "profile")


def _runtime_configurable() -> dict[str, Any]:
    try:
        config = get_config()
    except Exception:
        return {}
    return dict((config or {}).get("configurable") or {})


def _graph_is_resuming() -> bool:
    """Return whether the current ToolNode execution is replaying a resume.

    LangGraph re-executes a node from its beginning after ``Command(resume=...)``.
    The flag lets approval gates preserve their interrupt order without exposing a
    new approval prompt during an ordinary, non-resumed invocation.
    """
    return bool(_runtime_configurable().get("__pregel_resuming"))


def _owner_ids() -> tuple[str | None, str | None, str | None]:
    configurable = _runtime_configurable()
    user_id = configurable.get("user_id")
    agent_instance_id = configurable.get("agent_instance_id")
    thread_id = configurable.get("thread_id")
    return (
        str(user_id) if user_id else None,
        str(agent_instance_id) if agent_instance_id else None,
        str(thread_id) if thread_id else None,
    )


def _decision(
    raw: Any, default_prompt: str, default_params: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(raw, dict):
        raw = {"action": str(raw)}
    action = str(raw.get("action") or "approve").lower()
    prompt = raw.get("prompt") or default_prompt
    extra = raw.get("params") or {}
    if not isinstance(extra, dict):
        extra = {}
    return action, prompt, {**default_params, **extra}


def _skip_update(tool_name: str, tool_call_id: str) -> dict[str, Any]:
    return {
        "messages": [
            ToolMessage(
                content="User skipped media generation.",
                tool_call_id=tool_call_id,
                name=tool_name,
            )
        ]
    }


def _record_media_asset(
    *,
    business_repo,
    user_id: str | None,
    agent_instance_id: str | None,
    thread_id: str | None,
    kind: str,
    path,
    media_root,
) -> None:
    if business_repo is None or not user_id or not agent_instance_id:
        return
    try:
        relative = path.resolve().relative_to(media_root.resolve()).as_posix()
        business_repo.add_media_asset(
            UUID(str(user_id)),
            UUID(str(agent_instance_id)),
            kind=kind,
            storage_uri=relative,
            thread_id=thread_id,
        )
    except (NotFoundError, ValueError):
        return


def _media_update(
    *,
    tool_name: str,
    tool_call_id: str,
    kind: str,
    path,
    media_root,
    path_key: str,
) -> dict[str, Any]:
    url = media_url_for(path, media_root)
    payload = {
        "ok": True,
        "type": kind,
        "path": str(path),
        "url": url,
    }
    return {
        path_key: str(path),
        "messages": [
            ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id=tool_call_id,
                name=tool_name,
            )
        ],
    }


def _with_tool_audit(item, repository):
    """Attach scope-aware audit hooks without changing a StructuredTool schema."""
    original_func = getattr(item, "func", None)
    original_coroutine = getattr(item, "coroutine", None)
    if original_func is None and original_coroutine is None:
        return item
    tool_name = str(getattr(item, "name", "unknown"))
    risk_level = "high" if tool_name in {
        "discover_leads", "send_email", "generate_image", "generate_video",
    } else "low"

    def start(kwargs, config=None):
        values = dict((config or {}).get("configurable") or {}) if config else _runtime_configurable()
        try:
            scope = (
                UUID(str(values["user_id"])),
                UUID(str(values["agent_instance_id"])),
                UUID(str(values["config_version_id"])),
                str(values["thread_id"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
        approval_statuses = values.get("tool_approval_statuses") or {}
        approval_status = str(approval_statuses.get(tool_name, "not_required"))
        return repository.start(
            user_id=scope[0],
            agent_instance_id=scope[1],
            config_version_id=scope[2],
            thread_id=scope[3],
            tool_code=tool_name,
            risk_level=risk_level,
            approval_status=approval_status,
            inputs=kwargs,
        )

    def complete(record, *, status, output=None, error_code=None):
        if record is None:
            return
        external_request_id = None
        if isinstance(output, dict):
            external_request_id = output.get("external_request_id") or output.get("request_id")
        repository.complete(
            record.execution_id,
            status=status,
            output=output,
            error_code=error_code,
            external_request_id=str(external_request_id) if external_request_id else None,
        )

    if original_func is not None:
        def audited_func(*args, config: RunnableConfig, __original=original_func, **kwargs):
            record = start(kwargs, config)
            try:
                result = __original(*args, **kwargs)
            except GraphInterrupt:
                complete(record, status="interrupted", error_code="GraphInterrupt")
                raise
            except Exception as exc:
                complete(record, status="failed", error_code=type(exc).__name__)
                raise
            complete(record, status="succeeded", output=result)
            return result
        audited_func.__name__ = getattr(original_func, "__name__", tool_name)
        audited_func.__doc__ = getattr(original_func, "__doc__", None)
        item.func = audited_func

    if original_coroutine is not None:
        async def audited_coroutine(*args, config: RunnableConfig, __original=original_coroutine, **kwargs):
            record = start(kwargs, config)
            try:
                result = await __original(*args, **kwargs)
            except GraphInterrupt:
                complete(record, status="interrupted", error_code="GraphInterrupt")
                raise
            except Exception as exc:
                complete(record, status="failed", error_code=type(exc).__name__)
                raise
            complete(record, status="succeeded", output=result)
            return result
        audited_coroutine.__name__ = getattr(original_coroutine, "__name__", tool_name)
        audited_coroutine.__doc__ = getattr(original_coroutine, "__doc__", None)
        item.coroutine = audited_coroutine
    return item


def _now_from_clock(clock: Any):
    if clock is None:
        return None
    if callable(clock):
        return clock()
    return clock


def _extend_unique_tools(tools: list, extra_tools) -> None:
    existing = {getattr(item, "name", None) for item in tools}
    for item in extra_tools or []:
        name = getattr(item, "name", None)
        if name in existing:
            continue
        tools.append(item)
        if name is not None:
            existing.add(name)


def build_tools(
    *,
    store,
    image_client,
    video_client,
    settings,
    media_root,
    memory_store=None,
    email_client=None,
    extra_tools=None,
    business_repo=None,
    dify_client=None,
    skill_service=None,
    approval_manager=None,
    tool_audit_repository=None,
    clock=None,
    weather_client=None,
    weather_provider=None,
):
    @tool
    def search_kb(query: str, k: int = 4) -> str:
        """Search the current agent-instance knowledge base. Only call this for a supplementary lookup."""
        user_id, agent_instance_id, _thread_id = _owner_ids()
        if not user_id or not agent_instance_id:
            return format_kb_hits([])
        allowed_sources = _runtime_configurable().get("knowledge_sources")
        target = memory_store if memory_store is not None else store
        hits = kb_search(
            target,
            query=query,
            k=int(k or 4),
            namespace=kb_namespace(user_id, agent_instance_id),
            allowed_sources=allowed_sources,
        )
        return format_kb_hits(hits)

    @tool
    def generate_image(
        prompt: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Generate a 3:4 Xiaohongshu image. Pauses for human approval before calling the image API."""
        default_params = settings.default_image_params()
        action, final_prompt, params = _decision(
            interrupt(
                {
                    "type": "review_media",
                    "tool": "generate_image",
                    "prompt": prompt,
                    "params": default_params,
                    "options": ["approve", "skip", "update", "cancel", "reject"],
                }
            ),
            prompt,
            default_params,
        )
        if action in {"skip", "reject", "cancel"}:
            return Command(update=_skip_update("generate_image", tool_call_id))
        user_id, agent_instance_id, thread_id = _owner_ids()
        path = image_client.generate(
            final_prompt,
            params,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
        )
        _record_media_asset(
            business_repo=business_repo,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
            thread_id=thread_id,
            kind="image",
            path=path,
            media_root=media_root,
        )
        return Command(
            update=_media_update(
                tool_name="generate_image",
                tool_call_id=tool_call_id,
                kind="image",
                path=path,
                media_root=media_root,
                path_key="last_image_path",
            )
        )

    @tool
    def generate_video(
        prompt: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Generate a 9:16 Xiaohongshu video. Pauses for human approval before calling the video API."""
        default_params = settings.default_video_params()
        action, final_prompt, params = _decision(
            interrupt(
                {
                    "type": "review_media",
                    "tool": "generate_video",
                    "prompt": prompt,
                    "params": default_params,
                    "options": ["approve", "skip", "update", "cancel", "reject"],
                }
            ),
            prompt,
            default_params,
        )
        if action in {"skip", "reject", "cancel"}:
            return Command(update=_skip_update("generate_video", tool_call_id))
        user_id, agent_instance_id, thread_id = _owner_ids()
        path = video_client.generate(
            final_prompt,
            params,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
        )
        _record_media_asset(
            business_repo=business_repo,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
            thread_id=thread_id,
            kind="video",
            path=path,
            media_root=media_root,
        )
        return Command(
            update=_media_update(
                tool_name="generate_video",
                tool_call_id=tool_call_id,
                kind="video",
                path=path,
                media_root=media_root,
                path_key="last_video_path",
            )
        )

    timezone = getattr(settings, "assistant_timezone", None) or "Asia/Shanghai"
    default_city = getattr(settings, "assistant_city", None) or "广州"

    @tool
    def get_current_datetime() -> dict[str, Any]:
        """Return today's weekday and the current local datetime."""
        return current_datetime_payload(now=_now_from_clock(clock), timezone=timezone)

    @tool
    def get_weather(city: str = default_city) -> dict[str, Any]:
        """Return the current weather and temperature for a city. Defaults to Guangzhou."""
        target = (city or default_city).strip() or default_city
        if weather_provider is not None:
            payload = weather_provider(target)
            return payload if isinstance(payload, dict) else {"text": str(payload)}
        return weather_payload(target, timezone=timezone, client=weather_client)

    tools = [get_current_datetime, get_weather, search_kb, generate_image, generate_video]

    def _skill_scope() -> tuple[Any, Any, Any, Any] | None:
        configurable = _runtime_configurable()
        user_id = configurable.get("user_id")
        agent_instance_id = configurable.get("agent_instance_id")
        config_version_id = configurable.get("config_version_id")
        thread_id = configurable.get("thread_id")
        if not all((user_id, agent_instance_id, config_version_id, thread_id)):
            return None
        try:
            return UUID(str(user_id)), UUID(str(agent_instance_id)), UUID(str(config_version_id)), str(thread_id)
        except (TypeError, ValueError):
            return None

    def _approval_required(scope, *, kind: str, resource_code: str, consume: bool = False) -> bool:
        if approval_manager is None:
            return True
        user_id, agent_instance_id, config_version_id, thread_id = scope
        return approval_manager.ensure(
            user_id=user_id, agent_instance_id=agent_instance_id,
            config_version_id=config_version_id, thread_id=thread_id,
            approval_kind=kind, resource_code=resource_code, consume=consume,
        )

    def _approval_gate(scope, *, kind: str, resource_code: str, payload: dict[str, Any]) -> bool:
        """Require an independent approval and persist the resumed decision.

        The interrupt is deliberately inside the tool call so LangGraph resumes
        the exact ToolNode execution. No Skill approval is translated into a
        Script or Tool approval.
        """
        if approval_manager is None:
            return True
        already_approved = _approval_required(scope, kind=kind, resource_code=resource_code)
        if already_approved:
            # A resumed LangGraph node is replayed from its start.  Every
            # previously resolved interrupt must still occupy its original slot;
            # otherwise the next resume value can accidentally approve a later
            # Tool/Script gate.  Only replay an already-approved gate while the
            # graph is actually resuming, never during a fresh invocation.
            if _graph_is_resuming():
                try:
                    interrupt({**payload, "replay": True})
                except KeyError as exc:
                    if str(exc).strip("'") == "__pregel_scratchpad":
                        return False
                    raise
            return True
        user_id, agent_instance_id, config_version_id, thread_id = scope
        try:
            decision = interrupt(payload)
        except KeyError as exc:
            # Direct unit/tool invocation has no LangGraph scratchpad; fail
            # closed instead of leaking an internal KeyError. Graph execution
            # still raises the real interrupt and is resumable.
            if str(exc).strip("'") == "__pregel_scratchpad":
                return False
            raise
        if not isinstance(decision, dict):
            decision = {"action": str(decision)}
        action = str(decision.get("action") or "deny").lower()
        # Media HITL uses its own action vocabulary and is handled directly by
        # the media tools. Skill/Script/Tool approval interrupts must never
        # accept a media action or an arbitrary string.
        if action in {"deny", "reject", "cancel"}:
            return False
        if action not in {"approve_once", "approve_session"}:
            raise SkillSecurityError("unsupported approval action")
        approval_scope = "session" if action == "approve_session" else "once"
        record = approval_manager.repository.request(
            user_id=user_id, agent_instance_id=agent_instance_id,
            config_version_id=config_version_id, thread_id=thread_id,
            approval_kind=kind, resource_code=resource_code,
            approval_scope=approval_scope,
        )
        if record.status == "pending":
            approval_manager.repository.decide(record.approval_id, user_id=user_id, approved=True)
        return _approval_required(scope, kind=kind, resource_code=resource_code)

    def _skill_review_payload(skill, *, script_path: str | None = None) -> dict[str, Any]:
        if script_path is None:
            return {
                "type": "review_skill",
                "skill_id": str(skill.skill_id),
                "skill_name": skill.name,
                "reason": "该 Skill 未在当前线程获得独立审批，加载前需要用户确认。",
                "risk_level": skill.risk_level,
                "approval_mode": "once",
                "options": ["approve_once", "approve_session", "deny"],
            }
        return {
            "type": "review_skill_script",
            "skill_id": str(skill.skill_id),
            "script_path": script_path,
            "reason": "该 Skill 脚本将在受控 Python runner 中执行，需要独立脚本审批。",
            "options": ["approve_once", "approve_session", "deny"],
        }

    if skill_service is not None:

        @tool
        def web_search(query: str, limit: int = 10) -> str:
            """Search external Skill candidates only; never downloads or imports a Skill."""
            scope = _skill_scope()
            if scope is None:
                return json.dumps({"ok": False, "error": "missing Skill scope"}, ensure_ascii=False)
            if not _approval_required(scope, kind="tool", resource_code="web_search"):
                return json.dumps({"ok": False, "error": "tool approval is required"}, ensure_ascii=False)
            try:
                items = skill_service.search(query, limit=limit)
                return json.dumps(
                    {"ok": True, "items": [serialize_search_candidate(item) for item in items]},
                    ensure_ascii=False,
                )
            except SkillError as exc:
                return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

        @tool
        def list_available_skills() -> str:
            """List only Skills bound to the current agent config version."""
            scope = _skill_scope()
            if scope is None:
                return json.dumps({"ok": False, "error": "missing Skill scope"}, ensure_ascii=False)
            user_id, agent_instance_id, config_version_id, _thread_id = scope
            try:
                config = skill_service.repository.get_config(config_version_id)
                if config["user_id"] != user_id or config["agent_instance_id"] != agent_instance_id:
                    raise SkillSecurityError("skill config does not belong to current scope")
                items = [
                    skill for skill in skill_service.repository.list_skills(user_id=user_id)
                    if any(binding.skill_id == skill.skill_id for binding in skill_service.repository.list_bindings(config_version_id))
                ]
                return json.dumps(
                    {"ok": True, "items": [
                        {key: value for key, value in serialize_skill(item).items()
                         if key in {"skill_id", "code", "name", "description", "trigger_description", "risk_level", "approval_mode"}}
                        for item in items
                    ]}, ensure_ascii=False,
                )
            except SkillError as exc:
                return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

        @tool
        def load_skill(skill_id: str) -> str:
            """Load an approved, imported/bound Skill from the current config scope."""
            scope = _skill_scope()
            if scope is None:
                return json.dumps({"ok": False, "error": "missing Skill scope"}, ensure_ascii=False)
            try:
                parsed_skill_id = UUID(str(skill_id))
                user_id, agent_instance_id, config_version_id, thread_id = scope
                skill_preview = skill_service.repository.get_skill(parsed_skill_id)
                if skill_preview.owner_scope != "platform" or skill_preview.approval_mode != "auto":
                    if not _approval_gate(
                        scope, kind="skill", resource_code=skill_preview.code,
                        payload=_skill_review_payload(skill_preview),
                    ):
                        return json.dumps({"ok": False, "error": "skill approval denied"}, ensure_ascii=False)
                skill = skill_service.load_skill_for_scope(
                    user_id, agent_instance_id, config_version_id, parsed_skill_id,
                    approvals=approval_manager, thread_id=thread_id,
                )
                result = json.dumps({"ok": True, "skill": serialize_skill(skill)}, ensure_ascii=False)
                _approval_required(scope, kind="skill", resource_code=skill.code, consume=True)
                return result
            except (ValueError, SkillError) as exc:
                return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

        @tool
        def run_skill_script(skill_id: str, script_path: str, input_text: str = "") -> str:
            """Run one server-approved Python script from an approved Skill in isolation."""
            scope = _skill_scope()
            if scope is None:
                return json.dumps({"ok": False, "error": "missing Skill scope"}, ensure_ascii=False)
            try:
                parsed_skill_id = UUID(str(skill_id))
                user_id, agent_instance_id, config_version_id, thread_id = scope
                skill_preview = skill_service.repository.get_skill(parsed_skill_id)
                if skill_preview.owner_scope != "platform" or skill_preview.approval_mode != "auto":
                    if not _approval_gate(
                        scope, kind="skill", resource_code=skill_preview.code,
                        payload=_skill_review_payload(skill_preview),
                    ):
                        return json.dumps({"ok": False, "error": "skill approval denied"}, ensure_ascii=False)
                skill = skill_service.load_skill_for_scope(
                    user_id, agent_instance_id, config_version_id, parsed_skill_id,
                    approvals=approval_manager, thread_id=thread_id,
                )
                script_name = str(script_path or "").replace("\\", "/").lstrip("/")
                if not script_name or script_name.startswith("../") or "/../" in f"/{script_name}":
                    raise SkillSecurityError("script path is not allowed")
                artifact = skill_service.get_artifact_for_skill(skill.skill_id)
                allowed_scripts = {str(item).replace("\\", "/").lstrip("/") for item in artifact.manifest.get("scripts", [])}
                if script_name not in allowed_scripts:
                    raise SkillSecurityError("script is not in the server-approved manifest")
                if not _approval_gate(
                    scope, kind="tool", resource_code="run_skill_script",
                    payload={
                        "type": "review_tool",
                        "tool": "run_skill_script",
                        "reason": "执行外部 Skill 脚本需要独立工具审批。",
                        "risk_level": skill.risk_level,
                        "approval_mode": "once",
                        "options": ["approve_once", "approve_session", "deny"],
                    },
                ):
                    return json.dumps({"ok": False, "error": "tool approval denied"}, ensure_ascii=False)
                script_code = f"{skill.code}:{script_name}"
                if not _approval_gate(
                    scope, kind="script", resource_code=script_code,
                    payload=_skill_review_payload(skill, script_path=script_name),
                ):
                    return json.dumps({"ok": False, "error": "script approval denied"}, ensure_ascii=False)
                source_root = Path(artifact.storage_key).resolve()
                source = (source_root / script_name).resolve()
                if source_root not in source.parents or not source.is_file() or source.is_symlink():
                    raise SkillSecurityError("script must stay inside the imported Skill")
                with tempfile.TemporaryDirectory(prefix="agentdemo-skill-run-") as workdir:
                    workspace = Path(workdir)
                    target = workspace / Path(script_name).name
                    shutil.copyfile(source, target)
                    result = run_python_script(target, workspace=workspace, input_text=input_text)
                _approval_required(scope, kind="skill", resource_code=skill.code, consume=True)
                _approval_required(scope, kind="tool", resource_code="run_skill_script", consume=True)
                _approval_required(scope, kind="script", resource_code=script_code, consume=True)
                return json.dumps({"ok": True, "skill": skill.code, "script": script_name, "result": result}, ensure_ascii=False)
            except (ValueError, SkillError, SkillRunnerError, OSError) as exc:
                return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

        tools.extend([web_search, list_available_skills, load_skill, run_skill_script])

    if memory_store is not None:

        @tool
        def remember_fact(fact: str) -> str:
            """Remember a long-term fact about the user across conversations."""
            text = (fact or "").strip()
            if not text:
                return "empty fact"
            user_id, agent_instance_id, _thread_id = _owner_ids()
            if not user_id or not agent_instance_id:
                return json.dumps({"ok": False, "error": "missing instance context"}, ensure_ascii=False)
            key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            memory_store.put(profile_namespace(user_id, agent_instance_id), key, {"text": text})
            return json.dumps({"ok": True, "key": key}, ensure_ascii=False)

        @tool
        def recall_facts(query: str = "") -> str:
            """Recall remembered facts about the user."""
            user_id, agent_instance_id, _thread_id = _owner_ids()
            if not user_id or not agent_instance_id:
                return "NO_FACTS"
            hits = memory_store.search(
                profile_namespace(user_id, agent_instance_id),
                query=query or None,
                limit=20,
            )
            facts = []
            for hit in hits:
                value = getattr(hit, "value", None) or {}
                text = value.get("text")
                if text:
                    facts.append(text)
            if not facts:
                return "NO_FACTS"
            return "\n".join(facts)

        tools.extend([remember_fact, recall_facts])

    if email_client is not None:

        @tool
        def send_email(subject: str, body: str) -> str:
            """Send an email to the configured personal inbox. Pauses for tool approval before sending."""
            scope = _skill_scope()
            if scope is None:
                return json.dumps({"ok": False, "error": "missing instance context"}, ensure_ascii=False)
            if not _approval_gate(
                scope,
                kind="tool",
                resource_code="send_email",
                payload={
                    "type": "review_tool",
                    "tool": "send_email",
                    "reason": "发送邮件需要独立工具审批。",
                    "risk_level": "high",
                    "approval_mode": "once",
                    "subject": subject,
                    "options": ["approve_once", "approve_session", "deny"],
                },
            ):
                return json.dumps({"ok": False, "error": "tool approval denied"}, ensure_ascii=False)
            result = email_client.send(subject=subject, body=body)
            _approval_required(scope, kind="tool", resource_code="send_email", consume=True)
            return json.dumps(
                {
                    "ok": True,
                    "subject": result.get("subject"),
                    "to": result.get("to"),
                },
                ensure_ascii=False,
            )

        tools.append(send_email)


    if business_repo is not None and dify_client is not None:

        @tool
        def discover_leads(
            platform: str,
            account: str,
            keyword: str = "",
            video_id: str = "",
            url: str = "",
            limit: int = 0,
            channels: str = "",
            max_comments: str = "",
            reply_limit: str = "",
            message_limit: str = "",
            select: str = "",
            list_status: str = "",
        ) -> str:
            """Find leads on Douyin or Xiaohongshu and send replies. This really sends.

            platform must be douyin or xiaohongshu. account is required. Pass at least one of keyword, video_id, or url.
            Omit channels when possible; the worker defaults to comment,message.
            Add like or collect only when the user explicitly asks to like or favorite.
            If max_comments is omitted, the worker uses 10.
            If reply_limit or message_limit is omitted, the worker uses 1.
            """
            result = run_discover_leads(
                settings=settings,
                business_repo=business_repo,
                dify_client=dify_client,
                configurable=_runtime_configurable(),
                platform=platform,
                account=account,
                keyword=keyword,
                video_id=video_id,
                url=url,
                limit=limit or None,
                channels=channels,
                max_comments=max_comments,
                reply_limit=reply_limit,
                message_limit=message_limit,
                select=select,
                list_status=list_status,
            )
            return json_tool_result(result)

        tools.append(discover_leads)

    if business_repo is not None:

        @tool
        def list_jobs() -> str:
            """List job definitions and runs for the current agent instance."""
            return json_tool_result(run_list_jobs(business_repo, _runtime_configurable()))

        @tool
        def cancel_job(job_id: str = "", run_id: str = "") -> str:
            """Disable a job definition or cancel one job run. Only affects this user and instance."""
            return json_tool_result(
                run_cancel_job(
                    business_repo,
                    _runtime_configurable(),
                    job_id=job_id,
                    run_id=run_id,
                )
            )

        tools.extend([list_jobs, cancel_job])

    _extend_unique_tools(tools, extra_tools)

    if tool_audit_repository is not None:
        tools = [
            _with_tool_audit(item, tool_audit_repository)
            for item in tools
        ]
    return tools
