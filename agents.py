"""
The three core agents.

Each agent is a pure function: takes structured input, calls the LLM with a
purpose-built system prompt, returns structured output. No frameworks needed
for the agents themselves — LangGraph just wires them together.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests as _requests
from openai import OpenAI

from config import Config
from memory import MemeMemory, StoredIdea
from reddit_scraper import fetch_trends_across


@dataclass
class MemeIdea:
    concept: str          # one-line meme concept
    format: str           # e.g. "image macro", "tweet screenshot", "two-panel comparison"
    why_it_works: str     # short rationale tied to niche/voice
    risk_flags: list[str] # things you might want to double-check (sensitive topics, etc.)


@dataclass
class CaptionPackage:
    caption: str
    hashtags: list[str]
    first_comment: str  # IG strategy: put extra hashtags here


# ============================================================================
# Agent 1: Trend Scout
# ============================================================================
def trend_scout(cfg: Config, memory: MemeMemory) -> list[str]:
    """
    Pulls top Reddit posts, asks the LLM to extract 'meme angles' relevant to
    your niche, and stores them in ChromaDB as trends.

    Returns the list of extracted trend angles.
    """
    print("🔍 Trend Scout: fetching from Reddit...")
    raw_posts = fetch_trends_across(cfg.trend_subreddits, limit_each=15)

    if not raw_posts:
        print("  No posts fetched. Returning empty trends.")
        return []

    # Pick top 30 by score
    top = raw_posts[:30]
    titles = "\n".join(f"- [{p['score']} pts] {p['title']}" for p in top)

    client = OpenAI(api_key=cfg.openai_api_key)
    system = f"""You are a trend scout for a meme Instagram page.
Niche: {cfg.niche}
Voice: {cfg.voice}

You'll receive top Reddit post titles. Extract 8-12 RELEVANT trend angles —
themes, jokes, formats, or cultural moments that could be adapted for the page.
Skip anything off-niche.

