"""
Instagram posting via instagrapi.

Local: saves/loads a session file so we don't re-login every run.
Railway: loads session from INSTAGRAM_SESSION env var (base64-encoded JSON),
         generated once by running save_session.py locally.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from instagrapi import Client


_SESSION_FILE = Path("./data/ig_session.json")


def login(username: str, password: str) -> Client:
    cl = Client()
    cl.delay_range = [2, 5]

    session_b64 = os.environ.get("INSTAGRAM_SESSION")
    if session_b64:
        # Railway: restore trusted session — do NOT call login() again,
        # it triggers ChallengeRequired from an unfamiliar IP.
        session = json.loads(base64.b64decode(session_b64))
        cl.set_settings(session)
        cl.get_timeline_feed()  # lightweight call to verify session is alive
        return cl

    # Local: use session file
    _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _SESSION_FILE.exists():
        cl.load_settings(_SESSION_FILE)
    cl.login(username, password)
    cl.dump_settings(_SESSION_FILE)
    return cl


def post_photo(cl: Client, image_path: str, caption: str, first_comment: str = "") -> str:
    """Upload a photo and optionally add the first comment. Returns the media ID."""
    media = cl.photo_upload(Path(image_path), caption)
    if first_comment:
        time.sleep(3)
        cl.media_comment(media.id, first_comment)
    return str(media.id)
