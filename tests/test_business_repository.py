from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.repository import (
    DEFAULT_WORKFLOW_CODE,
    DuplicateBindingError,
    DuplicateJobRunError,
    DuplicateTitleError,
    JobDisabledError,
    InMemoryBusinessRepository,
    InvalidTitleError,
    KnowledgeSeed,
    NotFoundError,
    UnsupportedTemplateError,
)


@pytest.fixture(autouse=True)
def _no_real_postgres(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("business repository tests must not open real Postgres")

    monkeypatch.setattr("psycopg.connect", boom)


@pytest.fixture
def repo() -> InMemoryBusinessRepository:
    return InMemoryBusinessRepository()


def _user_and_instance(repo: InMemoryBusinessRepository, title: str = "助手A"):
    user = repo.create_user("alice", "hash-not-secret")
    instance = repo.create_agent_instance(user.user_id, title, intro="运营")
    return user, instance


def test_blank_and_whitespace_titles_are_rejected(repo):
    user, _instance = _user_and_instance(repo, "合法名")
    with pytest.raises(InvalidTitleError):
        repo.create_agent_instance(user.user_id, "   ")
    with pytest.raises(InvalidTitleError):
        repo.create_agent_instance(user.user_id, "助手 A")
    with pytest.raises(InvalidTitleError):
        repo.create_agent_instance(user.user_id, "助手\tA")


def test_duplicate_title_is_case_insensitive(repo):
    user, _instance = _user_and_instance(repo, "助手A")
    with pytest.raises(DuplicateTitleError):
        repo.create_agent_instance(user.user_id, "助手a")
    other = repo.create_user("bob", "hash-not-secret")
    second = repo.create_agent_instance(other.user_id, "助手A")
    assert second.user_id == other.user_id


def test_archived_title_can_be_reused(repo):
    user, instance = _user_and_instance(repo, "助手A")
    archived = repo.archive_agent_instance(instance.agent_instance_id)
    assert archived.status == "archived"
    assert archived.updated_at == instance.updated_at
    reused = repo.create_agent_instance(user.user_id, "助手A")
    assert reused.status == "active"
    assert reused.agent_instance_id != instance.agent_instance_id
    titles = [item.title for item in repo.list_agent_instances(user.user_id)]
    assert titles == ["助手A"]


def test_workflow_binding_is_unique_per_instance(repo):
    user, instance = _user_and_instance(repo)
    binding = repo.bind_workflow(user.user_id, instance.agent_instance_id)
    assert binding.workflow_code == DEFAULT_WORKFLOW_CODE
    with pytest.raises(DuplicateBindingError):
        repo.bind_workflow(user.user_id, instance.agent_instance_id, DEFAULT_WORKFLOW_CODE)
    other = repo.create_agent_instance(user.user_id, "助手B")
    second = repo.bind_workflow(user.user_id, other.agent_instance_id)
    assert second.agent_instance_id == other.agent_instance_id


def test_job_run_idempotency_key_is_unique(repo):
    user, instance = _user_and_instance(repo)
    job = repo.create_job_definition(
        user.user_id,
        instance.agent_instance_id,
        kind="douyin_topic_engage",
        cron="0 8 * * *",
    )
    assert job.require_approval is False
    scheduled_for = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)
    first = repo.create_job_run(job.job_id, scheduled_for)
    assert first.status == "scheduled"
    with pytest.raises(DuplicateJobRunError):
        repo.create_job_run(job.job_id, scheduled_for)
    later = repo.create_job_run(job.job_id, scheduled_for + timedelta(days=1), status="cancelled")
    assert later.status == "cancelled"
    disabled = repo.set_job_enabled(job.job_id, False)
    assert disabled.enabled is False
    with pytest.raises(JobDisabledError):
        repo.create_job_run(job.job_id, scheduled_for + timedelta(days=2))
    assert repo.get_job_definition(job.job_id) is not None


def test_v1_template_is_locked_to_douyin_ops(repo):
    user, _instance = _user_and_instance(repo)
    with pytest.raises(UnsupportedTemplateError):
        repo.create_agent_instance(user.user_id, "助手C", template_code="personal_assistant")