Respond as a JSON array of short strings, like:
["angle 1", "angle 2", ...]
Nothing else."""

    resp = client.chat.completions.create(
        model=cfg.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Top posts today:\n\n{titles}"},
        ],
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content or "{}"
    # Some models wrap arrays in {"trends": [...]}, handle both
    try:
        parsed = json.loads(content)
        trends = parsed if isinstance(parsed, list) else parsed.get("trends") or parsed.get("angles") or []
    except json.JSONDecodeError:
        trends = []

    # Persist into memory
    for t in trends:
        if isinstance(t, str) and t.strip():
            memory.add_trend(t, source="reddit")

    print(f"  ✅ Scouted {len(trends)} trend angles")
    return trends


# ============================================================================
# Agent 2: Idea Generator (RAG-flavored)
# ============================================================================
def idea_generator(
    cfg: Config, memory: MemeMemory, trends: list[str], n_ideas: int = 5
) -> list[MemeIdea]:
    """
    Generates n_ideas meme concepts, grounded in:
      - the current trends from the scout
      - your past TOP-PERFORMING memes (retrieved by similarity to each trend)
      - past ideas (so we don't repeat ourselves)
    """
    print(f"💡 Idea Generator: producing {n_ideas} concepts...")

    # RAG: pull your historic winners similar to each trend
    winners_context: list[str] = []
    for t in trends[:5]:  # cap so we don't blow context
        hits = memory.search_top_performers(t, k=2)
        winners_context.extend(h.text for h in hits)

    # RAG: pull recent ideas to avoid repeats
    recent_ideas: list[StoredIdea] = []
    for t in trends[:3]:
        recent_ideas.extend(memory.search_similar_ideas(t, k=3))
    avoid_text = "\n".join(f"- {i.text}" for i in recent_ideas[:10]) or "(no past ideas yet)"

    winners_text = "\n".join(f"- {w}" for w in winners_context[:8]) or "(no performance data yet)"
    trends_text = "\n".join(f"- {t}" for t in trends) or "(no trends found)"

    client = OpenAI(api_key=cfg.openai_api_key)
    system = f"""You are a meme idea generator for an Instagram page.
Niche: {cfg.niche}
Voice: {cfg.voice}

You'll receive:
1. Trending angles to riff on
2. Your page's past top-performing memes (study these — they define what works)
3. Recently generated ideas to AVOID (don't repeat them)

Generate {n_ideas} fresh meme concepts. Each must be:
- Adapted to the niche and voice
- Genuinely funny or relatable, not generic
- Specific enough to actually produce (don't say "a meme about Mondays")

For each concept, return:
- concept: one-line description of the meme
- format: e.g. "image macro", "two-panel comparison", "fake conversation screenshot", "before/after"
- why_it_works: 1-2 sentences tying it to the niche
- risk_flags: list of things to watch out for (sensitive topics, regional issues, copyright). Empty list if none.

Respond as JSON: {{"ideas": [{{...}}, {{...}}, ...]}}"""

    user = f"""TRENDS:
{trends_text}

PAST WINNERS (study the patterns):
{winners_text}

DON'T REPEAT THESE RECENT IDEAS:
{avoid_text}"""

    resp = client.chat.completions.create(
        model=cfg.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.9,  # crank creativity for ideation
    )

    content = resp.choices[0].message.content or "{}"
    parsed = json.loads(content)
    raw_ideas = parsed.get("ideas", [])

    ideas = [
        MemeIdea(
            concept=i.get("concept", ""),
            format=i.get("format", ""),
            why_it_works=i.get("why_it_works", ""),
            risk_flags=i.get("risk_flags", []) or [],
        )
        for i in raw_ideas
        if i.get("concept")
    ]

    # Save all as drafts so we can avoid repeats next time
    for idea in ideas:
        memory.add_idea(idea.concept, status="draft", format=idea.format)

    print(f"  ✅ Generated {len(ideas)} concepts")
    return ideas


# ============================================================================
# Agent 3: Caption Writer
# ============================================================================
def caption_writer(cfg: Config, idea: MemeIdea) -> CaptionPackage:
    """Writes the IG caption + hashtag strategy for an approved idea."""
    client = OpenAI(api_key=cfg.openai_api_key)
    system = f"""You are an Instagram caption writer for a meme page.
Niche: {cfg.niche}
Voice: {cfg.voice}

Rules:
- Caption: 1-2 lines max. Punchy. No "follow for more" begging.
- Hashtags: 8-15 mixing broad + niche tags. Lowercase. No spaces.
- First comment: 15-25 EXTRA hashtags (IG strategy — keeps caption clean while still indexing).

Respond as JSON:
{{"caption": "...", "hashtags": ["tag1", "tag2", ...], "first_comment": "..."}}"""

    user = f"""Meme concept: {idea.concept}
Format: {idea.format}
Why it works: {idea.why_it_works}"""

    resp = client.chat.completions.create(
        model=cfg.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    parsed = json.loads(resp.choices[0].message.content or "{}")
    return CaptionPackage(
        caption=parsed.get("caption", ""),
        hashtags=parsed.get("hashtags", []),
        first_comment=parsed.get("first_comment", ""),
    )


def _get_meme_font(size: int):
    from PIL import ImageFont
    candidates = [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/Library/Fonts/Impact.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _add_meme_text(img_path: str, text: str) -> None:
    """Overlay meme text inside a white rounded-rectangle box fixed at 20% of image height."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    img = Image.open(img_path).convert("RGBA")
    w, h = img.size

    box_w = int(w * 0.88)
    box_h = int(h * 0.20)              # fixed 20% of image height
    box_x = (w - box_w) // 2
    box_y = h - box_h - int(h * 0.02)
    radius = 22
    pad = int(box_h * 0.12)            # 12% of box as top/bottom padding
    max_text_w = box_w - int(w * 0.08)
    available_h = box_h - pad * 2

    # Binary-search for the largest font that fits inside the box
    tmp_draw = ImageDraw.Draw(img)
    lo, hi = 12, box_h
    best_font, best_lines = _get_meme_font(lo), [text]
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _get_meme_font(mid)
        lines = _wrap_text(tmp_draw, text, font, max_text_w)
        line_h = int(mid * 1.25)
        if len(lines) * line_h <= available_h:
            best_font, best_lines = font, lines
            lo = mid + 1
        else:
            hi = mid - 1

    line_h = int(((hi + 1) // 1) * 1.25)

    # Draw white rounded box
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=radius,
        fill=(255, 255, 255, 248),
    )
    img = Image.alpha_composite(img, overlay)

    # Center text block vertically inside the box
    draw = ImageDraw.Draw(img)
    font_size_used = (lo - 1)
    lh = int(font_size_used * 1.25)
    total_text_h = len(best_lines) * lh
    y = box_y + (box_h - total_text_h) // 2

    for line in best_lines:
        bbox = draw.textbbox((0, 0), line, font=best_font)
        x = (w - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=best_font, fill=(0, 0, 0, 255))
        y += lh

    img.convert("RGB").save(img_path, "PNG")


# ============================================================================
# Agent 4: Image Generator (DALL-E 3)
# ============================================================================
def image_generator(cfg: Config, idea: MemeIdea, caption: str = "") -> str:
    """
    Writes a DALL-E prompt for the meme concept, generates the image,
    downloads it, optionally burns the caption onto the bottom, and returns
    the local file path.
    """
    client = OpenAI(api_key=cfg.openai_api_key)

    # Step 1: GPT writes the DALL-E prompt
    system = f"""You write DALL-E 3 image generation prompts for Instagram meme visuals.
Niche: {cfg.niche}
Voice: {cfg.voice}

Rules:
- Describe the scene visually and specifically — no abstract descriptions
- Do NOT include any text or words in the image (caption handles that)
- Style: bold, clean, high contrast — works well as a meme visual
- Fit the meme format: for two-panel, describe both panels; for image macro, describe the scene
- Keep it under 150 words
- Respond with just the prompt string, nothing else"""

    prompt_resp = client.chat.completions.create(
        model=cfg.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Concept: {idea.concept}\nFormat: {idea.format}"},
        ],
    )
    dalle_prompt = (prompt_resp.choices[0].message.content or "").strip()

    # Step 2: Generate image with DALL-E 3
    img_resp = client.images.generate(
        model="dall-e-3",
        prompt=dalle_prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    image_url = img_resp.data[0].url or ""

    # Step 3: Download and save locally
    img_dir = Path("./data/images")
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / f"{uuid.uuid4()}.png"
    img_data = _requests.get(image_url, timeout=30).content
    img_path.write_bytes(img_data)

    # Step 4: Burn caption text onto the bottom of the image
    if caption:
        _add_meme_text(str(img_path), caption)

    return str(img_path)
