"""
Run this ONCE locally to generate an Instagram session token for Railway.

Usage:
    python save_session.py

Copy the printed INSTAGRAM_SESSION value into Railway's Variables tab.
"""
import base64
import json

from instagrapi import Client
from dotenv import load_dotenv
import os

load_dotenv(override=True)

username = os.getenv("INSTAGRAM_USERNAME", "")
password = os.getenv("INSTAGRAM_PASSWORD", "")

if not username or not password:
    raise SystemExit("Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in your .env first.")

print(f"Logging in as @{username} ...")
cl = Client()
cl.delay_range = [2, 5]
cl.login(username, password)

session_json = json.dumps(cl.get_settings())
session_b64 = base64.b64encode(session_json.encode()).decode()

print("\n✅ Success! Add this to Railway → Variables → RAW Editor:\n")
print(f"INSTAGRAM_SESSION={session_b64}")
print("\n(Keep this secret — it gives full access to your Instagram account.)")
