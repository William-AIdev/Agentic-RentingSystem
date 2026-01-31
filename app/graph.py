from __future__ import annotations

import os
from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.config import settings
from app.graph_tools import TOOLS


def _configure_langsmith_tracing() -> None:
    if not os.getenv("LANGSMITH_API_KEY"):
        return
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", os.getenv("LANGSMITH_PROJECT", "rental-agent"))


_configure_langsmith_tracing()


llm = init_chat_model(
    model=settings.openai_model,
    temperature=settings.openai_temperature,
    streaming=True,
).bind_tools(TOOLS)


def agent_node(state: MessagesState) -> dict[str, Any]:
    messages = cast(list[BaseMessage], state["messages"])
    system_messages: list[BaseMessage] = [SystemMessage(content=settings.SYSTEM_PROMPT)]
    response = llm.invoke(system_messages + messages)
    return {"messages": [response]}


tool_node = ToolNode(TOOLS)


graph = StateGraph(MessagesState)

graph.add_node("agent", agent_node)

graph.add_node("tools", tool_node)

graph.set_entry_point("agent")

graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", "__end__": "__end__"})

graph.add_edge("tools", "agent")


checkpointer = MemorySaver()


app = graph.compile(checkpointer=checkpointer)
