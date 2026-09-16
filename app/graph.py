from __future__ import annotations

from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.prompts import SYSTEM_PROMPT


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    last_image_path: NotRequired[str | None]
    last_video_path: NotRequired[str | None]


def build_graph(*, llm, tools, checkpointer):
    def chatbot(state: AgentState) -> dict[str, Any]:
        bound = llm.bind_tools(tools, parallel_tool_calls=False)
        message = bound.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        )
        tool_calls = getattr(message, "tool_calls", None) or []
        # Tutorial 4: disable parallel tool calls so interrupt/resume does not rerun tools.
        assert len(tool_calls) <= 1
        return {"messages": [message]}

    builder = StateGraph(AgentState)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", ToolNode(tools, handle_tool_errors=False))
    builder.add_conditional_edges("chatbot", tools_condition)
    builder.add_edge("tools", "chatbot")
    builder.add_edge(START, "chatbot")
    return builder.compile(checkpointer=checkpointer)


def interrupt_payload(snapshot) -> dict[str, Any] | None:
    interrupts = list(getattr(snapshot, "interrupts", ()) or ())
    for task in getattr(snapshot, "tasks", ()) or ():
        interrupts.extend(getattr(task, "interrupts", ()) or ())
    for item in interrupts:
        value = getattr(item, "value", item)
        if isinstance(value, dict) and value.get("type") == "review_media":
            return value
    return None
