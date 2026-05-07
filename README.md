# AI News Telegram Bot

Daily AI news digest bot that scrapes 5 sources, generates bilingual summaries (Ukrainian + English) via a free LLM on OpenRouter, and publishes to a public Telegram channel. Runs on GitHub Actions -- no server, no cost.

## What it does

Every day at 11:00 Kyiv time (08:00 UTC), the bot:

1. Scrapes 5 AI news sources (VentureBeat, TechCrunch, The Decoder, Anthropic, Karpathy)
2. Filters to articles published in the last 24 hours
3. Skips articles that were already posted (deduplication via `seen_urls.json`)
4. Generates a 2-3 sentence summary in Ukrainian and English using a free LLM
5. Posts each article to a public Telegram channel

## Sources

| Source | Method |
|--------|--------|
| VentureBeat AI | RSS feed |
| TechCrunch AI | RSS feed |
| The Decoder | RSS feed |
| anthropic.com/news | HTML scraping |
| karpathy.ai | HTML scraping (best-effort, fails silently) |

## One-time setup

1. **Create a Telegram bot:** Open Telegram, search for `@BotFather`, send `/newbot`, follow the prompts. Save the `BOT_TOKEN` it gives you.

2. **Create a public Telegram channel:** In Telegram, create a new channel, make it public, and choose a username (e.g., `@ai_news_daily_ua`). Add your bot as an **Administrator** with "Post Messages" permission.

3. **Fork or clone this repo** to your own GitHub account.

4. **Add GitHub Secrets** (repo Settings > Secrets and variables > Actions > New repository secret):
   - `OPENROUTER_API_KEY` -- your OpenRouter API key (get one at https://openrouter.ai/)
   - `TELEGRAM_BOT_TOKEN` -- the token from BotFather
   - `TELEGRAM_CHANNEL_ID` -- your channel username, e.g. `@ai_news_daily_ua`

5. **Push to GitHub** -- the bot will run automatically every day at 11:00 Kyiv time (08:00 UTC).

6. **Manual trigger:** Go to GitHub > Actions > "Daily AI News Digest" > "Run workflow" to trigger a run immediately.

## Local test run

```bash
export OPENROUTER_API_KEY=your_key
export TELEGRAM_BOT_TOKEN=your_token
export TELEGRAM_CHANNEL_ID=@your_channel
python main.py
```

## Message format

Each posted message looks like this:

```
[Ukrainian flag] Ukrainian summary of the article in 2-3 sentences.

[British flag] English summary of the article in 2-3 sentences.

[Link icon] Article Title
[Newspaper icon] Source Name
```

## Architecture

```
main.py                      -- entry point, orchestrates the pipeline
bot/
  parsers.py                 -- RSS + HTML scrapers for all 5 sources
  llm.py                     -- OpenRouter LLM client for bilingual summaries
  telegram_publisher.py      -- Telegram channel publisher
seen_urls.json               -- deduplication state (committed by GitHub Actions)
.github/workflows/daily.yml  -- cron job + manual trigger
```

## Notes

- The bot caps at 10 articles per run to stay within free LLM quotas.
- Anthropic and Karpathy HTML selectors may need adjustment if those sites are redesigned. Check the workflow logs if zero articles are returned from those sources.
- The free LLM model is fetched dynamically from `shir-man.com/free-llm/` before each run. If that endpoint is unavailable, it falls back to `openrouter/auto`.
