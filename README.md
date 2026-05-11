# AI News Telegram Bot

Daily AI news digest bot. Scrapes 5 sources, scores each article by relevance (1-10), generates bilingual summaries (Ukrainian + English) via a free LLM, and publishes to a Telegram channel. Runs on GitHub Actions — no server, no cost.

## What it does

Every day at **11:00 Kyiv time** (08:00 UTC), the bot:

1. Scrapes 5 AI news sources
2. Filters articles published in the last 48 hours
3. Skips already-posted articles (deduplication via `seen_urls.json`)
4. Scores each article 1-10 for relevance — only articles scoring **> 7** are published
5. Generates a bilingual analytical summary (UA + EN) — not just facts, but "what this means for the industry"
6. Posts to your Telegram channel

## Sources

| Source | Method |
|--------|--------|
| VentureBeat AI | RSS |
| TechCrunch AI | RSS |
| The Decoder | RSS |
| anthropic.com/news | HTML scraping |
| karpathy.ai | HTML scraping (best-effort) |

## Message format

```
🇺🇦 Короткий аналітичний summary українською...

🇬🇧 Short analytical summary in English...

🔗 Article Title
📰 Source Name
```

---

## Setup Instructions

### Step 1 — Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Enter a name (e.g. `AI News Daily`) and a username (e.g. `ai_news_daily_bot`)
4. Save the token it gives you — looks like `123456789:ABCdef...`

### Step 2 — Create a Telegram Channel

1. In Telegram: tap the pencil icon → New Channel
2. Choose **Public** channel, set a username (e.g. `@ai_news_daily_ua`)
3. Open Channel Info → Administrators → Add Administrator
4. Search for your bot username → Add with **"Post Messages"** permission

> **Private channel?** You'll need a numeric channel ID (e.g. `-1001234567890`).
> Forward any message from the channel to **@userinfobot** or **@RawDataBot** to get it.

### Step 3 — Get an OpenRouter API Key

1. Go to **openrouter.ai** and sign up (free, no credit card needed)
2. Go to **Keys** → Create Key
3. Save the key — starts with `sk-or-...`

> The bot uses shir-man.com to pick the best free model each day automatically.

### Step 4 — Fork this repo

1. Go to `github.com/igor-shulga/ai-news-bot`
2. Click **Fork** → Create fork
3. You now have your own copy at `github.com/YOUR_USERNAME/ai-news-bot`

### Step 5 — Add GitHub Secrets

In your forked repo: **Settings → Secrets and variables → Actions → New repository secret**

Add these 3 secrets:

| Secret name | Value |
|-------------|-------|
| `OPENROUTER_API_KEY` | Your OpenRouter key (`sk-or-...`) |
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_CHANNEL_ID` | `@your_channel_username` or `-1001234567890` for private |

### Step 6 — Run it

**Automatic:** The bot runs every day at 08:00 UTC (11:00 Kyiv) automatically.

**Manual trigger:**
1. Go to your repo → **Actions** tab
2. Click **Daily AI News Digest** in the left sidebar
3. Click **Run workflow** → **Run workflow**

Watch the logs — you'll see articles being scored and published.

---

## Local test run

```bash
git clone https://github.com/YOUR_USERNAME/ai-news-bot
cd ai-news-bot
pip install -r requirements.txt

export OPENROUTER_API_KEY=sk-or-...
export TELEGRAM_BOT_TOKEN=123456:ABC...
export TELEGRAM_CHANNEL_ID=@your_channel

python main.py
```

---

## Architecture

```
main.py                       ← orchestrator: fetch → deduplicate → summarize → publish
bot/
  parsers.py                  ← RSS + HTML scrapers for all 5 sources
  llm.py                      ← OpenRouter client: batch scoring + bilingual summaries
  telegram_publisher.py       ← posts to Telegram channel
seen_urls.json                ← deduplication state (auto-committed by GitHub Actions)
.github/workflows/daily.yml   ← cron schedule + manual trigger
```

## Notes

- Articles are processed in batches of 5 to stay within free LLM quotas
- If batch scoring fails, falls back to per-article calls automatically
- Anthropic/Karpathy HTML selectors may break if those sites redesign — check logs if 0 articles from those sources
- `seen_urls.json` is committed back to the repo after each run to persist deduplication state
