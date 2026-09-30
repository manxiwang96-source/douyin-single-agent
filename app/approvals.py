from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation

ApprovalKind = Literal["import", "skill", "script", "tool"]
ApprovalScope = Literal["once", "session", "always"]
APPROVAL_KINDS = ("import", "skill", "script", "tool")
APPROVAL_SCOPES = ("once", "session", "always")
TERMINAL_STATUSES = ("denied", "expired", "revoked")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    config_version_id: UUID
    thread_id: str
    approval_kind: ApprovalKind
    resource_code: str
    status: str
    requested_at: datetime
    decided_at: datetime | None = None
    decided_by: UUID | None = None
    reason: str = ""
    approval_scope: ApprovalScope = "once"
    expires_at: datetime | None = None
    consumed_at: datetime | None = None


class ApprovalError(RuntimeError):
    pass


class ApprovalScopeError(ApprovalError):
    pass


class InMemoryApprovalRepository:
    """Isolated, durable-in-process approval store for all four approval kinds.

    ``once`` and ``always`` grants are consumed by the caller after one
    successful action. ``session`` grants remain valid for the exact thread and
    config version. No scope can cross a user, agent, config version, or thread
    boundary.
    """

    def __init__(self):
        self.records: dict[UUID, ApprovalRecord] = {}

    def get(self, approval_id: UUID) -> ApprovalRecord | None:
        return self.records.get(approval_id)

    @staticmethod
    def _validate_kind_scope(approval_kind: ApprovalKind, approval_scope: ApprovalScope) -> None:
        if approval_kind not in APPROVAL_KINDS:
            raise ValueError(f"unsupported approval kind: {approval_kind}")
        if approval_scope not in APPROVAL_SCOPES:
            raise ValueError(f"unsupported approval scope: {approval_scope}")

    @staticmethod
    def _expired(record: ApprovalRecord, now: datetime | None = None) -> bool:
        return bool(record.expires_at and record.expires_at <= (now or _now()))

    def _expire_if_needed(self, record: ApprovalRecord) -> ApprovalRecord:
        if record.status == "approved" and self._expired(record):
            record = replace(record, status="expired")
            self.records[record.approval_id] = record
        return record

    def request(
        self,
        *,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID,
        thread_id: str,
        approval_kind: ApprovalKind,
        resource_code: str,
        approval_scope: ApprovalScope = "once",
        expires_at: datetime | None = None,
    ) -> ApprovalRecord:
        self._validate_kind_scope(approval_kind, approval_scope)
        for existing in list(self.records.values()):
            if not (
                existing.user_id == user_id
                and existing.agent_instance_id == agent_instance_id
                and existing.config_version_id == config_version_id
                and existing.thread_id == thread_id
                and existing.approval_kind == approval_kind
                and existing.resource_code == resource_code
                and existing.approval_scope == approval_scope
            ):
                continue
            existing = self._expire_if_needed(existing)
            if existing.status == "pending":
                return existing
            if existing.status == "approved" and not (
                approval_scope in {"once", "always"} and existing.consumed_at is not None
            ):
                return existing
        record = ApprovalRecord(
            approval_id=uuid4(),
            user_id=user_id,
            agent_instance_id=agent_instance_id,
            config_version_id=config_version_id,
            thread_id=thread_id,
            approval_kind=approval_kind,
            resource_code=resource_code,
            status="pending",
            requested_at=_now(),
            approval_scope=approval_scope,
            expires_at=expires_at,
        )
        self.records[record.approval_id] = record
        return record

    def decide(self, approval_id: UUID, *, user_id: UUID, approved: bool, reason: str = "") -> ApprovalRecord:
        record = self.records.get(approval_id)
        if record is None or record.user_id != user_id:
            raise ApprovalScopeError("approval does not belong to current user")
        record = self._expire_if_needed(record)
        target = "approved" if approved else "denied"
        if record.status == target:
            return record
        if record.status != "pending":
            raise ApprovalError(f"approval is already {record.status}")
        updated = replace(
            record,
            status=target,
            decided_at=_now(),
            decided_by=user_id,
            reason=reason,
            consumed_at=None,
        )
        self.records[approval_id] = updated
        return updated

    def is_approved(
        self,
        *,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID,
        thread_id: str,
        approval_kind: ApprovalKind,
        resource_code: str,
        approval_scope: ApprovalScope | None = None,
    ) -> bool:
        for item in list(self.records.values()):
            if not (
                item.user_id == user_id
                and item.agent_instance_id == agent_instance_id
                and item.config_version_id == config_version_id
                and item.thread_id == thread_id
                and item.approval_kind == approval_kind
                and item.resource_code == resource_code
                and (approval_scope is None or item.approval_scope == approval_scope)
            ):
                continue
            item = self._expire_if_needed(item)
            if item.status != "approved":
                continue
            if item.approval_scope in {"once", "always"} and item.consumed_at is not None:
                continue
            return True
        return False

    def consume(
        self,
        *,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID,
        thread_id: str,
        approval_kind: ApprovalKind,
        resource_code: str,
        approval_scope: ApprovalScope | None = None,
    ) -> ApprovalRecord | None:
        for item in list(self.records.values()):
            if self.is_approved(
                user_id=user_id,
                agent_instance_id=agent_instance_id,
                config_version_id=config_version_id,
                thread_id=thread_id,
                approval_kind=approval_kind,
                resource_code=resource_code,
                approval_scope=approval_scope,
            ):
                if (
                    item.user_id == user_id
                    and item.agent_instance_id == agent_instance_id
                    and item.config_version_id == config_version_id
                    and item.thread_id == thread_id
                    and item.approval_kind == approval_kind
                    and item.resource_code == resource_code
                    and (approval_scope is None or item.approval_scope == approval_scope)
                    and item.status == "approved"
                ):
                    updated = replace(item, consumed_at=_now())
                    self.records[item.approval_id] = updated
                    return updated
        return None

    def revoke_scope(self, *, user_id: UUID, agent_instance_id: UUID, config_version_id: UUID | None = None) -> int:
        changed = 0
        for approval_id, item in list(self.records.items()):
            if (
                item.user_id == user_id
                and item.agent_instance_id == agent_instance_id
                and (config_version_id is None or item.config_version_id == config_version_id)
                and item.status in {"pending", "approved"}
            ):
                self.records[approval_id] = replace(item, status="revoked", decided_at=_now(), decided_by=user_id)
                changed += 1
        return changed

    def list_for_scope(self, *, user_id: UUID, agent_instance_id: UUID, config_version_id: UUID, thread_id: str) -> list[ApprovalRecord]:
        return [
            item
            for item in self.records.values()
            if item.user_id == user_id
            and item.agent_instance_id == agent_instance_id
            and item.config_version_id == config_version_id
            and item.thread_id == thread_id
        ]

    def list_for_agent(
        self,
        *,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID | None = None,
        thread_id: str | None = None,
    ) -> list[ApprovalRecord]:
        return [
            item
            for item in self.records.values()
            if item.user_id == user_id
            and item.agent_instance_id == agent_instance_id
            and (config_version_id is None or item.config_version_id == config_version_id)
            and (thread_id is None or item.thread_id == thread_id)
        ]


