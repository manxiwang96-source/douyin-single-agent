from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
import streamlit as st

from ui.view_model import build_chat_view, interrupt_card

API_BASE = os.environ.get("STREAMLIT_API_BASE", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="Xiaohongshu Ops Assistant", layout="centered")


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=180.0)


def ensure_thread(client: httpx.Client) -> str:
    if "thread_id" not in st.session_state:
        created = client.post("/v1/threads")
        created.raise_for_status()
        st.session_state.thread_id = created.json()["id"]
    return st.session_state.thread_id


def load_thread(client: httpx.Client, thread_id: str) -> dict:
    response = client.get(f"/v1/threads/{thread_id}")
    response.raise_for_status()
    return response.json()


def main() -> None:
    client = _client()
    thread_id = ensure_thread(client)
    try:
        thread = load_thread(client, thread_id)
    except httpx.HTTPError:
        st.session_state.pop("thread_id", None)
        thread_id = ensure_thread(client)
        thread = load_thread(client, thread_id)

    view = build_chat_view(thread, API_BASE)
    st.title("小红书运营助手")
    card = interrupt_card(view)
    if card["visible"]:
        st.info("生成前需要人工审核。审核完成前不能继续发消息。")
        prompt = st.text_area("Prompt", value=card["prompt"], key="hitl_prompt")
        params_raw = st.text_area(
            "Params JSON",
            value=json.dumps(card["params"], ensure_ascii=False, indent=2),
            key="hitl_params",
        )
        approve_col, skip_col = st.columns(2)
        if approve_col.button("Approve"):
            try:
                params = json.loads(params_raw or "{}")
            except json.JSONDecodeError:
                params = card["params"]
            client.post(
                f"/v1/threads/{thread_id}/resume",
                json={"action": "approve", "prompt": prompt, "params": params},
            ).raise_for_status()
            st.rerun()
        if skip_col.button("Skip"):
            client.post(
                f"/v1/threads/{thread_id}/resume",
                json={"action": "skip", "prompt": prompt, "params": {}},
            ).raise_for_status()
            st.rerun()

    for message in view["messages"]:
        with st.chat_message(message["role"]):
            if message["content"]:
                st.markdown(message["content"])
            for preview in message["previews"]:
                if preview["widget"] == "image":
                    st.image(preview["url"])
                elif preview["widget"] == "video":
                    st.video(preview["url"])

    user_text = st.chat_input(
        "输入产品信息或改稿需求",
        disabled=not view["chat_input_enabled"],
    )
    if user_text:
        client.post(
            f"/v1/threads/{thread_id}/messages",
            json={"content": user_text},
        ).raise_for_status()
        st.rerun()


main()
