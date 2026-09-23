from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plaza import isoformat
from app.repository import (
    JobRunNotCancellableError,
    NotFoundError,
    utcnow,
)

TERMINAL_JOB_RUN_STATUSES = frozenset({"succeeded", "failed", "skipped", "cancelled"})
PROTECTED_ENGAGE_STATUSES = frozenset({"sent", "failed", "needs_login", "cancelled"})
CANCELLABLE_ENGAGE_STATUSES = frozenset({"proposed", "ready_to_send", "sending"})


class JobAccessDenied(Exception):
    """Caller does not own this job or run."""


def parse_job_uuid(raw: str, *, label: str) -> UUID:
    try:
        return UUID(str(raw))
    except Exception as exc:
        raise NotFoundError(f"{label} not found") from exc


def job_payload(job) -> dict[str, Any]:
    return {
        "job_id": str(job.job_id),
        "user_id": str(job.user_id),
        "agent_instance_id": str(job.agent_instance_id),
        "kind": job.kind,
        "cron": job.cron,
        "timezone": job.timezone,
        "enabled": bool(job.enabled),
        "require_approval": bool(job.require_approval),
        "payload": dict(job.payload or {}),
        "created_at": isoformat(job.created_at),
        "updated_at": isoformat(job.updated_at),
    }


def run_payload(run) -> dict[str, Any]:
    return {
        "job_run_id": str(run.job_run_id),
        "job_id": str(run.job_id),
        "user_id": str(run.user_id),
        "agent_instance_id": str(run.agent_instance_id),
        "scheduled_for": isoformat(run.scheduled_for),
        "status": run.status,
        "error": run.error,
        "started_at": isoformat(run.started_at),
        "finished_at": isoformat(run.finished_at),
    }


def list_owned_jobs(repo, *, user_id: UUID, agent_instance_id: UUID) -> dict[str, Any]:
    jobs = repo.list_job_definitions(user_id, agent_instance_id)
    runs = repo.list_job_runs(user_id, agent_instance_id)
    return {
        "ok": True,
        "jobs": [job_payload(item) for item in jobs],
        "runs": [run_payload(item) for item in runs],
    }


def _owned_job(repo, *, user_id: UUID, job_id: UUID, agent_instance_id: UUID | None = None):
    job = repo.get_job_definition(job_id)
    if job is None:
        raise NotFoundError(f"job definition not found: {job_id}")
    if job.user_id != user_id:
        raise JobAccessDenied("job forbidden")
    if agent_instance_id is not None and job.agent_instance_id != agent_instance_id:
        raise JobAccessDenied("job forbidden")
    return job


def _owned_run(repo, *, user_id: UUID, job_run_id: UUID, agent_instance_id: UUID | None = None):
    run = repo.get_job_run(job_run_id)
    if run is None:
        raise NotFoundError(f"job run not found: {job_run_id}")
    if run.user_id != user_id:
        raise JobAccessDenied("job run forbidden")
    if agent_instance_id is not None and run.agent_instance_id != agent_instance_id:
        raise JobAccessDenied("job run forbidden")
    return run


def disable_job(
    repo,
    *,
    user_id: UUID,
    job_id: UUID,
    agent_instance_id: UUID | None = None,
) -> dict[str, Any]:
    job = _owned_job(repo, user_id=user_id, job_id=job_id, agent_instance_id=agent_instance_id)
    updated = repo.set_job_enabled(job.job_id, False)
    return {
        "ok": True,
        "deleted": False,
        "job": job_payload(updated),
    }


def cancel_job_run(
    repo,
    *,
    user_id: UUID,
    job_run_id: UUID,
    agent_instance_id: UUID | None = None,
) -> dict[str, Any]:
    run = _owned_run(repo, user_id=user_id, job_run_id=job_run_id, agent_instance_id=agent_instance_id)
    if run.status in TERMINAL_JOB_RUN_STATUSES:
        raise JobRunNotCancellableError(f"job run cannot be cancelled: {run.status}")
    updated = repo.update_job_run(
        run.job_run_id,
        status="cancelled",
        finished_at=utcnow(),
        error="cancelled",
    )
    local = _cancel_local_rows(repo, updated)
    return {
        "ok": True,
        "deleted": False,
        "run": run_payload(updated),
        "local": local,
    }