class PostgresApprovalRepository:
    """PostgreSQL adapter for thread-scoped, four-kind approvals."""

    def __init__(self, pool):
        self.pool = pool

    def _row(self, row) -> ApprovalRecord:
        def _uuid(value):
            return value if isinstance(value, UUID) else UUID(str(value))

        return ApprovalRecord(
            approval_id=_uuid(row["approval_id"]),
            user_id=_uuid(row["user_id"]),
            agent_instance_id=_uuid(row["agent_instance_id"]),
            config_version_id=_uuid(row["config_version_id"]),
            thread_id=str(row["thread_id"]),
            approval_kind=row["approval_kind"],
            resource_code=str(row["resource_code"]),
            status=row["status"],
            requested_at=row["requested_at"],
            decided_at=row.get("decided_at"),
            decided_by=_uuid(row["decided_by"]) if row.get("decided_by") else None,
            reason=row.get("reason") or "",
            approval_scope=row.get("approval_scope") or "once",
            expires_at=row.get("expires_at"),
            consumed_at=row.get("consumed_at"),
        )

    def get(self, approval_id: UUID) -> ApprovalRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT * FROM thread_action_approvals WHERE approval_id = %s", (approval_id,)).fetchone()
        return self._row(row) if row else None

    def request(
        self,
        *,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID,
        thread_id: str,
        approval_kind: ApprovalKind,
        resource_code: str,
        approval_scope: ApprovalScope = "once",
        expires_at: datetime | None = None,
    ) -> ApprovalRecord:
        if approval_kind not in APPROVAL_KINDS:
            raise ValueError(f"unsupported approval kind: {approval_kind}")
        if approval_scope not in APPROVAL_SCOPES:
            raise ValueError(f"unsupported approval scope: {approval_scope}")
        approval_id = uuid4()
        with self.pool.connection() as conn:
            try:
                row = conn.execute(
                    """
                    INSERT INTO thread_action_approvals (
                        approval_id, user_id, agent_instance_id, config_version_id,
                        thread_id, approval_kind, resource_code, approval_scope, expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, agent_instance_id, config_version_id, thread_id, approval_kind, resource_code, approval_scope)
                    DO NOTHING
                    RETURNING *
                    """,
                    (approval_id, user_id, agent_instance_id, config_version_id, thread_id, approval_kind, resource_code, approval_scope, expires_at),
                ).fetchone()
            except UniqueViolation:
                row = None
            if row is None:
                row = conn.execute(
                    """
                    SELECT * FROM thread_action_approvals
                    WHERE user_id = %s AND agent_instance_id = %s AND config_version_id = %s
                      AND thread_id = %s AND approval_kind = %s AND resource_code = %s
                      AND approval_scope = %s
                    """,
                    (user_id, agent_instance_id, config_version_id, thread_id, approval_kind, resource_code, approval_scope),
                ).fetchone()
                if row and row["status"] in {"expired", "denied", "revoked"}:
                    row = conn.execute(
                        """
                        UPDATE thread_action_approvals
                        SET status = 'pending', requested_at = CURRENT_TIMESTAMP,
                            decided_at = NULL, decided_by = NULL, reason = '',
                            expires_at = %s, consumed_at = NULL, approval_scope = %s
                        WHERE approval_id = %s
                        RETURNING *
                        """,
                        (expires_at, approval_scope, row["approval_id"]),
                    ).fetchone()
        return self._row(row)

    def decide(self, approval_id: UUID, *, user_id: UUID, approved: bool, reason: str = "") -> ApprovalRecord:
        target = "approved" if approved else "denied"
        with self.pool.connection() as conn:
            current = conn.execute(
                "SELECT * FROM thread_action_approvals WHERE approval_id = %s AND user_id = %s",
                (approval_id, user_id),
            ).fetchone()
            if not current:
                raise ApprovalScopeError("approval does not belong to current user")
            if current["status"] == target:
                return self._row(current)
            if current["status"] != "pending":
                raise ApprovalError(f"approval is already {current['status']}")
            row = conn.execute(
                """
                UPDATE thread_action_approvals
                SET status = %s, decided_at = CURRENT_TIMESTAMP, decided_by = %s,
                    reason = %s, consumed_at = NULL
                WHERE approval_id = %s AND user_id = %s
                RETURNING *
                """,
                (target, user_id, reason, approval_id, user_id),
            ).fetchone()
        return self._row(row)

    def is_approved(
        self,
        *,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID,
        thread_id: str,
        approval_kind: ApprovalKind,
        resource_code: str,
        approval_scope: ApprovalScope | None = None,
    ) -> bool:
        clauses = [
            "user_id = %s", "agent_instance_id = %s", "config_version_id = %s",
            "thread_id = %s", "approval_kind = %s", "resource_code = %s",
            "status = 'approved'", "(expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
            "(approval_scope = 'session' OR consumed_at IS NULL)",
        ]
        params: list[object] = [user_id, agent_instance_id, config_version_id, thread_id, approval_kind, resource_code]
        if approval_scope is not None:
            clauses.append("approval_scope = %s")
            params.append(approval_scope)
        with self.pool.connection() as conn:
            row = conn.execute(f"SELECT 1 FROM thread_action_approvals WHERE {' AND '.join(clauses)}", tuple(params)).fetchone()
        return row is not None

    def consume(self, **scope) -> ApprovalRecord | None:
        with self.pool.connection() as conn:
            clauses = [
                "user_id = %s", "agent_instance_id = %s", "config_version_id = %s",
                "thread_id = %s", "approval_kind = %s", "resource_code = %s",
                "status = 'approved'", "(expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
                "approval_scope IN ('once', 'always')", "consumed_at IS NULL",
            ]
            params: list[object] = [scope["user_id"], scope["agent_instance_id"], scope["config_version_id"], scope["thread_id"], scope["approval_kind"], scope["resource_code"]]
            if scope.get("approval_scope") is not None:
                clauses.append("approval_scope = %s")
                params.append(scope["approval_scope"])
            row = conn.execute(
                f"UPDATE thread_action_approvals SET consumed_at = CURRENT_TIMESTAMP WHERE {' AND '.join(clauses)} RETURNING *",
                tuple(params),
            ).fetchone()
        return self._row(row) if row else None

    def revoke_scope(self, *, user_id: UUID, agent_instance_id: UUID, config_version_id: UUID | None = None) -> int:
        clauses = ["user_id = %s", "agent_instance_id = %s", "status IN ('pending', 'approved')"]
        params: list[object] = [user_id, agent_instance_id]
        if config_version_id is not None:
            clauses.append("config_version_id = %s")
            params.append(config_version_id)
        with self.pool.connection() as conn:
            row = conn.execute(
                f"UPDATE thread_action_approvals SET status = 'revoked', decided_at = CURRENT_TIMESTAMP, decided_by = %s WHERE {' AND '.join(clauses)}",
                tuple([user_id, *params]),
            )
            return row.rowcount

    def list_for_scope(self, *, user_id: UUID, agent_instance_id: UUID, config_version_id: UUID, thread_id: str) -> list[ApprovalRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM thread_action_approvals WHERE user_id = %s AND agent_instance_id = %s AND config_version_id = %s AND thread_id = %s ORDER BY requested_at",
                (user_id, agent_instance_id, config_version_id, thread_id),
            ).fetchall()
        return [self._row(row) for row in rows]

    def list_for_agent(
        self,
        *,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID | None = None,
        thread_id: str | None = None,
    ) -> list[ApprovalRecord]:
        clauses = ["user_id = %s", "agent_instance_id = %s"]
        params: list[object] = [user_id, agent_instance_id]
        if config_version_id is not None:
            clauses.append("config_version_id = %s")
            params.append(config_version_id)
        if thread_id is not None:
            clauses.append("thread_id = %s")
            params.append(thread_id)
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM thread_action_approvals WHERE {' AND '.join(clauses)} ORDER BY requested_at", tuple(params)
            ).fetchall()
        return [self._row(row) for row in rows]


