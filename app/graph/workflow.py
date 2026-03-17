"""
app/graph/workflow.py
LangGraph directed graph — the core orchestration engine.

Graph topology:
  START
    └── orchestrator_node          (plans, injects memory context)
          ├── news_node            ─┐
          ├── financial_node        ├─ fan-out (parallel via Send)
          └── document_node        ─┘
                └── aggregator_node   (fan-in, merges all outputs)
                      └── reviewer_node  (LLM structured thesis)
                            └── END

Conditional edge on reviewer_node:
  • passes validation → END
  • fails validation  → reviewer_node (retry, max 3)
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.logging import get_logger
from app.graph.nodes import (
    aggregator_node,
    document_node,
    financial_node,
    news_node,
    orchestrator_node,
    reviewer_node,
)
from app.schemas.models import AgentState

logger = get_logger(__name__)

_MAX_REVIEWER_RETRIES = 3


def _route_after_reviewer(state: AgentState) -> str:
    """
    Conditional edge: if reviewer produced a valid thesis, go to END.
    If validation failed and we haven't hit retry cap, loop back.
    """
    if state.get("thesis"):
        return END
    retries = state.get("reviewer_retries", 0)
    if retries >= _MAX_REVIEWER_RETRIES:
        logger.error(
            "reviewer_retry_cap_reached",
            session_id=state.get("session_id"),
            ticker=state.get("ticker"),
        )
        return END   # surface partial state rather than infinite loop
    return "reviewer_node"


def build_graph() -> StateGraph:
    """
    Construct and compile the LangGraph workflow.
    Returns a compiled graph ready for .ainvoke() / .astream().
    """
    builder = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    builder.add_node("orchestrator_node", orchestrator_node)
    builder.add_node("news_node", news_node)
    builder.add_node("financial_node", financial_node)
    builder.add_node("document_node", document_node)
    builder.add_node("aggregator_node", aggregator_node)
    builder.add_node("reviewer_node", reviewer_node)

    # ── Entry point ───────────────────────────────────────────────────────────
    builder.add_edge(START, "orchestrator_node")

    # ── Fan-out: orchestrator → all three research agents in parallel ─────────
    builder.add_edge("orchestrator_node", "news_node")
    builder.add_edge("orchestrator_node", "financial_node")
    builder.add_edge("orchestrator_node", "document_node")

    # ── Fan-in: all agents → aggregator ──────────────────────────────────────
    builder.add_edge("news_node", "aggregator_node")
    builder.add_edge("financial_node", "aggregator_node")
    builder.add_edge("document_node", "aggregator_node")

    # ── Aggregator → reviewer ─────────────────────────────────────────────────
    builder.add_edge("aggregator_node", "reviewer_node")

    # ── Conditional: reviewer → END or retry ─────────────────────────────────
    builder.add_conditional_edges(
        "reviewer_node",
        _route_after_reviewer,
        {END: END, "reviewer_node": "reviewer_node"},
    )

    graph = builder.compile()
    logger.info("langgraph_compiled", nodes=list(builder.nodes))
    return graph


# Module-level singleton — compiled once, reused across requests
_graph: StateGraph | None = None


def get_graph() -> StateGraph:
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
