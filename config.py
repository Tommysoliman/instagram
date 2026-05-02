"""Configuration loaded from .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    openai_model: str
    embedding_model: str
    chroma_dir: str
    niche: str
    voice: str
    trend_subreddits: list[str]
    instagram_username: str = ""
    instagram_password: str = ""


def load_config() -> Config:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in.")

    subs_raw = os.getenv("TREND_SUBREDDITS", "memes,dankmemes")
    subs = [s.strip() for s in subs_raw.split(",") if s.strip()]

    return Config(
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        chroma_dir=os.getenv("CHROMA_DIR", "./data/chroma"),
        niche=os.getenv("MEME_NICHE", "general humor"),
        voice=os.getenv("MEME_VOICE", "casual, relatable, dry humor"),
        trend_subreddits=subs,
        instagram_username=os.getenv("INSTAGRAM_USERNAME", ""),
        instagram_password=os.getenv("INSTAGRAM_PASSWORD", ""),
    )
