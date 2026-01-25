from __future__ import annotations

import logging
import threading
import uuid
from typing import List, Tuple

import gradio as gr
from langchain_core.messages import AIMessage, HumanMessage

from app.config import settings
from app.graph import app
from app.rag import rules_rag


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


def _ensure_thread_id(thread_id: str | None) -> str:
    if thread_id:
        return thread_id
    return f"thread-{uuid.uuid4().hex}"


def _load_chat(thread_id: str | None) -> Tuple[List[dict[str, str]], str]:
    thread_id = _ensure_thread_id(thread_id)
    history: list[dict[str, str]] = []
    try:
        state = app.get_state({"configurable": {"thread_id": thread_id}})
        messages = state.values.get("messages", []) if state else []
        for message in messages:
            if isinstance(message, HumanMessage):
                history.append({"role": "user", "content": message.content})
            elif isinstance(message, AIMessage):
                history.append({"role": "assistant", "content": message.content})
    except Exception:
        pass
    return history, thread_id


def _chat(message: str, history: list[dict[str, str]], thread_id: str | None):
    thread_id = _ensure_thread_id(thread_id)
    result = app.invoke(
        {"messages": [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    ai_msg = result["messages"][-1]
    content = ai_msg.content if isinstance(ai_msg, AIMessage) else str(ai_msg)
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": content},
    ]
    return "", history, thread_id


def _new_chat():
    thread_id = _ensure_thread_id(None)
    return [], thread_id


def build_ui() -> gr.Blocks:
    with gr.Blocks(title=settings.app_title) as demo:
        gr.Markdown("""# Rental Agent - 基于 LangGraph 的订单/规则助手。""")
        browser_state = gr.BrowserState(storage_key="rental_thread_id")
        chatbot = gr.Chatbot(label="对话")
        msg = gr.Textbox(label="输入", placeholder="输入问题或订单指令")
        send = gr.Button("发送")
        new_chat = gr.Button("新对话")

        demo.load(_load_chat, inputs=browser_state, outputs=[chatbot, browser_state])
        msg.submit(_chat, inputs=[msg, chatbot, browser_state], outputs=[msg, chatbot, browser_state])
        send.click(_chat, inputs=[msg, chatbot, browser_state], outputs=[msg, chatbot, browser_state])
        new_chat.click(_new_chat, outputs=[chatbot, browser_state])

    return demo


def main() -> None:
    # Warm up RAG in background; tools can short-circuit if not ready yet.
    threading.Thread(target=lambda: rules_rag.error, daemon=True).start()
    ui = build_ui()
    ui.queue()
    ui.launch(server_name=settings.app_host,
              server_port=settings.app_port,
              debug=True,
              show_error=True,
              theme=gr.themes.Citrus()
              )


if __name__ == "__main__":
    main()
