"""
Run this ONCE locally to generate an Instagram session token for Railway.

Steps to get your sessionid from Chrome:
1. Go to instagram.com — logged in as @broesmeme
2. Press F12 → Application → Cookies → https://www.instagram.com
3. Find the cookie named "sessionid"
4. Right-click the row → Copy Value   (NOT the shown value — use Copy Value)

Then run:  python save_session.py
"""
import base64
import json
import os
from urllib.parse import unquote

from instagrapi import Client
from dotenv import load_dotenv

load_dotenv(override=True)

username = os.getenv("INSTAGRAM_USERNAME", "broesmeme")

print(f"Account: @{username}")
print()
sessionid = input("Paste sessionid here: ").strip()

# Instagram sometimes URL-encodes the value (%2C instead of comma, \054 = octal comma)
sessionid = unquote(sessionid)
sessionid = sessionid.replace("\\054", ",")

print(f"\nDecoded sessionid: {sessionid[:30]}...")
print("Verifying with Instagram...")

cl = Client()
cl.delay_range = [2, 5]
cl.username = username

try:
    cl.login_by_sessionid(sessionid)
    session_json = json.dumps(cl.get_settings())
    session_b64 = base64.b64encode(session_json.encode()).decode()
    print("\n✅ Success! Add this to Railway Variables → RAW Editor:\n")
    print(f"INSTAGRAM_SESSION={session_b64}")
    print("\nKeep this secret — treat it like a password.")
except Exception as e:
    print(f"\n❌ Failed: {e}")
    print("\nMake sure you:")
    print("  - Are logged in as @broesmeme on instagram.com")
    print("  - Copied the 'sessionid' cookie value (not the name)")
    print("  - The session is not expired (try logging out and back in on Instagram)")
