"""
Lightweight Reddit scraper using the public JSON endpoint.
No auth required for read-only public data, no PRAW dependency.

If Reddit blocks you (rate limits or User-Agent checks), swap to PRAW.
"""
from __future__ import annotations

import requests

USER_AGENT = "meme-agent/0.1 (research)"


def fetch_top_posts(subreddit: str, limit: int = 25, period: str = "day") -> list[dict]:
    """
    period: 'hour' | 'day' | 'week' | 'month' | 'year' | 'all'
    Returns list of dicts: {title, score, num_comments, url, permalink}
    """
    url = f"https://www.reddit.com/r/{subreddit}/top.json"
    params = {"limit": limit, "t": period}
    headers = {"User-Agent": USER_AGENT}

    r = requests.get(url, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()

    posts = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        posts.append(
            {
                "title": d.get("title", ""),
                "score": d.get("score", 0),
                "num_comments": d.get("num_comments", 0),
                "subreddit": d.get("subreddit", subreddit),
                "url": d.get("url", ""),
                "permalink": f"https://reddit.com{d.get('permalink', '')}",
            }
        )
    return posts


def fetch_trends_across(subreddits: list[str], limit_each: int = 10) -> list[dict]:
    """Aggregate top posts from multiple subreddits."""
    all_posts: list[dict] = []
    for sub in subreddits:
        try:
            all_posts.extend(fetch_top_posts(sub, limit=limit_each))
        except Exception as e:
            print(f"  ⚠️  Failed to fetch r/{sub}: {e}")
    # sort by Reddit score (rough proxy for "what's hot")
    all_posts.sort(key=lambda p: p["score"], reverse=True)
    return all_posts
