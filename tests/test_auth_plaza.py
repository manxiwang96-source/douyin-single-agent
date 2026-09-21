from __future__ import annotations

import base64
import json

from uuid import UUID

from app.auth import PBKDF2_SCHEME, hash_password
from tests.fakes import TINY_PNG
from tests.http_helpers import create_and_open, make_client, register_and_login


def test_unauthenticated_business_routes_are_401(runtime):
    client = make_client(runtime)
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/agent-instances").status_code == 401
    assert client.post("/v1/threads").status_code == 401
    assert client.get("/v1/media/images/demo.png").status_code == 401
    assert client.post("/v1/assistant/jobs/run", json={"kind": "morning_brief"}).status_code == 401


def test_register_login_me_logout(runtime):
    client = make_client(runtime)
    body = register_and_login(client)
    me = client.get("/v1/me")
    assert me.status_code == 200
    assert me.json()["login_name"] == "alice"
    assert me.json()["user_id"] == body["user_id"]
    hashed = runtime.business_repo.get_user_by_login_name("alice").password_hash
    assert hashed.startswith(PBKDF2_SCHEME + "$")
    assert "password123" not in hashed
    logout = client.post("/v1/auth/logout")
    assert logout.status_code == 200
    assert client.get("/v1/me").status_code == 401


def test_duplicate_login_and_short_password(runtime):
    client = make_client(runtime)
    first = client.post("/v1/auth/register", json={"login_name": "alice", "password": "password123"})
    assert first.status_code == 201
    dup = client.post("/v1/auth/register", json={"login_name": "alice", "password": "password123"})
    assert dup.status_code == 409
    short = client.post("/v1/auth/register", json={"login_name": "bob", "password": "short"})
    assert short.status_code == 400


def test_wrong_password_is_401(runtime):
    client = make_client(runtime)
    client.post("/v1/auth/register", json={"login_name": "alice", "password": "password123"})
    response = client.post("/v1/auth/login", json={"login_name": "alice", "password": "wrongpass"})
    assert response.status_code == 401


def test_disabled_user_cannot_login(runtime):
    client = make_client(runtime)
    user = runtime.business_repo.create_user(
        "paused",
        hash_password("password123"),
        status="disabled",
    )
    assert user.status == "disabled"
    response = client.post("/v1/auth/login", json={"login_name": "paused", "password": "password123"})
    assert response.status_code == 403


def test_legacy_create_thread_is_not_product_entry(runtime):
    client = make_client(runtime)
    register_and_login(client)
    response = client.post("/v1/threads")
    assert response.status_code == 400


def test_one_user_multiple_instances_and_title_rules(runtime):
    client = make_client(runtime)
    register_and_login(client)
    first = client.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "agent-a", "intro": "one"},
    )
    assert first.status_code == 201
    second = client.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "agent-b", "intro": "two"},
    )
    assert second.status_code == 201
    blank = client.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "   ", "intro": "x"},
    )
    assert blank.status_code == 400
    space = client.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "agent a", "intro": "x"},
    )
    assert space.status_code == 400
    dup = client.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "Agent-A", "intro": "x"},
    )
    assert dup.status_code == 409
    listed = client.get("/v1/agent-instances")
    assert listed.status_code == 200
    titles = [item["title"] for item in listed.json()["items"]]
    assert titles == ["agent-a", "agent-b"]
    assert all("created_at" in item and "updated_at" in item for item in listed.json()["items"])
    assert all(item["agent_mode"] == "single" for item in listed.json()["items"])


def test_open_does_not_change_updated_at_and_reuses_thread(runtime):
    client = make_client(runtime)
    register_and_login(client)
    created = create_and_open(client, title="agent-open")
    updated_at = created["updated_at"]
    thread_id = created["thread_id"]
    again = client.post(f"/v1/agent-instances/{created['agent_instance_id']}/open")
    assert again.status_code == 200
    assert again.json()["thread_id"] == thread_id
    card = client.get("/v1/agent-instances").json()["items"][0]
    assert card["updated_at"] == updated_at


def test_create_binds_workflow_and_seeds_demo_docs(runtime):
    client = make_client(runtime)
    register_and_login(client)
    created = client.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "agent-seed", "intro": "demo"},
    )
    assert created.status_code == 201
    instance_id = created.json()["agent_instance_id"]
    sidebar = client.get(f"/v1/agent-instances/{instance_id}/sidebar")
    assert sidebar.status_code == 200
    body = sidebar.json()
    dumped = json.dumps(body)
    assert "DIFY_API_KEY" not in dumped
    assert runtime.settings.dify_api_key == "" or runtime.settings.dify_api_key not in dumped
    assert "app-" not in dumped
    assert body["agent_mode"] == "single"
    assert "capability_description" in body
    assert "development_notes" in body
    assert "model" not in body
    codes = [item["code"] for item in body["workflows"]]
    assert "douyin-lead-discovery" in codes
    names = [item["name"] for item in body["tools"]]
    assert "discover_douyin_leads" in names
    filenames = {item["filename"] for item in body["knowledge_documents"]}
    assert "compliance-boundary.md" in filenames
    assert "comment-dm-scripts.md" in filenames
    assert "when-to-send.md" in filenames
    assert "faq.md" in filenames
    assert all(item["source"] == "seeded_demo" for item in body["knowledge_documents"])
    bindings = runtime.business_repo.list_workflow_bindings(UUID(created.json()["agent_instance_id"]))
    assert [item.workflow_code for item in bindings] == ["douyin-lead-discovery"]


def test_patch_title_updates_updated_at(runtime):
    client = make_client(runtime)
    register_and_login(client)
    created = client.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "agent-old", "intro": "a"},
    )
    instance_id = created.json()["agent_instance_id"]
    before = created.json()["updated_at"]
    patched = client.patch(
        f"/v1/agent-instances/{instance_id}",
        json={"title": "agent-new"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "agent-new"
    assert patched.json()["updated_at"] != before


def test_avatar_persists_outside_media_assets(runtime):
    client = make_client(runtime)
    register_and_login(client)
    avatar = base64.b64encode(TINY_PNG).decode("ascii")
    created = client.post(
        "/v1/agent-instances",
        json={
            "template_code": "douyin_ops",
            "title": "agent-avatar",
            "intro": "pic",
            "avatar": avatar,
        },
    )
    assert created.status_code == 201
    assert created.json()["avatar_uri"].startswith("avatars/")
    image = client.get(created.json()["avatar_url"])
    assert image.status_code == 200
    assert image.content == TINY_PNG
    assert runtime.media_root.name == "outputs" or "outputs" in str(runtime.media_root)


def test_other_user_cannot_see_instance(runtime):
    alice = make_client(runtime)
    register_and_login(alice, login_name="alice")
    created = alice.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "alice-bot", "intro": "x"},
    )
    instance_id = created.json()["agent_instance_id"]
    bob = make_client(runtime)
    register_and_login(bob, login_name="bob")
    assert bob.get("/v1/agent-instances").json()["items"] == []
    assert bob.get(f"/v1/agent-instances/{instance_id}/sidebar").status_code == 404
    assert bob.post(f"/v1/agent-instances/{instance_id}/open").status_code == 404
