"""Grafo del clasificador con LangGraph."""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import classify, format_reply, validate_input
from app.agent.state import AgentState


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("validate_input", validate_input)
    builder.add_node("classify", classify)
    builder.add_node("format_reply", format_reply)

    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "classify")
    builder.add_edge("classify", "format_reply")
    builder.add_edge("format_reply", END)
    return builder.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()
