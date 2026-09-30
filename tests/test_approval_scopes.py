from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.approvals import ApprovalError, ApprovalManager, ApprovalScopeError


def _scope():
    return {
        "user_id": uuid4(),
        "agent_instance_id": uuid4(),
        "config_version_id": uuid4(),
        "thread_id": "thread-a",
        "approval_kind": "skill",
        "resource_code": "external-skill",
    }


def _approve(manager: ApprovalManager, scope: dict, approval_scope: str = "once"):
    record = manager.repository.request(**scope, approval_scope=approval_scope)
    return manager.repository.decide(record.approval_id, user_id=scope["user_id"], approved=True)


def test_once_is_consumed_and_cannot_cross_scope():
    manager = ApprovalManager()
    scope = _scope()
    _approve(manager, scope, "once")
    assert manager.ensure(**scope)
    assert manager.ensure(**scope, consume=True)
    assert not manager.ensure(**scope)
    assert not manager.ensure(**{**scope, "thread_id": "thread-b"})
    assert not manager.ensure(**{**scope, "config_version_id": uuid4()})


def test_session_stays_valid_for_thread_but_not_other_thread_or_config():
    manager = ApprovalManager()
    scope = _scope()
    _approve(manager, scope, "session")
    assert manager.ensure(**scope)
    assert manager.ensure(**scope, consume=True)
    assert manager.ensure(**scope)
    assert not manager.ensure(**{**scope, "thread_id": "thread-b"})
    assert not manager.ensure(**{**scope, "config_version_id": uuid4()})


def test_always_requires_explicit_consumption_before_next_request():
    manager = ApprovalManager()
    scope = _scope()
    _approve(manager, scope, "always")
    assert manager.ensure(**scope)
    manager.ensure(**scope, consume=True)
    assert not manager.ensure(**scope)
    new_record = manager.repository.request(**scope, approval_scope="always")
    assert new_record.status == "pending"


def test_expired_approval_is_not_usable_and_is_re_requestable():
    manager = ApprovalManager()
    scope = _scope()
    record = manager.repository.request(
        **scope,
        approval_scope="once",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    manager.repository.decide(record.approval_id, user_id=scope["user_id"], approved=True)
    assert not manager.ensure(**scope)
    assert manager.repository.get(record.approval_id).status == "expired"
    new_record = manager.repository.request(**scope, approval_scope="once")
    assert new_record.approval_id != record.approval_id


def test_decide_and_revoke_are_idempotent_and_user_scoped():
    manager = ApprovalManager()
    scope = _scope()
    record = manager.repository.request(**scope)
    with pytest.raises(ApprovalScopeError):
        manager.repository.decide(record.approval_id, user_id=uuid4(), approved=True)
    approved = manager.repository.decide(record.approval_id, user_id=scope["user_id"], approved=True)
    assert manager.repository.decide(record.approval_id, user_id=scope["user_id"], approved=True) == approved
    assert manager.revoke_scope(
        user_id=scope["user_id"], agent_instance_id=scope["agent_instance_id"],
        config_version_id=scope["config_version_id"],
    ) == 1
    assert manager.revoke_scope(
        user_id=scope["user_id"], agent_instance_id=scope["agent_instance_id"],
        config_version_id=scope["config_version_id"],
    ) == 0
    assert not manager.ensure(**scope)


def test_four_approval_kinds_never_derive_from_each_other():
    manager = ApprovalManager()
    scope = _scope()
    for kind in ("import", "skill", "script", "tool"):
        _approve(manager, {**scope, "approval_kind": kind}, "session")
    for kind in ("import", "skill", "script", "tool"):
        assert manager.ensure(**{**scope, "approval_kind": kind})
    assert not manager.ensure(**{**scope, "approval_kind": "tool", "resource_code": "other-tool"})


def test_invalid_scope_is_rejected():
    manager = ApprovalManager()
    with pytest.raises(ValueError):
        manager.repository.request(**_scope(), approval_scope="forever")
