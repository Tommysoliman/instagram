"""
Instagram posting via instagrapi.
Saves a session file so we don't re-login every run.
"""
from __future__ import annotations

import time
from pathlib import Path

from instagrapi import Client


_SESSION_FILE = Path("./data/ig_session.json")


def login(username: str, password: str) -> Client:
    cl = Client()
    cl.delay_range = [2, 5]

    _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    if _SESSION_FILE.exists():
        cl.load_settings(_SESSION_FILE)

    cl.login(username, password)
    cl.dump_settings(_SESSION_FILE)
    return cl


def post_photo(cl: Client, image_path: str, caption: str, first_comment: str = "") -> str:
    """
    Upload a photo and optionally add the first comment.
    Returns the media ID.
    """
    media = cl.photo_upload(Path(image_path), caption)
    if first_comment:
        time.sleep(3)  # small delay before commenting
        cl.media_comment(media.id, first_comment)
    return str(media.id)
