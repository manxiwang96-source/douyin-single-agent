from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from app.dify_client import normalize_job_status, parse_json_value
from app.repository import (
    DEFAULT_WORKFLOW_CODE,
    ENGAGE_COMMENT_STATUSES,
    ENGAGE_DM_STATUSES,
    ENGAGE_VIDEO_STATUSES,
    WORKFLOW_RUN_STATUSES,
    utcnow,
)

LEAD_WORKFLOW_CODE = DEFAULT_WORKFLOW_CODE
DEDUP_WINDOW = timedelta(minutes=10)
BLOCKED_ACCOUNT_STATUSES = frozenset({"paused", "needs_login"})
DEFAULT_LEAD_PLATFORM = "douyin"
DEFAULT_LEAD_LIMIT = 20
DEFAULT_LEAD_CHANNELS = "comment,message"
DEFAULT_DOUYIN_HTTP_BASE_URL = "http://192.168.1.33:8765"
CHANNEL_COMMENT = "comment"
CHANNEL_MESSAGE = "message"
ALLOWED_LEAD_CHANNEL_VALUES = frozenset(
    {CHANNEL_COMMENT, CHANNEL_MESSAGE, DEFAULT_LEAD_CHANNELS}
)
_CHANNEL_TOKEN_ALIASES = {
    "comment": CHANNEL_COMMENT,
    "comments": CHANNEL_COMMENT,
    "评论": CHANNEL_COMMENT,
    "message": CHANNEL_MESSAGE,
    "messages": CHANNEL_MESSAGE,
    "dm": CHANNEL_MESSAGE,
    "dms": CHANNEL_MESSAGE,
    "私信": CHANNEL_MESSAGE,
}


def normalize_lead_channels(channels: str = "") -> str:
    raw = str(channels or "").strip()
    if not raw:
        return DEFAULT_LEAD_CHANNELS
    compact = raw.replace(" ", "")
    if compact in ALLOWED_LEAD_CHANNEL_VALUES:
        return compact
    if compact == f"{CHANNEL_MESSAGE},{CHANNEL_COMMENT}":
        return DEFAULT_LEAD_CHANNELS
    found: list[str] = []
    for piece in re.split(r"[,，、/;；]+", raw):
        token = piece.strip()
        mapped = _CHANNEL_TOKEN_ALIASES.get(token.lower()) or _CHANNEL_TOKEN_ALIASES.get(token)
        if mapped and mapped not in found:
            found.append(mapped)
    if CHANNEL_COMMENT in found and CHANNEL_MESSAGE in found:
        return DEFAULT_LEAD_CHANNELS
    if len(found) == 1:
        return found[0]
    return DEFAULT_LEAD_CHANNELS



def json_tool_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def build_dify_inputs(
    settings,
    *,
    account: str,
    keyword: str = "",
    video_id: str = "",
    limit: int | str | None = None,
    channels: str = "",
    list_status: str = "",
) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "account": account,
        "platform": DEFAULT_LEAD_PLATFORM,
        "no_send": False,
        "auto_login": True,
        "assess": True,
        "limit": DEFAULT_LEAD_LIMIT,
        "channels": DEFAULT_LEAD_CHANNELS,
    }
    if video_id:
        inputs["video_id"] = video_id
    elif keyword:
        inputs["keyword"] = keyword
    if limit is not None and str(limit) != "":
        inputs["limit"] = limit
    inputs["channels"] = normalize_lead_channels(channels)
    if list_status:
        inputs["list_status"] = list_status
    base_url = (getattr(settings, "douyin_http_base_url", "") or "").strip()
    api_token = (getattr(settings, "douyin_http_api_token", "") or "").strip()
    inputs["base_url"] = base_url or DEFAULT_DOUYIN_HTTP_BASE_URL
    if api_token:
        inputs["api_token"] = api_token
    return inputs


