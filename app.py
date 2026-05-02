from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, send_from_directory

from config import load_config
from memory import MemeMemory
from agents import trend_scout, idea_generator, caption_writer, image_generator, MemeIdea
from poster import login as ig_login, post_photo

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "meme-agent-secret")

STATE_FILE = Path("./data/app_state.json")
IMAGES_DIR = Path("./data/images")
_ig_client = None


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _ideas_to_dicts(ideas: list[MemeIdea]) -> list[dict]:
    return [
        {
            "concept": i.concept,
            "format": i.format,
            "why_it_works": i.why_it_works,
            "risk_flags": i.risk_flags,
        }
        for i in ideas
    ]


def _dicts_to_ideas(dicts: list[dict]) -> list[MemeIdea]:
    return [
        MemeIdea(
            concept=d["concept"],
            format=d["format"],
            why_it_works=d["why_it_works"],
            risk_flags=d.get("risk_flags", []),
        )
        for d in dicts
    ]


@app.route("/")
def index():
    cfg = load_config()
    state = _load_state()
    return render_template("index.html", niche=cfg.niche, voice=cfg.voice, status=state.get("status", "idle"))


@app.route("/generate", methods=["POST"])
def generate():
    count = int(request.form.get("count", 5))
    cfg = load_config()
    mem = MemeMemory(cfg)
    trends = trend_scout(cfg, mem)
    ideas = idea_generator(cfg, mem, trends, n_ideas=count)
    _save_state({"status": "ideas_ready", "ideas": _ideas_to_dicts(ideas)})
    return redirect(url_for("review"))


@app.route("/review")
def review():
    state = _load_state()
    ideas = state.get("ideas", [])
    if not ideas:
        return redirect(url_for("index"))
    return render_template("review.html", ideas=enumerate(ideas))


@app.route("/post", methods=["POST"])
def post():
    global _ig_client
    selected = request.form.getlist("selected")
    if not selected:
        return redirect(url_for("review"))

    state = _load_state()
    all_ideas = _dicts_to_ideas(state.get("ideas", []))
    approved = [all_ideas[int(i)] for i in selected if int(i) < len(all_ideas)]

    cfg = load_config()
    results = []

    for idea in approved:
        cap = caption_writer(cfg, idea)
        try:
            img_path = image_generator(cfg, idea, caption=cap.caption)
            img_file = Path(img_path).name
        except Exception as e:
            img_path = ""
            img_file = ""

        results.append({
            "concept": idea.concept,
            "format": idea.format,
            "caption": cap.caption,
            "hashtags": cap.hashtags,
            "first_comment": cap.first_comment,
            "image_path": img_path,
            "image_file": img_file,
            "media_id": None,
            "error": None,
        })

    if cfg.instagram_username and cfg.instagram_password:
        try:
            if _ig_client is None:
                _ig_client = ig_login(cfg.instagram_username, cfg.instagram_password)
        except Exception as e:
            for r in results:
                r["error"] = f"Instagram login failed: {e}"
            _save_state({"status": "done", "results": results})
            return redirect(url_for("results"))

        for r in results:
            if not r["image_path"]:
                r["error"] = "Image generation failed"
                continue
            try:
                full_caption = r["caption"] + "\n\n" + " ".join(f"#{h}" for h in r["hashtags"])
                media_id = post_photo(_ig_client, r["image_path"], full_caption, r["first_comment"])
                r["media_id"] = media_id
            except Exception as e:
                r["error"] = str(e)

    _save_state({"status": "done", "results": results})
    return redirect(url_for("results"))


@app.route("/results")
def results():
    state = _load_state()
    return render_template("results.html", results=state.get("results", []))


@app.route("/image/<filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR.resolve(), filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
