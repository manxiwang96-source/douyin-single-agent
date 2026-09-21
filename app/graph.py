from __future__ import annotations

from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_config, get_store
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.utils.runnable import RunnableCallable

from app.prompts import SYSTEM_PROMPT

DEFAULT_ALLOWED_WORKFLOW_CODES = ["douyin-lead-discovery"]
SCHEDULER_USER_ID = "00000000-0000-4000-8000-000000000001"
SCHEDULER_AGENT_INSTANCE_ID = "00000000-0000-4000-8000-000000000002"


def build_invoke_config(
    *,
    thread_id: str,
    user_id,
    agent_instance_id,
    allowed_workflow_codes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": str(thread_id),
            "user_id": str(user_id),
            "agent_instance_id": str(agent_instance_id),
            "allowed_workflow_codes": list(
                allowed_workflow_codes
                if allowed_workflow_codes is not None
                else DEFAULT_ALLOWED_WORKFLOW_CODES
            ),
        }
    }


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    last_image_path: NotRequired[str | None]
    last_video_path: NotRequired[str | None]


def _message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text") or "")
        return "".join(parts)
    return str(content or "")


def _configurable(config: RunnableConfig | None) -> dict[str, Any]:
    if not config:
        try:
            config = get_config()
        except Exception:
            return {}
    return dict((config or {}).get("configurable") or {})


def _retrieve_instance_knowledge(state: AgentState, config: RunnableConfig | None) -> str:
    messages = state.get("messages") or []
    if messages and isinstance(messages[-1], ToolMessage):
        return ""
    configurable = _configurable(config)
    user_id = configurable.get("user_id")
    agent_instance_id = configurable.get("agent_instance_id")
    if not user_id or not agent_instance_id:
        return ""
    try:
        store = get_store()
    except Exception:
        store = None
    if store is None:
        return ""
    query = ""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            query = _message_text(message).strip()
            break
    if not query:
        return ""
    namespace = (str(user_id), str(agent_instance_id), "kb")
    try:
        hits = store.search(namespace, query=query, limit=4)
    except Exception:
        return ""
    texts: list[str] = []
    for hit in hits or []:
        score = getattr(hit, "score", None)
        if score is not None and score <= 0:
            continue
        value = getattr(hit, "value", None) or {}
        text = value.get("text")
        if text:
            texts.append(str(text))
    return "\n\n".join(texts)


def build_graph(*, llm, tools, checkpointer, store=None):
    def _chat_payload(state: AgentState, config: RunnableConfig | None = None):
        bound = llm.bind_tools(tools, parallel_tool_calls=False)
        payload = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        retrieved = _retrieve_instance_knowledge(state, config)
        if retrieved:
            payload = [
                payload[0],
                SystemMessage(content="Use the following instance knowledge if relevant:\n" + retrieved),
                *payload[1:],
            ]
        return bound, payload

    def _chat_result(message):
        tool_calls = getattr(message, "tool_calls", None) or []
        # Tutorial 4: disable parallel tool calls so interrupt/resume does not rerun tools.
        assert len(tool_calls) <= 1
        return {"messages": [message]}

    def chatbot(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        bound, payload = _chat_payload(state, config)
        return _chat_result(bound.invoke(payload))

    async def achatbot(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        bound, payload = _chat_payload(state, config)
        return _chat_result(await bound.ainvoke(payload))

    builder = StateGraph(AgentState)
    builder.add_node("chatbot", RunnableCallable(chatbot, achatbot, name="chatbot"))
    builder.add_node("tools", ToolNode(tools, handle_tool_errors=False))
    builder.add_conditional_edges("chatbot", tools_condition)
    builder.add_edge("tools", "chatbot")
    builder.add_edge(START, "chatbot")
    return builder.compile(checkpointer=checkpointer, store=store)


def interrupt_payload(snapshot) -> dict[str, Any] | None:
    interrupts = list(getattr(snapshot, "interrupts", ()) or ())
    for task in getattr(snapshot, "tasks", ()) or ():
        interrupts.extend(getattr(task, "interrupts", ()) or ())
    for item in interrupts:
        value = getattr(item, "value", item)
        if isinstance(value, dict) and value.get("type") == "review_media":
            return value
    return None