def validate_lead_args(*, account: str, keyword: str, video_id: str) -> str | None:
    if not (account or "").strip():
        return "account is required"
    if not (keyword or "").strip() and not (video_id or "").strip():
        return "keyword or video_id is required"
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def find_in_progress_run(repo, user_id: UUID, agent_instance_id: UUID, inputs: dict[str, Any]):
    since = utcnow() - DEDUP_WINDOW
    account = _norm(inputs.get("account"))
    keyword = _norm(inputs.get("keyword"))
    video_id = _norm(inputs.get("video_id"))
    for record in repo.list_workflow_runs(user_id, agent_instance_id, status="running", since=since):
        existing = record.inputs or {}
        if (
            _norm(existing.get("account")) == account
            and _norm(existing.get("keyword")) == keyword
            and _norm(existing.get("video_id")) == video_id
        ):
            return record
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    parsed = parse_json_value(value)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("data", "items", "list", "comments", "messages", "videos", "result"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        return [parsed]
    return []


def _delivery_items(value: Any) -> tuple[list[Any], str | None]:
    """Only explicit arrays/array wrappers are records; error objects stay errors."""
    if value is None or value == "":
        return [], "delivery response unavailable"
    parsed = parse_json_value(value)
    if isinstance(parsed, list):
        return parsed, None
    if not isinstance(parsed, dict):
        return [], "delivery response is not a list"
    if parsed.get("ok") is False or parsed.get("error") or parsed.get("message"):
        return [], _first_text(parsed, "error", "message") or "delivery request failed"
    for key in ("data", "items", "list", "comments", "messages", "result"):
        if isinstance(parsed.get(key), list):
            return parsed[key], None
    return [], "delivery response is not a list"


def _item_status(item: dict[str, Any], allowed: frozenset[str], default: str = "unverified") -> str:
    raw = str(item.get("status") or item.get("send_status") or "").strip().lower()
    if raw in allowed:
        return raw
    if raw in {"success", "succeeded", "completed", "delivered"}:
        return "sent"
    if "login" in raw:
        return "needs_login"
    if raw in {"fail", "failed", "error"}:
        return "failed"
    if raw in {"cancelled", "canceled"}:
        return "cancelled"
    return default


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _delivery_result(outputs: Any, *, job_status: str) -> tuple[dict[str, dict[str, int]], list[dict[str, Any]], list[str], bool]:
    payload = outputs if isinstance(outputs, dict) else {}
    delivery = {
        "comments": {"sent": 0, "failed": 0, "unverified": 0},
        "dms": {"sent": 0, "failed": 0, "unverified": 0},
    }
    message_details: list[dict[str, Any]] = []
    errors: list[str] = []
    for output_key, channel, allowed in (
        ("list_comment", "comments", ENGAGE_COMMENT_STATUSES),
        ("list_message", "dms", ENGAGE_DM_STATUSES),
    ):
        items, response_error = _delivery_items(payload.get(output_key))
        if response_error:
            delivery[channel]["failed"] += 1 if response_error != "delivery response unavailable" else 0
            delivery[channel]["unverified"] += 1 if response_error == "delivery response unavailable" else 0
            errors.append(f"{channel}: {response_error}")
            continue
        for item in items:
            if not isinstance(item, dict):
                delivery[channel]["unverified"] += 1
                errors.append(f"{channel}: delivery item is not an object")
                continue
            dify_status = _item_status(item, allowed)
            status = dify_status
            if job_status != "succeeded" and status == "sent":
                status = "unverified"
            if status == "sent":
                delivery[channel]["sent"] += 1
            elif status in {"failed", "needs_login", "cancelled"}:
                delivery[channel]["failed"] += 1
            else:
                delivery[channel]["unverified"] += 1
            if status in {"failed", "needs_login", "cancelled"} and item.get("error"):
                errors.append(str(item["error"]))
            if channel == "dms":
                detail = dict(item)
                if dify_status != status:
                    detail["dify_status"] = dify_status
                detail["status"] = status
                message_details.append(detail)
    delivery_ok = job_status == "succeeded" and not errors and all(
        counts["failed"] == 0 and counts["unverified"] == 0
        for counts in delivery.values()
    )
    return delivery, message_details, errors, delivery_ok


def apply_engage_writeback(
    repo,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    thread_id: str | None,
    workflow_run_id: str | None,
    outputs: Any,
    keyword: str | None = None,
) -> dict[str, int]:
    payload = outputs if isinstance(outputs, dict) else {}
    comments, _ = _delivery_items(payload.get("list_comment"))
    messages, _ = _delivery_items(payload.get("list_message"))
    videos = _as_list(payload.get("snapshot"))
    if not videos and isinstance(payload.get("snapshot"), dict):
        videos = _as_list(payload["snapshot"].get("videos"))
    written = {"videos": 0, "comments": 0, "dms": 0}
    for item in videos:
        if not isinstance(item, dict):
            continue
        platform_video_id = _first_text(item, "platform_video_id", "video_id", "aweme_id", "id") or "unknown"
        status = _item_status(item, ENGAGE_VIDEO_STATUSES, "discovered")
        repo.add_engage_video(
            user_id,
            agent_instance_id,
            platform_video_id=platform_video_id,
            keyword=item.get("keyword") or keyword,
            title=item.get("title"),
            url=item.get("url") or item.get("share_url"),
            status=status if status in ENGAGE_VIDEO_STATUSES else "discovered",
            thread_id=thread_id,
            workflow_run_id=workflow_run_id,
        )
        written["videos"] += 1
    for item in comments:
        if not isinstance(item, dict):
            continue
        status = _item_status(item, ENGAGE_COMMENT_STATUSES)
        repo.add_engage_comment(
            user_id,
            agent_instance_id,
            platform_comment_id=_first_text(item, "platform_comment_id", "comment_id", "cid", "id") or "unknown",
            video_id=_first_text(item, "video_id", "aweme_id", "platform_video_id") or "unknown",
            source_text=_first_text(item, "source_text", "text", "content", "comment"),
            candidate_reply=_first_text(item, "candidate_reply", "reply", "approved_reply"),
            status=status if status in ENGAGE_COMMENT_STATUSES else "proposed",
            thread_id=thread_id,
            workflow_run_id=workflow_run_id,
        )
        written["comments"] += 1
    for item in messages:
        if not isinstance(item, dict):
            continue
        status = _item_status(item, ENGAGE_DM_STATUSES)
        repo.add_engage_dm(
            user_id,
            agent_instance_id,
            platform_message_id=_first_text(item, "platform_message_id", "message_id", "id") or "unknown",
            video_id=_first_text(item, "video_id", "aweme_id", "platform_video_id") or "unknown",
            source_text=_first_text(item, "source_text", "text", "content", "message"),
            candidate_reply=_first_text(item, "candidate_reply", "reply", "approved_reply", "content"),
            status=status if status in ENGAGE_DM_STATUSES else "proposed",
            thread_id=thread_id,
            workflow_run_id=workflow_run_id,
        )
        written["dms"] += 1
    return written


def summarize_lead_result(
    *,
    status: str,
    outputs: Any,
    written: dict[str, int],
    error: str | None,
    delivery: dict[str, dict[str, int]] | None = None,
) -> str:
    parts = [f"status={status}"]
    if delivery is not None:
        parts.append(
            "delivery="
            + ",".join(
                f"{channel}:sent={counts['sent']} failed={counts['failed']} unverified={counts['unverified']}"
                for channel, counts in delivery.items()
            )
        )
    if error:
        parts.append(f"error={error}")
    elif isinstance(outputs, dict) and outputs:
        keys = ",".join(sorted(str(key) for key in outputs.keys()))
        parts.append(f"outputs={keys}")
    else:
        parts.append("no structured engage rows")
    return "; ".join(parts)

def run_discover_douyin_leads(
    *,
    settings,
    business_repo,
    dify_client,
    configurable: dict[str, Any],
    account: str,
    keyword: str = "",
    video_id: str = "",
    limit: int | str | None = None,
    channels: str = "",
    list_status: str = "",
) -> dict[str, Any]:
    user_id_raw = configurable.get("user_id")
    agent_instance_id_raw = configurable.get("agent_instance_id")
    thread_id = str(configurable.get("thread_id") or "") or None
    allowed = list(configurable.get("allowed_workflow_codes") or [])
    if LEAD_WORKFLOW_CODE not in allowed:
        return {"ok": False, "error": "workflow not bound", "status": "failed"}
    missing = validate_lead_args(account=account, keyword=keyword, video_id=video_id)
    if missing:
        return {"ok": False, "error": missing, "status": "failed"}
    try:
        user_id = UUID(str(user_id_raw))
        agent_instance_id = UUID(str(agent_instance_id_raw))
    except Exception:
        return {"ok": False, "error": "missing instance context", "status": "failed"}

    account_text = account.strip()
    record = business_repo.get_douyin_account(user_id, agent_instance_id, account_text)
    if record is not None and record.status in BLOCKED_ACCOUNT_STATUSES:
        return {
            "ok": False,
            "error": f"account {record.status}",
            "status": record.status,
            "account": account_text,
        }

    inputs = build_dify_inputs(
        settings,
        account=account_text,
        keyword=(keyword or "").strip(),
        video_id=(video_id or "").strip(),
        limit=limit,
        channels=(channels or "").strip(),
        list_status=(list_status or "").strip(),
    )
    existing = find_in_progress_run(business_repo, user_id, agent_instance_id, inputs)
    if existing is not None:
        return {
            "ok": True,
            "reused": True,
            "status": existing.status,
            "workflow_run_id": existing.workflow_run_id,
            "id": str(existing.id),
            "summary": "in-progress run reused; skipped second POST",
        }

    run = business_repo.create_workflow_run(
        user_id,
        agent_instance_id,
        workflow_code=LEAD_WORKFLOW_CODE,
        inputs=inputs,
        status="running",
        thread_id=thread_id,
        dify_app_id=getattr(settings, "dify_lead_app_id", None),
    )
    result = dify_client.run(LEAD_WORKFLOW_CODE, inputs, user=str(user_id))
    outputs = result.get("outputs") if isinstance(result.get("outputs"), dict) else {}
    dify_workflow_status = str(result.get("dify_workflow_status") or "unverified")
    workflow_ok = bool(result.get("workflow_ok"))
    job_status = normalize_job_status(result.get("job_status"))
    if job_status == "unverified" and isinstance(outputs, dict):
        response = parse_json_value(outputs.get("job_response"))
        response_dict = response if isinstance(response, dict) else {}
        response_data = response_dict.get("data") if isinstance(response_dict.get("data"), dict) else {}
        job_status = normalize_job_status(response_data.get("status") or response_dict.get("status") or outputs.get("job_status"))
    status = str(result.get("status") or (job_status if job_status != "unverified" else "failed"))
    if status not in WORKFLOW_RUN_STATUSES and status not in {"unverified"}:
        status = "failed"
    job_id = result.get("job_id") or outputs.get("job_id")
    workflow_run_id = result.get("workflow_run_id")
    task_error = result.get("error")
    if job_status == "unverified" and not task_error:
        task_error = "job status unavailable"
    if job_status == "failed" and not task_error:
        task_error = "job failed"
    delivery, message_details, delivery_errors, delivery_ok = _delivery_result(outputs, job_status=job_status)
    error = task_error or (delivery_errors[0] if delivery_errors else None)
    if job_status == "succeeded" and delivery_errors and not error:
        error = delivery_errors[0]
    if job_status == "succeeded" and delivery_ok:
        status = "succeeded"
    elif job_status == "succeeded" and any(
        counts["unverified"] > 0 and counts["failed"] == 0 for counts in delivery.values()
    ) and not any(counts["failed"] > 0 for counts in delivery.values()):
        status = "unverified"
    elif job_status == "cancelled":
        status = "cancelled"
    elif job_status == "timeout":
        status = "timeout"
    elif job_status == "failed":
        status = "failed"
    elif job_status == "unverified":
        status = "unverified"
    else:
        status = "failed"
    written = {"videos": 0, "comments": 0, "dms": 0}
    if job_status == "succeeded":
        try:
            written = apply_engage_writeback(
                business_repo,
                user_id=user_id,
                agent_instance_id=agent_instance_id,
                thread_id=thread_id,
                workflow_run_id=workflow_run_id or str(run.id),
                outputs=outputs,
                keyword=inputs.get("keyword"),
            )
        except Exception:
            written = {"videos": 0, "comments": 0, "dms": 0}
    persisted_status = "failed" if status == "unverified" else status
    updated = business_repo.update_workflow_run(
        run.id,
        status=persisted_status,
        outputs=outputs if isinstance(outputs, dict) else None,
        error=error,
        workflow_run_id=workflow_run_id,
    )
    ok = bool(workflow_ok and job_status == "succeeded" and delivery_ok)
    summary = summarize_lead_result(
        status=status,
        outputs=outputs,
        written=written,
        error=error,
        delivery=delivery,
    )
    return {
        "ok": ok,
        "workflow_ok": workflow_ok,
        "delivery_ok": delivery_ok,
        "status": status,
        "dify_workflow_status": dify_workflow_status,
        "job_status": job_status,
        "workflow_run_id": workflow_run_id,
        "job_id": job_id,
        "id": str(updated.id),
        "error": error,
        "delivery": delivery,
        "message_details": message_details,
        "summary": summary,
        "written": written,
    }
