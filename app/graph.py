from __future__ import annotations

from typing import Any, Dict

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.config import settings
from app.tools import TOOLS


SYSTEM_PROMPT = (
    "你是衣物租赁助手。\n"
    "- 用户问流程/规则/押金/清洗/尺码等解释性问题时，优先调用 rag_rules_tool。\n"
    "- 用户创建/更新/取消/查询订单等操作时，必须调用相应订单工具。\n"
    "- 如果缺少必要字段（例如订单号、时间、SKU 等），先追问补齐。"
)


llm = init_chat_model(
    model=settings.openai_model,
    temperature=settings.openai_temperature,
).bind_tools(TOOLS)


def agent_node(state: MessagesState) -> Dict[str, Any]:
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])
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