class ApprovalManager:
    def __init__(self, repository=None):
        self.repository = repository or InMemoryApprovalRepository()

    def ensure(
        self,
        *,
        user_id: UUID,
        agent_instance_id: UUID,
        config_version_id: UUID,
        thread_id: str,
        approval_kind: ApprovalKind,
        resource_code: str,
        approval_scope: ApprovalScope | None = None,
        consume: bool = False,
    ) -> bool:
        approved = self.repository.is_approved(
            user_id=user_id,
            agent_instance_id=agent_instance_id,
            config_version_id=config_version_id,
            thread_id=thread_id,
            approval_kind=approval_kind,
            resource_code=resource_code,
            approval_scope=approval_scope,
        )
        if approved and consume:
            self.repository.consume(
                user_id=user_id,
                agent_instance_id=agent_instance_id,
                config_version_id=config_version_id,
                thread_id=thread_id,
                approval_kind=approval_kind,
                resource_code=resource_code,
                approval_scope=approval_scope,
            )
        return approved

    def require_or_request(self, *, approval_scope: ApprovalScope = "once", **scope) -> ApprovalRecord | None:
        if self.ensure(**scope, approval_scope=approval_scope):
            return None
        return self.repository.request(**scope, approval_scope=approval_scope)

    def revoke_scope(self, **scope) -> int:
        return self.repository.revoke_scope(**scope)
