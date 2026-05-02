"""
LangGraph workflow that wires the agents together.

Flow:
    scout_trends  →  generate_ideas  →  human_approve  →  write_captions  →  END

The human_approve node interrupts execution. You review the ideas in the CLI,
mark which to keep, and the graph resumes with only those.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from config import Config
from memory import MemeMemory
from agents import (
    MemeIdea,
    CaptionPackage,
    trend_scout,
    idea_generator,
    caption_writer,
)


# ----------------------------------------------------------------------------
# Shared state — passed between every node
# ----------------------------------------------------------------------------
class MemeState(TypedDict, total=False):
    trends: list[str]
    ideas: list[MemeIdea]
    approved_ideas: list[MemeIdea]
    captions: list[tuple[MemeIdea, CaptionPackage]]


# ----------------------------------------------------------------------------
# Nodes
# ----------------------------------------------------------------------------
def make_scout_node(cfg: Config, mem: MemeMemory):
    def node(state: MemeState) -> MemeState:
        trends = trend_scout(cfg, mem)
        return {"trends": trends}
    return node


def make_idea_node(cfg: Config, mem: MemeMemory, n_ideas: int = 5):
    def node(state: MemeState) -> MemeState:
        ideas = idea_generator(cfg, mem, state.get("trends", []), n_ideas=n_ideas)
        return {"ideas": ideas}
    return node


def human_approval_node(state: MemeState) -> MemeState:
    """LangGraph will interrupt before this runs (see compile() below)."""
    # When the graph resumes, `approved_ideas` is set externally before resume.
    # If somehow we got here without approvals, default to empty.
    return {"approved_ideas": state.get("approved_ideas", [])}


def make_caption_node(cfg: Config):
    def node(state: MemeState) -> MemeState:
        approved = state.get("approved_ideas", [])
        if not approved:
            print("⚠️  No approved ideas. Skipping caption writing.")
            return {"captions": []}

        print(f"✍️  Caption Writer: writing for {len(approved)} approved idea(s)...")
        out: list[tuple[MemeIdea, CaptionPackage]] = []
        for idea in approved:
            cap = caption_writer(cfg, idea)
            out.append((idea, cap))
        print(f"  ✅ Wrote {len(out)} caption package(s)")
        return {"captions": out}
    return node


# ----------------------------------------------------------------------------
# Build & compile
# ----------------------------------------------------------------------------
def build_graph(cfg: Config, mem: MemeMemory, n_ideas: int = 5):
    g = StateGraph(MemeState)

    g.add_node("scout", make_scout_node(cfg, mem))
    g.add_node("ideate", make_idea_node(cfg, mem, n_ideas=n_ideas))
    g.add_node("approve", human_approval_node)
    g.add_node("captions", make_caption_node(cfg))

    g.set_entry_point("scout")
    g.add_edge("scout", "ideate")
    g.add_edge("ideate", "approve")
    g.add_edge("approve", "captions")
    g.add_edge("captions", END)

    # Interrupt BEFORE the approval node so we can collect human input
    return g.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["approve"],
    )
