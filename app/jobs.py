from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage

from app.graph import SCHEDULER_AGENT_INSTANCE_ID, SCHEDULER_USER_ID, build_invoke_config
from app.mcp_client import DayFacts, run_coroutine

JOBS_NAMESPACE = ("assistant", "jobs")
HYDRATE_SLOTS = ("08", "10", "12", "14", "16", "18", "20", "22")
MORNING_THREAD_PREFIX = "assistant-morning-brief"
MORNING_BRIEF_GRAPH_TIMEOUT_S = 180.0


def now_in_zone(settings, now: datetime | None = None) -> datetime:
    zone = ZoneInfo(settings.assistant_timezone)
    current = datetime.now(zone) if now is None else now
    if current.tzinfo is None:
        return current.replace(tzinfo=zone)
    return current.astimezone(zone)


def normalize_slot(slot: str | int) -> str:
    text = str(slot).strip()
    if ":" in text:
        text = text.split(":", 1)[0]
    hour = int(text)
    if hour < 0 or hour > 23:
        raise ValueError(f"invalid hydrate slot: {slot}")
    return f"{hour:02d}"


def _job_item(store, key: str):
    return store.get(JOBS_NAMESPACE, key)


def job_already_done(store, key: str) -> bool:
    return _job_item(store, key) is not None


def mark_job_done(store, key: str, payload: dict[str, Any]) -> None:
    store.put(JOBS_NAMESPACE, key, payload)


def morning_brief_key(day: str) -> str:
    return f"morning_brief:{day}"


def hydrate_key(day: str, slot: str) -> str:
    return f"hydrate:{day}:{slot}"


def format_facts_fallback(facts: DayFacts) -> str:
    temperature = "未知" if facts.temperature_c is None else f"{facts.temperature_c}°C"
    return (
        f"今天是{facts.weekday}。{facts.city}天气{facts.weather}，气温{temperature}。"
        "\n（模型未成功发送，已回退为事实摘要）"
    )


def morning_brief_prompt(facts: DayFacts) -> str:
    temperature = "未知" if facts.temperature_c is None else f"{facts.temperature_c}°C"
    return (
        "请根据以下真实事实，写今天的晨间简报，并调用 send_email 发给我。\n"
        f"- 城市：{facts.city}\n"
        f"- 星期：{facts.weekday}\n"
        f"- 天气：{facts.weather}\n"
        f"- 温度：{temperature}\n"
        f"- 日期时间：{facts.iso or facts.date}\n"
        "要求：\n"
        "1. 必须调用 send_email，subject 用「晨间简报 YYYY-MM-DD」。\n"
        "2. 正文先陈述上述事实，再给出 2-4 条针对今天情境的具体建议。\n"
        "3. 建议必须根据这些事实临场生成，不要套固定模板，也不要写小红书笔记格式。\n"
        "4. 可以把 08:00 喝水提醒并入正文。"
    )


async def arun_morning_brief(
    runtime,
    *,
    force: bool = False,
    now: datetime | None = None,
    graph_timeout_s: float | None = None,
) -> dict[str, Any]:
    current = now_in_zone(runtime.settings, now)
    day = current.date().isoformat()
    key = morning_brief_key(day)
    if not force and job_already_done(runtime.memory_store, key):
        return {"status": "skipped", "reason": "already_sent", "kind": "morning_brief", "date": day}
    facts = await runtime.facts_provider.aget_facts(runtime.settings.assistant_city)
    sent_before = len(getattr(runtime.email_client, "sends", []) or [])
    config = build_invoke_config(
        thread_id=f"{MORNING_THREAD_PREFIX}-{day}",
        user_id=SCHEDULER_USER_ID,
        agent_instance_id=SCHEDULER_AGENT_INSTANCE_ID,
    )
    timeout = MORNING_BRIEF_GRAPH_TIMEOUT_S if graph_timeout_s is None else graph_timeout_s
    try:
        await asyncio.wait_for(
            runtime.graph.ainvoke(
                {"messages": [HumanMessage(content=morning_brief_prompt(facts))]},
                config,
            ),
            timeout=timeout,
        )
    except Exception:
        pass
    sent_after = getattr(runtime.email_client, "sends", []) or []
    if len(sent_after) > sent_before:
        status = "sent"
        email = sent_after[-1]
    else:
        subject = f"晨间简报 {day}"
        email = runtime.email_client.send(subject=subject, body=format_facts_fallback(facts))
        status = "sent_fallback"
    result = {
        "status": status,
        "kind": "morning_brief",
        "date": day,
        "facts": facts.as_dict(),
        "email": {
            "subject": email.get("subject"),
            "to": email.get("to"),
        },
    }
    mark_job_done(runtime.memory_store, key, {"status": status, "date": day})
    return result


async def arun_hydrate(
    runtime,
    slot: str | int,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized = normalize_slot(slot)
    if normalized == "08":
        return {
            "status": "merged_into_morning_brief",
            "kind": "hydrate",
            "slot": normalized,
        }
    if normalized not in HYDRATE_SLOTS:
        raise ValueError(f"hydrate slot must be one of {HYDRATE_SLOTS}")
    current = now_in_zone(runtime.settings, now)
    day = current.date().isoformat()
    key = hydrate_key(day, normalized)
    if not force and job_already_done(runtime.memory_store, key):
        return {
            "status": "skipped",
            "reason": "already_sent",
            "kind": "hydrate",
            "slot": normalized,
            "date": day,
        }
    subject = "喝水提醒"
    body = f"现在是 {normalized}:00，记得喝一杯水。"
    email = runtime.email_client.send(subject=subject, body=body)
    result = {
        "status": "sent",
        "kind": "hydrate",
        "slot": normalized,
        "date": day,
        "email": {"subject": email.get("subject"), "to": email.get("to")},
    }
    mark_job_done(runtime.memory_store, key, {"status": "sent", "slot": normalized, "date": day})
    return result


async def acatch_up_jobs(runtime, now: datetime | None = None) -> list[dict[str, Any]]:
    current = now_in_zone(runtime.settings, now)
    results: list[dict[str, Any]] = []
    if current.hour > 22:
        return results
    if current.hour >= 8:
        results.append(await arun_morning_brief(runtime, now=current))
    slot = f"{current.hour:02d}"
    if slot in HYDRATE_SLOTS and slot != "08":
        results.append(await arun_hydrate(runtime, slot, now=current))
    return results


def run_morning_brief(
    runtime,
    *,
    force: bool = False,
    now: datetime | None = None,
    graph_timeout_s: float | None = None,
) -> dict[str, Any]:
    return run_coroutine(
        arun_morning_brief(
            runtime,
            force=force,
            now=now,
            graph_timeout_s=graph_timeout_s,
        )
    )


def run_hydrate(
    runtime,
    slot: str | int,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    return run_coroutine(arun_hydrate(runtime, slot, force=force, now=now))


def catch_up_jobs(runtime, now: datetime | None = None) -> list[dict[str, Any]]:
    return run_coroutine(acatch_up_jobs(runtime, now=now))