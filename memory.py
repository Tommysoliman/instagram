"""
ChromaDB-backed memory for the meme system.

Stores three kinds of memories:
1. trends      — what's hot right now (short-lived, ~7 days relevance)
2. ideas       — meme concepts you've generated, with status (approved/rejected/posted)
3. performance — posted memes + their engagement (likes, saves, comments)

These give the idea-generation agent two kinds of context:
- "What's trending in my niche this week?"
- "What kinds of memes work for MY page?"

Both are retrieved by semantic similarity, not just recency.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Literal

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from config import Config


IdeaStatus = Literal["draft", "approved", "rejected", "posted"]


@dataclass
class StoredIdea:
    id: str
    text: str
    status: IdeaStatus
    score: float | None  # distance from query (lower = more similar)
    metadata: dict


class MemeMemory:
    """Three Chroma collections behind one API."""

    def __init__(self, cfg: Config) -> None:
        self.client = chromadb.PersistentClient(
            path=cfg.chroma_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        embedder = OpenAIEmbeddingFunction(
            api_key=cfg.openai_api_key,
            model_name=cfg.embedding_model,
        )

        self.trends = self.client.get_or_create_collection(
            name="trends", embedding_function=embedder
        )
        self.ideas = self.client.get_or_create_collection(
            name="ideas", embedding_function=embedder
        )
        self.performance = self.client.get_or_create_collection(
            name="performance", embedding_function=embedder
        )

    # ---------- TRENDS ----------
    def add_trend(self, text: str, source: str) -> str:
        tid = str(uuid.uuid4())
        self.trends.add(
            ids=[tid],
            documents=[text],
            metadatas=[{"source": source, "ts": time.time()}],
        )
        return tid

    def search_trends(self, query: str, k: int = 5) -> list[StoredIdea]:
        res = self.trends.query(query_texts=[query], n_results=k)
        return _to_stored(res)

    # ---------- IDEAS ----------
    def add_idea(self, text: str, status: IdeaStatus = "draft", **extra) -> str:
        iid = str(uuid.uuid4())
        meta = {"status": status, "ts": time.time(), **extra}
        self.ideas.add(ids=[iid], documents=[text], metadatas=[meta])
        return iid

    def update_idea_status(self, idea_id: str, status: IdeaStatus) -> None:
        self.ideas.update(ids=[idea_id], metadatas=[{"status": status}])

    def search_similar_ideas(self, query: str, k: int = 5) -> list[StoredIdea]:
        """Useful to avoid repeating yourself."""
        res = self.ideas.query(query_texts=[query], n_results=k)
        return _to_stored(res)

    # ---------- PERFORMANCE ----------
    def add_performance(
        self, idea_text: str, likes: int, saves: int, comments: int
    ) -> str:
        pid = str(uuid.uuid4())
        engagement_score = likes + (saves * 3) + (comments * 2)  # weighted
        self.performance.add(
            ids=[pid],
            documents=[idea_text],
            metadatas=[
                {
                    "likes": likes,
                    "saves": saves,
                    "comments": comments,
                    "engagement_score": engagement_score,
                    "ts": time.time(),
                }
            ],
        )
        return pid

    def search_top_performers(self, query: str, k: int = 5) -> list[StoredIdea]:
        """Find past memes similar to a query that performed well."""
        res = self.performance.query(query_texts=[query], n_results=k)
        return _to_stored(res)


def _to_stored(chroma_result: dict) -> list[StoredIdea]:
    """Convert Chroma's nested result dict into a flat list."""
    if not chroma_result["ids"] or not chroma_result["ids"][0]:
        return []

    ids = chroma_result["ids"][0]
    docs = chroma_result["documents"][0]
    metas = chroma_result["metadatas"][0]
    dists = chroma_result.get("distances", [[None] * len(ids)])[0]

    out: list[StoredIdea] = []
    for i, doc, meta, dist in zip(ids, docs, metas, dists):
        out.append(
            StoredIdea(
                id=i,
                text=doc,
                status=meta.get("status", "n/a"),
                score=dist,
                metadata=meta,
            )
        )
    return out