def test_knowledge_seed_writes_sql_first_and_keeps_instance_on_store_failure(repo):
    user, instance = _user_and_instance(repo)
    docs = repo.seed_knowledge_documents(
        user.user_id,
        instance.agent_instance_id,
        [
            KnowledgeSeed(
                title="demo",
                filename="intro.md",
                storage_uri="knowledge/douyin_ops_demo/intro.md",
            )
        ],
        write_store=lambda _doc: (_ for _ in ()).throw(RuntimeError("store down")),
    )
    assert repo.get_agent_instance(instance.agent_instance_id) is not None
    assert docs[0].status == "failed"
    ready = repo.seed_knowledge_documents(
        user.user_id,
        instance.agent_instance_id,
        [
            KnowledgeSeed(
                title="ok",
                filename="ok.md",
                storage_uri="knowledge/douyin_ops_demo/ok.md",
            )
        ],
        write_store=lambda _doc: None,
    )
    assert ready[0].status == "ready"


def test_trimmed_title_is_stored(repo):
    user = repo.create_user("carol", "hash-not-secret")
    instance = repo.create_agent_instance(user.user_id, "  助手D  ")
    assert instance.title == "助手D"


def test_media_asset_requires_owned_instance(repo):
    user, instance = _user_and_instance(repo, "media-owner")
    record = repo.add_media_asset(
        user.user_id,
        instance.agent_instance_id,
        kind="image",
        storage_uri=f"{user.user_id}/{instance.agent_instance_id}/images/demo.png",
        thread_id="thread-1",
    )
    assert record.kind == "image"
    assert repo.list_media_assets(instance.agent_instance_id)[0].asset_id == record.asset_id
    other = repo.create_user("dave", "hash-not-secret")
    with pytest.raises(NotFoundError):
        repo.add_media_asset(other.user_id, instance.agent_instance_id, kind="video", storage_uri="x")
    with pytest.raises(NotFoundError):
        repo.add_media_asset(user.user_id, uuid4(), kind="image", storage_uri="x")

def test_workflow_run_and_engage_projection(repo):
    user, instance = _user_and_instance(repo, "wf-owner")
    account = repo.upsert_douyin_account(
        user.user_id,
        instance.agent_instance_id,
        "shop1",
        display_name="店铺一",
        status="active",
    )
    assert repo.get_douyin_account(user.user_id, instance.agent_instance_id, "shop1").account_id == account.account_id
    run = repo.create_workflow_run(
        user.user_id,
        instance.agent_instance_id,
        workflow_code=DEFAULT_WORKFLOW_CODE,
        inputs={"account": "shop1", "no_send": False},
        status="running",
    )
    updated = repo.update_workflow_run(
        run.id,
        status="succeeded",
        outputs={"list_comment": []},
        workflow_run_id="wf-1",
    )
    assert updated.status == "succeeded"
    listed = repo.list_workflow_runs(user.user_id, instance.agent_instance_id, status="succeeded")
    assert listed[0].id == run.id
    video = repo.add_engage_video(
        user.user_id,
        instance.agent_instance_id,
        platform_video_id="v1",
        status="discovered",
        keyword="敏感肌",
        workflow_run_id="wf-1",
    )
    comment = repo.add_engage_comment(
        user.user_id,
        instance.agent_instance_id,
        platform_comment_id="c1",
        video_id="v1",
        status="sent",
        source_text="想买",
    )
    dm = repo.add_engage_dm(
        user.user_id,
        instance.agent_instance_id,
        platform_message_id="m1",
        video_id="v1",
        status="sent",
        source_text="多少钱",
    )
    assert repo.list_engage_videos(user.user_id, instance.agent_instance_id)[0].id == video.id
    assert repo.list_engage_comments(user.user_id, instance.agent_instance_id)[0].id == comment.id
    assert repo.list_engage_dms(user.user_id, instance.agent_instance_id)[0].id == dm.id
