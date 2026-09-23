from __future__ import annotations

from pathlib import Path

from ui.view_model import (
    absolute_media_url,
    auth_gate,
    build_chat_view,
    create_instance_payload,
    interrupt_card,
    plaza_cards,
    sidebar_view,
    with_pending_user,
)


def test_absolute_media_url_joins_api_base():
    url = absolute_media_url(
        "http://127.0.0.1:8000",
        "/v1/media/images/demo.png",
    )
    assert url == "http://127.0.0.1:8000/v1/media/images/demo.png"


def test_view_model_maps_media_to_image_and_video_widgets():
    thread = {
        "status": "idle",
        "interrupt": None,
        "messages": [
            {"role": "user", "content": "请配图和视频", "media": []},
            {
                "role": "assistant",
                "content": "已生成",
                "media": [
                    {"type": "image", "url": "/v1/media/images/a.png"},
                    {"type": "video", "url": "/v1/media/videos/b.mp4"},
                ],
            },
        ],
    }
    view = build_chat_view(thread, "http://127.0.0.1:8000")
    assert view["chat_input_enabled"] is True
    assistant = view["messages"][1]
    assert assistant["previews"][0] == {
        "widget": "image",
        "url": "http://127.0.0.1:8000/v1/media/images/a.png",
    }
    assert assistant["previews"][1] == {
        "widget": "video",
        "url": "http://127.0.0.1:8000/v1/media/videos/b.mp4",
    }


def test_interrupt_disables_chat_input_and_keeps_card_out_of_history():
    thread = {
        "status": "interrupted",
        "interrupt": {
            "type": "review_media",
            "tool": "generate_image",
            "prompt": "bottle",
            "params": {"quality": "low"},
        },
        "messages": [{"role": "user", "content": "配图", "media": []}],
    }
    view = build_chat_view(thread, "http://127.0.0.1:8000")
    assert view["chat_input_enabled"] is False
    card = interrupt_card(view)
    assert card["visible"] is True
    assert card["prompt"] == "bottle"
    assert all("Approve" not in (item["content"] or "") for item in view["messages"])


def test_streamlit_app_uses_preview_widgets():
    text = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    assert "st.image(preview[\"url\"])" in text or "st.image(" in text
    assert "st.video(" in text
    assert "st.chat_input" in text
    assert "disabled=not view[\"chat_input_enabled\"]" in text or "disabled=" in text


def test_pending_user_is_echoed_before_api_returns():
    messages = [{"role": "assistant", "content": "卖点是什么？", "previews": []}]
    view = with_pending_user(messages, "主要卖点是敏感肌")
    assert view[-1] == {
        "role": "user",
        "content": "主要卖点是敏感肌",
        "previews": [],
    }


def test_pending_user_does_not_duplicate_existing_bubble():
    messages = [{"role": "user", "content": "主要卖点是敏感肌", "previews": []}]
    view = with_pending_user(messages, "主要卖点是敏感肌")
    assert view == messages


def test_streamlit_app_echoes_pending_user():
    text = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    assert "pending_user" in text
    assert "with_pending_user" in text
    assert "正在回复" in text


def test_plaza_cards_expose_required_fields():
    cards = plaza_cards(
        [
            {
                "agent_instance_id": "id-1",
                "title": "助手A",
                "intro": "日常运营",
                "avatar_url": "/v1/agent-instances/id-1/avatar",
                "agent_mode": "single",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-02T00:00:00",
            }
        ]
    )
    card = cards[0]
    assert card["title"] == "助手A"
    assert card["intro"] == "日常运营"
    assert card["avatar_url"] == "/v1/agent-instances/id-1/avatar"
    assert card["agent_mode"] == "single"
    assert card["agent_mode_label"] == "单智能体模式"
    assert card["created_at"] == "2026-01-01T00:00:00"
    assert card["updated_at"] == "2026-01-02T00:00:00"


def test_sidebar_view_is_readonly_and_omits_model():
    view = sidebar_view(
        {
            "title": "助手A",
            "intro": "卡片简介",
            "capability_description": "规划抖音运营并触达线索",
            "development_notes": "能力只展示不勾选",
            "agent_mode": "single",
            "agent_mode_label": "单智能体模式",
            "knowledge_documents": [{"title": "faq", "filename": "faq.md"}],
            "workflows": [
                {
                    "code": "douyin-lead-discovery",
                    "display_name": "抖音线索发现与触达",
                }
            ],
            "tools": [
                {
                    "name": "discover_douyin_leads",
                    "display_name": "抖音线索发现",
                    "user_facing_summary": "扫描并真实发送评论或私信",
                }
            ],
            "model": "should-not-appear",
        }
    )
    assert view["readonly"] is True
    assert "model" not in view
    assert view["capability_description"] == "规划抖音运营并触达线索"
    assert view["development_notes"] == "能力只展示不勾选"
    assert view["agent_mode_label"] == "单智能体模式"
    assert view["knowledge_documents"][0]["filename"] == "faq.md"
    assert view["workflows"][0]["code"] == "douyin-lead-discovery"
    assert view["tools"][0]["name"] == "discover_douyin_leads"


def test_create_instance_payload_locks_douyin_ops_template():
    payload = create_instance_payload("助手A", "简介", "YmFzZTY0")
    assert payload["template_code"] == "douyin_ops"
    assert payload["title"] == "助手A"
    assert payload["intro"] == "简介"
    assert payload["avatar"] == "YmFzZTY0"
    assert set(payload) <= {"template_code", "title", "intro", "avatar"}


def test_auth_gate_has_no_thread_before_login():
    gate = auth_gate(
        {
            "thread_id": "thread-1",
            "agent_instance_id": "agent-1",
            "page": "chat",
        }
    )
    assert gate["authenticated"] is False
    assert gate["page"] == "login"
    assert gate["thread_id"] is None
    assert gate["agent_instance_id"] is None


def test_auth_gate_allows_thread_only_after_login_and_open():
    after_login = auth_gate({"token": "abc", "page": "plaza"})
    assert after_login["authenticated"] is True
    assert after_login["page"] == "plaza"
    assert after_login["thread_id"] is None
    opened = auth_gate(
        {
            "token": "abc",
            "page": "chat",
            "thread_id": "thread-1",
            "agent_instance_id": "agent-1",
        }
    )
    assert opened["authenticated"] is True
    assert opened["page"] == "chat"
    assert opened["thread_id"] == "thread-1"


def test_streamlit_app_uses_login_plaza_and_sidebar_http():
    text = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    assert 'st.title("抖音运营助手")' in text
    assert "/v1/auth/login" in text
    assert "/v1/auth/register" in text
    assert "/v1/agent-instances" in text
    assert "/open" in text
    assert "/sidebar" in text
    assert "Authorization" in text
    assert "Bearer" in text
    assert "create_instance_payload" in text
    assert "plaza_cards" in text
    assert "sidebar_view" in text
    assert "auth_gate" in text
    assert "st.session_state" in text
    assert 'post("/v1/threads")' not in text
    assert "POST /v1/threads" not in text
    assert "app.repository" not in text
    assert "InMemoryBusinessRepository" not in text
    assert "PostgresStore" not in text
    assert "DIFY_API_KEY" not in text
    assert "dify_api_key" not in text
    assert "from app." not in text


def test_streamlit_and_view_model_do_not_render_secrets():
    app = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    view = Path("ui/view_model.py").read_text(encoding="utf-8")
    combined = app + view
    for secret in ("DIFY_API_KEY", "dify_api_key", "SMTP_PASSWORD", "password_hash"):
        assert secret not in combined
