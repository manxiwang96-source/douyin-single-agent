from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from app.dify_client import compact_workflow_node, extract_dify_error, normalize_job_status, parse_json_value, parse_optional_bool
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
ALLOWED_LEAD_PLATFORMS = frozenset({"douyin", "xiaohongshu"})
DEFAULT_LEAD_PLATFORM = "douyin"
DEFAULT_LEAD_LIMIT = 20
DEFAULT_LEAD_CHANNELS = "comment,message"
DEFAULT_DOUYIN_HTTP_BASE_URL = "http://192.168.1.33:8765"
CHANNEL_COMMENT = "comment"
CHANNEL_MESSAGE = "message"
CHANNEL_LIKE = "like"
CHANNEL_COLLECT = "collect"
CANONICAL_CHANNEL_ORDER = (
    CHANNEL_COMMENT,
    CHANNEL_MESSAGE,
    CHANNEL_LIKE,
    CHANNEL_COLLECT,
)
DEFAULT_MAX_COMMENTS = 10
MAX_COMMENTS_MIN = 1
MAX_COMMENTS_MAX = 50
DEFAULT_ROUND_LIMIT = 1
ROUND_LIMIT_MIN = 1
ROUND_LIMIT_MAX = 10
_CHANNEL_TOKEN_ALIASES = {
    "comment": CHANNEL_COMMENT,
    "comments": CHANNEL_COMMENT,
    "评论": CHANNEL_COMMENT,
    "message": CHANNEL_MESSAGE,
    "messages": CHANNEL_MESSAGE,
    "dm": CHANNEL_MESSAGE,
    "dms": CHANNEL_MESSAGE,
    "私信": CHANNEL_MESSAGE,
    "like": CHANNEL_LIKE,
    "likes": CHANNEL_LIKE,
    "点赞": CHANNEL_LIKE,
    "collect": CHANNEL_COLLECT,
    "favorite": CHANNEL_COLLECT,
    "favourite": CHANNEL_COLLECT,
    "收藏": CHANNEL_COLLECT,
}


def normalize_lead_channels(channels: str = "") -> str:
    raw = str(channels or "").strip()
    if not raw:
        return DEFAULT_LEAD_CHANNELS
    found: set[str] = set()
    for piece in re.split(r"[,，、/;；]+", raw):
        token = piece.strip()
        mapped = _CHANNEL_TOKEN_ALIASES.get(token.lower()) or _CHANNEL_TOKEN_ALIASES.get(token)
        if mapped:
            found.add(mapped)
    if not found:
        return DEFAULT_LEAD_CHANNELS
    return ",".join(channel for channel in CANONICAL_CHANNEL_ORDER if channel in found)


