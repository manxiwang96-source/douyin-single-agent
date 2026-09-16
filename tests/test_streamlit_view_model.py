from __future__ import annotations

from pathlib import Path

from ui.view_model import absolute_media_url, build_chat_view, interrupt_card, with_pending_user


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
