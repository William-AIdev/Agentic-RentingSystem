from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, TypedDict

from langgraph.graph import END, StateGraph

from services import order_services as svc
from services.types import OrdersServiceError, Order


class AgentState(TypedDict, total=False):
    action: str
    args: Dict[str, Any]
    text: str
    result: Any
    error: str


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("start_at/end_at must be datetime or ISO string")


def _serialize_order(order: Order) -> Dict[str, Any]:
    return {
        "order_id": order.order_id,
        "user_name": order.user_name,
        "user_wechat": order.user_wechat,
        "sku": order.sku,
        "start_at": order.start_at.isoformat(),
        "end_at": order.end_at.isoformat(),
        "buffer_hours": order.buffer_hours,
        "status": order.status,
        "locker_code": order.locker_code,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def _serialize_result(value: Any) -> Any:
    if isinstance(value, Order):
        return _serialize_order(value)
    return value


def _parse_text_input(text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    cleaned = text.strip()
    if not cleaned:
        return None, {}
    if cleaned.startswith("{"):
        payload = json.loads(cleaned)
        action = payload.get("action")
        args = payload.get("args") or {}
        return action, args

    tokens = cleaned.split()
    cmd = tokens[0].lower()
    if cmd in {"get", "fetch"} and len(tokens) >= 2:
        return "get_order", {"order_id": tokens[1]}
    if cmd == "cancel" and len(tokens) >= 2:
        return "cancel_order", {"order_id": tokens[1]}
    if cmd in {"pay", "paid"} and len(tokens) >= 2:
        return "mark_paid", {"order_id": tokens[1]}
    if cmd == "deliver" and len(tokens) >= 3:
        return "deliver_order", {"order_id": tokens[1], "locker_code": tokens[2]}
    if cmd in {"finish", "done"} and len(tokens) >= 2:
        return "finish_order", {"order_id": tokens[1]}
    return None, {}


def _make_tools(client: Optional[Any]) -> Dict[str, Any]:
    def _create_order(args: Dict[str, Any]) -> Order:
        kwargs: Dict[str, Any] = {
            "order_id": args["order_id"],
            "user_name": args["user_name"],
            "user_wechat": args["user_wechat"],
            "sku": args["sku"],
            "start_at": _parse_datetime(args["start_at"]),
            "end_at": _parse_datetime(args["end_at"]),
            "client": client,
        }
        if "status" in args:
            kwargs["status"] = args["status"]
        if "buffer_hours" in args:
            kwargs["buffer_hours"] = args["buffer_hours"]
        if "locker_code" in args:
            kwargs["locker_code"] = args["locker_code"]
        return svc.add_order_to_db(**kwargs)

    def _get_order(args: Dict[str, Any]) -> Order:
        return svc.get_order_detail(args["order_id"], client=client)

    def _update_order(args: Dict[str, Any]) -> Order:
        return svc.edit_order_from_db(args["order_id"], patch=args.get("patch") or {}, client=client)

    def _cancel_order(args: Dict[str, Any]) -> Order:
        return svc.cancel_order(
            args["order_id"],
            client=client,
            hard_delete=bool(args.get("hard_delete", False)),
        )

    def _mark_paid(args: Dict[str, Any]) -> Order:
        return svc.mark_order_paid(args["order_id"], client=client)

    def _deliver_order(args: Dict[str, Any]) -> Order:
        return svc.deliver_order(args["order_id"], locker_code=args["locker_code"], client=client)

    def _finish_order(args: Dict[str, Any]) -> Order:
        return svc.finish_order(args["order_id"], client=client)

    return {
        "create_order": _create_order,
        "get_order": _get_order,
        "update_order": _update_order,
        "cancel_order": _cancel_order,
        "mark_paid": _mark_paid,
        "deliver_order": _deliver_order,
        "finish_order": _finish_order,
    }


def build_graph(*, client: Optional[Any] = None):
    tools = _make_tools(client)

    def dispatch(state: AgentState) -> AgentState:
        action = state.get("action")
        args = state.get("args") or {}
        if not action and state.get("text"):
            try:
                action, args = _parse_text_input(state["text"])
            except Exception as exc:
                return {**state, "error": f"Invalid text input: {exc}"}
        if not action:
            return {**state, "error": "Missing action. Provide action/args or text."}
        tool = tools.get(action)
        if not tool:
            return {**state, "error": f"Unknown action: {action}"}
        try:
            result = tool(args)
        except OrdersServiceError as exc:
            return {**state, "error": f"{exc.__class__.__name__}: {exc}"}
        except Exception as exc:
            return {**state, "error": f"UnhandledError: {exc}"}
        return {**state, "result": _serialize_result(result)}

    graph = StateGraph(AgentState)
    graph.add_node("dispatch", dispatch)
    graph.set_entry_point("dispatch")
    graph.add_edge("dispatch", END)
    return graph.compile()


def run_agent(*,
              action: Optional[str] = None,
              args: Optional[Dict[str, Any]] = None,
              text: Optional[str] = None,
              client: Optional[Any] = None
              ) -> AgentState:
    graph = build_graph(client=client)
    state: AgentState = {}
    if text:
        state["text"] = text
    else:
        state["action"] = action or ""
        state["args"] = args or {}
    return graph.invoke(state)