def normalize_max_comments(max_comments: str | int | None = "") -> str:
    raw = str(max_comments if max_comments is not None else "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return str(DEFAULT_MAX_COMMENTS)
    if value < MAX_COMMENTS_MIN:
        value = MAX_COMMENTS_MIN
    elif value > MAX_COMMENTS_MAX:
        value = MAX_COMMENTS_MAX
    return str(value)


def normalize_round_limit(limit: str | int | None = "") -> str:
    raw = str(limit if limit is not None else "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return str(DEFAULT_ROUND_LIMIT)
    if value < ROUND_LIMIT_MIN:
        value = ROUND_LIMIT_MIN
    elif value > ROUND_LIMIT_MAX:
        value = ROUND_LIMIT_MAX
    return str(value)


def json_tool_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def build_dify_inputs(
    settings,
    *,
    platform: str,
    account: str,
    keyword: str = "",
    video_id: str = "",
    url: str = "",
    limit: int | str | None = None,
    channels: str = "",
    max_comments: str = "",
    reply_limit: str = "",
    message_limit: str = "",
    select: str = "",
    list_status: str = "",
) -> dict[str, Any]:
    channels = normalize_lead_channels(channels)
    selected = set(channels.split(","))
    inputs: dict[str, Any] = {
        "account": account,
        "platform": platform,
        "no_send": False,
        "auto_login": True,
        "assess": True,
        "limit": DEFAULT_LEAD_LIMIT,
        "channels": channels,
        "channel_comment": CHANNEL_COMMENT in selected,
        "channel_message": CHANNEL_MESSAGE in selected,
        "channel_like": CHANNEL_LIKE in selected,
        "channel_collect": CHANNEL_COLLECT in selected,
        "max_comments": normalize_max_comments(max_comments),
        "reply_limit": normalize_round_limit(reply_limit),
        "message_limit": normalize_round_limit(message_limit),
    }
    if video_id:
        inputs["video_id"] = video_id
    elif keyword:
        inputs["keyword"] = keyword
    if url:
        inputs["url"] = url
    if limit is not None and str(limit) != "":
        inputs["limit"] = limit
    for key, value in (("select", select), ("list_status", list_status)):
        if value not in (None, ""):
            inputs[key] = value
    base_url = (getattr(settings, "douyin_http_base_url", "") or "").strip()
    api_token = (getattr(settings, "douyin_http_api_token", "") or "").strip()
    inputs["base_url"] = base_url or DEFAULT_DOUYIN_HTTP_BASE_URL
    if api_token:
        inputs["api_token"] = api_token
    return inputs


def validate_lead_args(*, platform: str, account: str, keyword: str, video_id: str, url: str) -> str | None:
    if platform not in ALLOWED_LEAD_PLATFORMS:
        return "platform must be douyin or xiaohongshu"
    if not (account or "").strip():
        return "account is required"
    if not any(((keyword or "").strip(), (video_id or "").strip(), (url or "").strip())):
        return "keyword, video_id, or url is required"
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def find_in_progress_run(repo, user_id: UUID, agent_instance_id: UUID, inputs: dict[str, Any]):
    since = utcnow() - DEDUP_WINDOW
    account = _norm(inputs.get("account"))
    keyword = _norm(inputs.get("keyword"))
    video_id = _norm(inputs.get("video_id"))
    url = _norm(inputs.get("url"))
    platform = _norm(inputs.get("platform"))
    for record in repo.list_workflow_runs(user_id, agent_instance_id, status="running", since=since):
        existing = record.inputs or {}
        if (
            _norm(existing.get("platform")) == platform
            and _norm(existing.get("account")) == account
            and _norm(existing.get("keyword")) == keyword
            and _norm(existing.get("video_id")) == video_id
            and _norm(existing.get("url")) == url
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


def _delivery_items(value: Any, *, depth: int = 0) -> tuple[list[Any], str | None]:
    """Unwrap nested list job packages; only inner item arrays are records."""
    if value is None or value == "":
        return [], "delivery response unavailable"
    parsed = parse_json_value(value)
    if isinstance(parsed, list):
        return parsed, None
    if not isinstance(parsed, dict):
        return [], "delivery response is not a list"
    if depth > 4:
        return [], "delivery response is not a list"
    if parsed.get("ok") is False:
        return [], extract_dify_error(parsed) or "delivery request failed"
    status = str(parsed.get("status") or "").strip().lower()
    if "command" in parsed and status in {"failed", "timeout", "cancelled", "canceled", "error"}:
        return [], _delivery_layer_error(parsed) or "delivery request failed"
    layer_error = _delivery_layer_error(parsed)
    if layer_error:
        return [], layer_error
    for key in ("items", "list", "comments", "messages", "result"):
        if isinstance(parsed.get(key), list):
            return parsed[key], None
    data = parsed.get("data")
    if isinstance(data, list):
        return data, None
    parsed_data = parse_json_value(data)
    if isinstance(parsed_data, list):
        return parsed_data, None
    if isinstance(parsed_data, dict):
        return _delivery_items(parsed_data, depth=depth + 1)
    return [], "delivery response is not a list"


def _delivery_layer_error(payload: dict[str, Any]) -> str | None:
    for key in ("error", "reason", "error_message", "failure_reason"):
        error = payload.get(key)
        if error is None or not str(error).strip():
            continue
        if isinstance(error, (dict, list)):
            return json.dumps(error, ensure_ascii=False)
        return str(error)
    return None


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
            if status in {"failed", "needs_login", "cancelled"}:
                errors.append(extract_dify_error(item) or "Dify 未提供具体失败原因")
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


def _coerce_node_index(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def upsert_workflow_node(nodes: dict[tuple[str, int], dict[str, Any]], order: list[tuple[str, int]], event: Any) -> list[dict[str, Any]]:
    compact = compact_workflow_node(event)
    if compact is None and isinstance(event, dict) and event.get("node_id"):
        compact = {
            "node_id": str(event.get("node_id") or ""),
            "title": str(event.get("title") or event.get("label") or event.get("node_id") or ""),
            "node_type": event.get("node_type"),
            "index": _coerce_node_index(event.get("index")),
            "status": str(event.get("status") or "running"),
        }
        if event.get("error") not in (None, ""):
            compact["error"] = event.get("error")
    if not compact or not compact.get("node_id"):
        return [nodes[key] for key in order]
    key = (str(compact["node_id"]), _coerce_node_index(compact.get("index")))
    if key not in nodes:
        order.append(key)
    nodes[key] = compact
    return [nodes[item] for item in order]


def emit_dify_node_progress(nodes: list[dict[str, Any]]) -> None:
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        return
    if writer is None:
        return
    try:
        writer({"dify_nodes": list(nodes)})
    except Exception:
        return


def run_discover_leads(
    *,
    settings,
    business_repo,
    dify_client,
    configurable: dict[str, Any],
    platform: str,
    account: str,
    keyword: str = "",
    video_id: str = "",
    url: str = "",
    limit: int | str | None = None,
    channels: str = "",
    max_comments: str = "",
    reply_limit: str = "",
    message_limit: str = "",
    select: str = "",
    list_status: str = "",
) -> dict[str, Any]:
    user_id_raw = configurable.get("user_id")
    agent_instance_id_raw = configurable.get("agent_instance_id")
    thread_id = str(configurable.get("thread_id") or "") or None
    allowed = list(configurable.get("allowed_workflow_codes") or [])
    if LEAD_WORKFLOW_CODE not in allowed:
        return {"ok": False, "error": "workflow not bound", "status": "failed"}
    missing = validate_lead_args(
        platform=(platform or "").strip(),
        account=account,
        keyword=keyword,
        video_id=video_id,
        url=url,
    )
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
        platform=(platform or "").strip(),
        account=account_text,
        keyword=(keyword or "").strip(),
        video_id=(video_id or "").strip(),
        url=(url or "").strip(),
        limit=limit,
        channels=(channels or "").strip(),
        max_comments=(max_comments or "").strip(),
        reply_limit=(reply_limit or "").strip(),
        message_limit=(message_limit or "").strip(),
        select=(select or "").strip(),
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
    nodes_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    node_order: list[tuple[str, int]] = []

    def on_event(event: Any) -> None:
        snapshot = upsert_workflow_node(nodes_by_key, node_order, event)
        emit_dify_node_progress(snapshot)

    result = dify_client.run(LEAD_WORKFLOW_CODE, inputs, user=str(user_id), on_event=on_event)
    outputs = result.get("outputs") if isinstance(result.get("outputs"), dict) else {}
    dify_workflow_status = str(result.get("dify_workflow_status") or "unverified")
    workflow_ok = bool(result.get("workflow_ok"))
    job_status = normalize_job_status(result.get("job_status"))
    if isinstance(outputs, dict):
        response = parse_json_value(outputs.get("job_response"))
        response_dict = response if isinstance(response, dict) else {}
        response_data = response_dict.get("data") if isinstance(response_dict.get("data"), dict) else {}
        response_raw = response_data.get("status") or response_dict.get("status")
        if response_raw not in (None, ""):
            job_status = normalize_job_status(response_raw)
        elif job_status == "unverified":
            job_status = normalize_job_status(outputs.get("job_status"))
    lead_ok = parse_optional_bool(result.get("lead_ok"))
    lead_status = str(result.get("lead_status") or "").strip() or None
    lead_error = result.get("lead_error")
    video_status = result.get("video_status")
    video_id_result = result.get("video_id")
    result_summary = result.get("summary")
    if isinstance(outputs, dict):
        if lead_ok is None:
            lead_ok = parse_optional_bool(outputs.get("lead_ok"))
        lead_status = lead_status or (str(outputs.get("lead_status") or "").strip() or None)
        lead_error = lead_error or outputs.get("lead_error")
        video_status = video_status or outputs.get("video_status")
        video_id_result = video_id_result or outputs.get("video_id")
        result_summary = result_summary or outputs.get("summary")
    if isinstance(lead_error, (dict, list)):
        lead_error = json.dumps(lead_error, ensure_ascii=False)
    lead_error = str(lead_error).strip() if lead_error not in (None, "") else None
    if isinstance(result_summary, (dict, list)):
        result_summary = json.dumps(result_summary, ensure_ascii=False)
    result_summary = str(result_summary).strip() if result_summary not in (None, "") else None
    status = str(result.get("status") or (job_status if job_status != "unverified" else "failed"))
    if status not in WORKFLOW_RUN_STATUSES and status not in {"unverified"}:
        status = "failed"
    job_id = result.get("job_id") or outputs.get("job_id")
    workflow_run_id = result.get("workflow_run_id")
    task_error = result.get("error")
    job_response_error = extract_dify_error(outputs.get("job_response")) if isinstance(outputs, dict) else None
    if not task_error and job_status in {"failed", "timeout", "cancelled"}:
        task_error = job_response_error
    if job_status == "unverified" and not task_error:
        task_error = "job status unavailable"
    if workflow_ok and lead_ok is None and not task_error:
        task_error = "lead result unavailable"
    if job_status == "failed" and not task_error:
        task_error = "job failed"
    delivery, message_details, delivery_errors, delivery_ok = _delivery_result(outputs, job_status=job_status)
    error_parts: list[str] = []
    if lead_error:
        error_parts.append(lead_error)
    for candidate in [task_error, *delivery_errors]:
        candidate_text = str(candidate) if candidate else ""
        if (
            (task_error == "job status unavailable" or lead_ok is False)
            and candidate_text.endswith(": delivery response unavailable")
        ):
            continue
        if candidate_text and candidate_text not in error_parts:
            error_parts.append(candidate_text)
    error = "; ".join(error_parts) or None
    if not workflow_ok:
        status = str(result.get("status") or "failed")
    elif lead_ok is True:
        status = "succeeded"
    elif job_status == "cancelled":
        status = "cancelled"
    elif job_status == "timeout":
        status = "timeout"
    elif lead_status in {"needs_login", "failed"} or lead_ok is False:
        status = "failed"
        delivery_ok = False
    else:
        status = "unverified"
    written = {"videos": 0, "comments": 0, "dms": 0}
    if lead_ok is True and job_status == "succeeded":
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
    ok = bool(workflow_ok and lead_ok is True)
    summary = result_summary or summarize_lead_result(
        status=status,
        outputs=outputs,
        written=written,
        error=error,
        delivery=delivery,
    )
    payload = {
        "ok": ok,
        "workflow_ok": workflow_ok,
        "delivery_ok": delivery_ok,
        "status": status,
        "platform": inputs.get("platform"),
        "dify_workflow_status": dify_workflow_status,
        "lead_ok": lead_ok,
        "lead_status": lead_status,
        "lead_error": lead_error,
        "video_status": video_status,
        "video_id": video_id_result,
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
    if node_order:
        payload["workflow_nodes"] = [nodes_by_key[key] for key in node_order]
    return payload