def _linked_video_ids(repo, run) -> set[str]:
    return {
        item.platform_video_id
        for item in repo.list_engage_videos(run.user_id, run.agent_instance_id)
        if item.job_run_id == run.job_run_id and item.platform_video_id
    }


def _should_cancel_engage(status: str) -> bool:
    return status in CANCELLABLE_ENGAGE_STATUSES and status not in PROTECTED_ENGAGE_STATUSES


def _cancel_local_rows(repo, run) -> dict[str, int]:
    written = {"comments": 0, "dms": 0, "workflow_runs": 0}
    for item in repo.list_workflow_runs(run.user_id, run.agent_instance_id):
        if item.job_run_id != run.job_run_id:
            continue
        if item.status == "running":
            repo.update_workflow_run(item.id, status="cancelled", error="job run cancelled")
            written["workflow_runs"] += 1
    video_ids = _linked_video_ids(repo, run)
    if not video_ids:
        return written
    for comment in repo.list_engage_comments(run.user_id, run.agent_instance_id):
        if comment.video_id not in video_ids:
            continue
        if not _should_cancel_engage(comment.status):
            continue
        repo.update_engage_comment(comment.id, status="cancelled")
        written["comments"] += 1
    for dm in repo.list_engage_dms(run.user_id, run.agent_instance_id):
        if dm.video_id not in video_ids:
            continue
        if not _should_cancel_engage(dm.status):
            continue
        repo.update_engage_dm(dm.id, status="cancelled")
        written["dms"] += 1
    return written


def run_list_jobs(repo, configurable: dict[str, Any]) -> dict[str, Any]:
    owner = _owner_ids(configurable)
    if owner is None:
        return {"ok": False, "error": "missing instance context", "status": "failed"}
    user_id, agent_instance_id = owner
    return list_owned_jobs(repo, user_id=user_id, agent_instance_id=agent_instance_id)


def run_cancel_job(
    repo,
    configurable: dict[str, Any],
    *,
    job_id: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    owner = _owner_ids(configurable)
    if owner is None:
        return {"ok": False, "error": "missing instance context", "status": "failed"}
    user_id, agent_instance_id = owner
    job_text = (job_id or "").strip()
    run_text = (run_id or "").strip()
    if not job_text and not run_text:
        return {"ok": False, "error": "job_id or run_id is required", "status": "failed"}
    result: dict[str, Any] = {"ok": True}
    try:
        if run_text:
            cancelled = cancel_job_run(
                repo,
                user_id=user_id,
                job_run_id=parse_job_uuid(run_text, label="job run"),
                agent_instance_id=agent_instance_id,
            )
            result["run"] = cancelled["run"]
            result["local"] = cancelled["local"]
            result["deleted"] = False
        if job_text:
            disabled = disable_job(
                repo,
                user_id=user_id,
                job_id=parse_job_uuid(job_text, label="job"),
                agent_instance_id=agent_instance_id,
            )
            result["job"] = disabled["job"]
            result["deleted"] = False
        return result
    except JobAccessDenied:
        return {"ok": False, "error": "forbidden", "status": "forbidden"}
    except NotFoundError:
        return {"ok": False, "error": "not found", "status": "not_found"}
    except JobRunNotCancellableError as exc:
        return {"ok": False, "error": str(exc), "status": "not_cancellable"}


def _owner_ids(configurable: dict[str, Any]) -> tuple[UUID, UUID] | None:
    try:
        return UUID(str(configurable.get("user_id"))), UUID(str(configurable.get("agent_instance_id")))
    except Exception:
        return None
