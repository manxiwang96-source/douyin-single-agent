from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ToolExecutionRecord:
    execution_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    config_version_id: UUID
    thread_id: str
    tool_code: str
    risk_level: str
    approval_status: str
    execution_status: str
    input_digest: str | None
    output_digest: str | None
    external_request_id: str | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None = None


class InMemoryToolAuditRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, ToolExecutionRecord] = {}

    def start(self, *, user_id: UUID, agent_instance_id: UUID, config_version_id: UUID, thread_id: str, tool_code: str, risk_level: str = "low", approval_status: str = "not_required", inputs: Any = None) -> ToolExecutionRecord:
        record = ToolExecutionRecord(uuid4(), user_id, agent_instance_id, config_version_id, thread_id, tool_code, risk_level, approval_status, "running", digest(inputs) if inputs is not None else None, None, None, None, _now())
        self.records[record.execution_id] = record
        return record

    def complete(self, execution_id: UUID, *, status: str, output: Any = None, error_code: str | None = None, external_request_id: str | None = None) -> ToolExecutionRecord:
        current = self.records[execution_id]
        updated = replace(current, execution_status=status, output_digest=digest(output) if output is not None else None, error_code=error_code, external_request_id=external_request_id, completed_at=_now())
        self.records[execution_id] = updated
        return updated

    def list_for_scope(self, *, user_id: UUID, agent_instance_id: UUID, config_version_id: UUID, thread_id: str | None = None) -> list[ToolExecutionRecord]:
        user_id = UUID(str(user_id))
        agent_instance_id = UUID(str(agent_instance_id))
        config_version_id = UUID(str(config_version_id))
        return [
            item for item in self.records.values()
            if item.user_id == user_id
            and item.agent_instance_id == agent_instance_id
            and item.config_version_id == config_version_id
            and (thread_id is None or item.thread_id == str(thread_id))
        ]


class PostgresToolAuditRepository:
    def __init__(self, pool) -> None:
        self.pool = pool

    def start(self, **kwargs) -> ToolExecutionRecord:
        record = ToolExecutionRecord(uuid4(), kwargs["user_id"], kwargs["agent_instance_id"], kwargs["config_version_id"], kwargs["thread_id"], kwargs["tool_code"], kwargs.get("risk_level", "low"), kwargs.get("approval_status", "not_required"), "running", digest(kwargs.get("inputs")) if kwargs.get("inputs") is not None else None, None, None, None, _now())
        with self.pool.connection() as conn:
            conn.execute("""INSERT INTO tool_execution_records (execution_id,user_id,agent_instance_id,config_version_id,thread_id,tool_code,risk_level,approval_status,execution_status,input_digest,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (record.execution_id,record.user_id,record.agent_instance_id,record.config_version_id,record.thread_id,record.tool_code,record.risk_level,record.approval_status,record.execution_status,record.input_digest,record.created_at))
        return record

    def complete(self, execution_id: UUID, *, status: str, output: Any = None, error_code: str | None = None, external_request_id: str | None = None) -> ToolExecutionRecord:
        with self.pool.connection() as conn:
            row = conn.execute("""UPDATE tool_execution_records SET execution_status=%s,output_digest=%s,error_code=%s,external_request_id=%s,completed_at=%s WHERE execution_id=%s RETURNING *""", (status,digest(output) if output is not None else None,error_code,external_request_id,_now(),execution_id)).fetchone()
        return _from_row(row)

    def list_for_scope(self, *, user_id: UUID, agent_instance_id: UUID, config_version_id: UUID, thread_id: str | None = None) -> list[ToolExecutionRecord]:
        sql = "SELECT * FROM tool_execution_records WHERE user_id=%s AND agent_instance_id=%s AND config_version_id=%s"
        params = [user_id, agent_instance_id, config_version_id]
        if thread_id is not None:
            sql += " AND thread_id=%s"; params.append(thread_id)
        sql += " ORDER BY created_at"
        with self.pool.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_from_row(row) for row in rows]


def _row_value(row, key: str, index: int):
    if hasattr(row, "get"):
        return row.get(key)
    return row[index]


def _from_row(row) -> ToolExecutionRecord:
    return ToolExecutionRecord(
        UUID(str(_row_value(row, "execution_id", 0))),
        UUID(str(_row_value(row, "user_id", 1))),
        UUID(str(_row_value(row, "agent_instance_id", 2))),
        UUID(str(_row_value(row, "config_version_id", 3))),
        str(_row_value(row, "thread_id", 4)),
        _row_value(row, "tool_code", 5),
        _row_value(row, "risk_level", 6),
        _row_value(row, "approval_status", 7),
        _row_value(row, "execution_status", 8),
        _row_value(row, "input_digest", 9),
        _row_value(row, "output_digest", 10),
        _row_value(row, "external_request_id", 11),
        _row_value(row, "error_code", 12),
        _row_value(row, "created_at", 13),
        _row_value(row, "completed_at", 14),
    )
