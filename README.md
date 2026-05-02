# Meme Agent

A 3-agent system that runs your Instagram meme page. You stay in the creative driver's seat — the agents do the legwork.

## What it does

1. 🔍 **Trend Scout** — pulls top Reddit posts from your chosen subreddits, extracts meme-worthy angles relevant to your niche.
2. 💡 **Idea Generator** — riffs on those trends to produce 5+ meme concepts. Uses ChromaDB to pull your past top performers (RAG) and avoid repeating recent ideas.
3. ✋ **You** — review the table of ideas in the terminal, pick which to keep.
4. ✍️ **Caption Writer** — produces caption + hashtags + first-comment hashtag pile for each approved idea.

ChromaDB stores three things across runs:
- **trends** — what's hot lately
- **ideas** — every concept ever generated (so you don't repeat yourself)
- **performance** — past memes + engagement (the system learns what works)

## Setup

```bash
# 1. Clone / unzip into a folder, then:
cd meme-agent

# 2. Create a virtual environment
python -m venv .venv
.\.venv\Scripts\activate     # Windows PowerShell
# source .venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
copy .env.example .env       # Windows
# cp .env.example .env       # Mac/Linux
# now edit .env and put your OPENAI_API_KEY in there
```

Edit `.env` and set:
- `OPENAI_API_KEY` — required
- `MEME_NICHE` — describe your page in one sentence
- `MEME_VOICE` — describe your tone
- `TREND_SUBREDDITS` — which subreddits to scrape

## Run

```bash
python main.py            # 5 ideas
python main.py --count 8  # 8 ideas
```

You'll see:
1. Trend scouting output
2. A table of meme ideas
3. A prompt — type `1,3,5` or `all` or `none`
4. Caption packages for whichever you approved

## Project structure

```
meme-agent/
├── .env.example         ← copy to .env
├── requirements.txt
├── config.py            ← env var loading
├── memory.py            ← ChromaDB wrapper
├── agents.py            ← the 3 agents (OpenAI calls)
├── graph.py             ← LangGraph orchestration
├── main.py              ← CLI entrypoint
└── tools/
    └── reddit_scraper.py ← public Reddit JSON, no auth
```

## What's next (you'll want to add these)

- **Image generation** — wire DALL-E / Imagen / a text-on-image PIL renderer into a 4th agent
- **Instagram posting** — Instagram Graph API (official, requires Business account) or `instagrapi` (unofficial)
- **Performance feedback loop** — a script that pulls likes/saves/comments after a post is live and calls `memory.add_performance(...)` so the system learns what works
- **Scheduling** — wrap `main.py` in a cron job or Windows Task Scheduler

## Cost notes

With `gpt-4o-mini` and `text-embedding-3-small`, one full run (scout + 5 ideas + 5 captions) costs roughly $0.01–0.03. You can run it daily on a few dollars a month.
