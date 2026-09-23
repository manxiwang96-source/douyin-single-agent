from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
import streamlit as st

from ui.view_model import (
    auth_gate,
    build_chat_view,
    create_instance_payload,
    interrupt_card,
    plaza_cards,
    sidebar_view,
    with_pending_user,
)

API_BASE = os.environ.get("STREAMLIT_API_BASE", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="抖音运营助手", layout="wide")


def _client() -> httpx.Client:
    headers: dict[str, str] = {}
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API_BASE, timeout=180.0, headers=headers)


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail:
        return detail
    return response.text or f"HTTP {response.status_code}"


def _reset_session() -> None:
    for key in list(st.session_state.keys()):
        st.session_state.pop(key, None)


def _clear_chat() -> None:
    for key in ("thread_id", "agent_instance_id", "pending_user", "page"):
        st.session_state.pop(key, None)
    st.session_state.page = "plaza"


def _logout(client: httpx.Client) -> None:
    try:
        client.post("/v1/auth/logout")
    except httpx.HTTPError:
        pass
    _reset_session()


def _handle_auth_error(response: httpx.Response) -> bool:
    if response.status_code != 401:
        return False
    _reset_session()
    return True


def _fetch_bytes(client: httpx.Client, url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return None
    if _handle_auth_error(response):
        st.rerun()
    if response.status_code != 200:
        return None
    return response.content


def _already_shown(messages: list[dict], pending: str) -> bool:
    return any(
        item.get("role") == "user" and (item.get("content") or "") == pending
        for item in messages
    )


def _store_login(body: dict) -> None:
    st.session_state.token = body["token"]
    st.session_state.user_id = body.get("user_id")
    st.session_state.login_name = body.get("login_name")
    st.session_state.page = "plaza"
    st.session_state.pop("thread_id", None)
    st.session_state.pop("agent_instance_id", None)


def render_login() -> None:
    st.title("抖音运营助手")
    st.caption("登录后进入智能体广场，再点卡片开始对话。")
    tab_login, tab_register = st.tabs(["登录", "注册"])
    with tab_login:
        with st.form("login_form"):
            login_name = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")
        if submitted:
            try:
                response = httpx.post(
                    f"{API_BASE}/v1/auth/login",
                    json={"login_name": login_name, "password": password},
                    timeout=30.0,
                )
            except httpx.HTTPError:
                st.error("登录失败，请检查服务是否可用。")
            else:
                if response.status_code == 200:
                    _store_login(response.json())
                    st.rerun()
                else:
                    st.error(_detail(response))
    with tab_register:
        with st.form("register_form"):
            login_name = st.text_input("新账号")
            password = st.text_input("新密码", type="password")
            submitted = st.form_submit_button("注册并登录")
        if submitted:
            try:
                registered = httpx.post(
                    f"{API_BASE}/v1/auth/register",
                    json={"login_name": login_name, "password": password},
                    timeout=30.0,
                )
            except httpx.HTTPError:
                st.error("注册失败，请检查服务是否可用。")
            else:
                if registered.status_code not in {200, 201}:
                    st.error(_detail(registered))
                else:
                    login = httpx.post(
                        f"{API_BASE}/v1/auth/login",
                        json={"login_name": login_name, "password": password},
                        timeout=30.0,
                    )
                    if login.status_code == 200:
                        _store_login(login.json())
                        st.rerun()
                    else:
                        st.error(_detail(login))


def render_create_form(client: httpx.Client) -> None:
    st.subheader("新建智能体")
    st.caption("模板固定为抖音运营助手，不能改成别的模板。")
    with st.form("create_instance_form"):
        title = st.text_input("名称")
        intro = st.text_area("简介")
        avatar_file = st.file_uploader(
            "头像",
            type=["png", "jpg", "jpeg", "webp", "gif"],
        )
        created = st.form_submit_button("创建")
        cancelled = st.form_submit_button("取消")
    if cancelled:
        st.session_state.show_create = False
        st.rerun()
    if created:
        avatar = None
        if avatar_file is not None:
            avatar = base64.b64encode(avatar_file.getvalue()).decode("ascii")
        payload = create_instance_payload(title, intro, avatar)
        try:
            response = client.post("/v1/agent-instances", json=payload)
        except httpx.HTTPError:
            st.error("创建失败，请重试。")
            return
        if _handle_auth_error(response):
            st.rerun()
        if response.status_code in {200, 201}:
            st.session_state.show_create = False
            st.rerun()
        else:
            st.error(_detail(response))


def render_plaza(client: httpx.Client) -> None:
    header_left, header_mid, header_right = st.columns([4, 1, 1])
    with header_left:
        st.title("抖音运营助手")
        st.caption("选择一张广场卡片进入对话。点进对话不会改最近编辑时间。")
    with header_mid:
        if st.button("新建智能体"):
            st.session_state.show_create = True
    with header_right:
        if st.button("退出登录"):
            _logout(client)
            st.rerun()

    if st.session_state.get("show_create"):
        render_create_form(client)

    try:
        listed = client.get("/v1/agent-instances")
    except httpx.HTTPError:
        st.error("加载广场失败，请重试。")
        return
    if _handle_auth_error(listed):
        st.rerun()
    if listed.status_code != 200:
        st.error(_detail(listed))
        return
    cards = plaza_cards(listed.json().get("items") or [])
    if not cards:
        st.info("还没有智能体，先新建一个。")
        return
    for card in cards:
        with st.container(border=True):
            avatar_col, body_col = st.columns([1, 4])
            with avatar_col:
                image = _fetch_bytes(client, card.get("avatar_url"))
                if image:
                    st.image(image)
            with body_col:
                st.subheader(card["title"])
                if card["intro"]:
                    st.write(card["intro"])
                st.caption(
                    f"{card['agent_mode_label']} · 创建时间 {card['created_at'] or '-'} · 最近编辑 {card['updated_at'] or '-'}"
                )
                if st.button("进入对话", key=f"open-{card['agent_instance_id']}"):
                    try:
                        opened = client.post(
                            f"/v1/agent-instances/{card['agent_instance_id']}/open"
                        )
                    except httpx.HTTPError:
                        st.error("打开对话失败，请重试。")
                        continue
                    if _handle_auth_error(opened):
                        st.rerun()
                    if opened.status_code != 200:
                        st.error(_detail(opened))
                        continue
                    body = opened.json()
                    st.session_state.page = "chat"
                    st.session_state.agent_instance_id = body["agent_instance_id"]
                    st.session_state.thread_id = body["thread_id"]
                    st.session_state.pop("pending_user", None)
                    st.rerun()


def render_sidebar_panel(client: httpx.Client, agent_instance_id: str) -> None:
    try:
        response = client.get(f"/v1/agent-instances/{agent_instance_id}/sidebar")
    except httpx.HTTPError:
        st.error("加载侧边栏失败。")
        return
    if _handle_auth_error(response):
        st.rerun()
    if response.status_code != 200:
        st.error(_detail(response))
        return
    view = sidebar_view(response.json())
    st.markdown(f"### {view['title']}")
    st.markdown("**应用描述**")
    st.write(view["capability_description"])
    st.markdown("**应用开发要点**")
    st.write(view["development_notes"])
    st.markdown("**应用设置**")
    st.write(view["agent_mode_label"])
    st.caption("多智能体模式只展示，不能切换。")
    st.markdown("**知识库**")
    documents = view["knowledge_documents"]
    if documents:
        for item in documents:
            st.write(f"- {item.get('title') or item.get('filename')}")
    else:
        st.caption("暂无知识库文档")
    st.markdown("**工作流**")
    workflows = view["workflows"]
    if workflows:
        for item in workflows:
            st.write(f"- {item.get('display_name') or item.get('code')}")
    else:
        st.caption("暂无工作流")
    st.markdown("**工具**")
    tools = view["tools"]
    if tools:
        for item in tools:
            summary = item.get("user_facing_summary") or ""
            name = item.get("display_name") or item.get("name")
            st.write(f"- {name}：{summary}" if summary else f"- {name}")
    else:
        st.caption("暂无工具")


def render_chat(client: httpx.Client, thread_id: str, agent_instance_id: str) -> None:
    header_left, header_mid, header_right = st.columns([4, 1, 1])
    with header_left:
        st.title("抖音运营助手")
        st.caption("可规划抖音运营、配图/视频；评论和私信会真实发送。")
    with header_mid:
        if st.button("返回广场"):
            _clear_chat()
            st.rerun()
    with header_right:
        if st.button("退出登录"):
            _logout(client)
            st.rerun()

    chat_col, side_col = st.columns([3, 1])
    with side_col:
        render_sidebar_panel(client, agent_instance_id)

    with chat_col:
        try:
            loaded = client.get(f"/v1/threads/{thread_id}")
        except httpx.HTTPError:
            st.error("加载对话失败，请重试。")
            return
        if _handle_auth_error(loaded):
            st.rerun()
        if loaded.status_code != 200:
            st.error(_detail(loaded))
            return
        thread = loaded.json()
        view = build_chat_view(thread, API_BASE)
        pending = st.session_state.get("pending_user")
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

        for message in with_pending_user(view["messages"], pending):
            with st.chat_message(message["role"]):
                if message["content"]:
                    st.markdown(message["content"])
                for preview in message["previews"]:
                    data = _fetch_bytes(client, preview["url"])
                    if preview["widget"] == "image":
                        if data:
                            st.image(data)
                        else:
                            st.image(preview["url"])
                    elif preview["widget"] == "video":
                        if data:
                            st.video(data)
                        else:
                            st.video(preview["url"])

        sending = (
            bool(pending)
            and view["chat_input_enabled"]
            and not _already_shown(view["messages"], pending or "")
        )
        user_text = st.chat_input(
            "输入抖音运营问题、提醒或内容需求",
            disabled=not view["chat_input_enabled"] or sending,
        )
        if user_text:
            st.session_state.pending_user = user_text
            pending = user_text
            if not _already_shown(view["messages"], user_text):
                with st.chat_message("user"):
                    st.markdown(user_text)

        if pending and view["chat_input_enabled"]:
            if _already_shown(view["messages"], pending):
                st.session_state.pop("pending_user", None)
            else:
                try:
                    with st.spinner("正在回复..."):
                        posted = client.post(
                            f"/v1/threads/{thread_id}/messages",
                            json={"content": pending},
                        )
                    if _handle_auth_error(posted):
                        st.rerun()
                    posted.raise_for_status()
                except httpx.HTTPError:
                    st.error("发送失败，请重试。")
                else:
                    st.session_state.pop("pending_user", None)
                    st.rerun()


def main() -> None:
    gate = auth_gate(dict(st.session_state))
    if not gate["authenticated"]:
        render_login()
        return
    client = _client()
    if gate["page"] == "chat" and gate["thread_id"] and gate["agent_instance_id"]:
        render_chat(client, gate["thread_id"], gate["agent_instance_id"])
        return
    render_plaza(client)


main()
