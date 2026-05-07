"""
AI News Bot — main entry point.

Orchestrates the full pipeline:
  1. Fetch articles from all configured sources
  2. Deduplicate against previously seen URLs
  3. Summarize each new article via OpenRouter LLM
  4. Publish bilingual summaries to a Telegram channel
  5. Persist seen URLs for future deduplication
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from bot.llm import summarize_batch
from bot.parsers import Article, fetch_all
from bot.telegram_publisher import publish_all

# Maximum number of articles to process per run (to stay within free LLM quotas)
MAX_ARTICLES_PER_RUN = 5

# Path to the deduplication state file (committed to repo by GitHub Actions)
SEEN_FILE = Path(__file__).parent / "seen_urls.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_seen() -> set[str]:
    """Load the set of previously seen article URLs from disk."""
    if SEEN_FILE.exists():
        try:
            data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            return set(data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Corrupted %s, starting fresh: %s", SEEN_FILE, exc)
            return set()
    return set()


def save_seen(seen: set[str]) -> None:
    """Persist the set of seen URLs to disk as a JSON array."""
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Saved %d seen URLs to %s", len(seen), SEEN_FILE)


async def main() -> None:
    """Run the full fetch-summarize-publish pipeline."""
    seen = load_seen()
    logger.info("Loaded %d previously seen URLs", len(seen))

    articles = fetch_all()
    new_articles = [a for a in articles if a.url not in seen]
    logger.info(
        "Found %d total articles, %d are new", len(articles), len(new_articles)
    )

    if not new_articles:
        logger.info("No new articles today. Exiting.")
        return

    # Cap the number of articles per run
    batch = new_articles[:MAX_ARTICLES_PER_RUN]
    if len(new_articles) > MAX_ARTICLES_PER_RUN:
        logger.info(
            "Capping at %d articles (skipping %d)",
            MAX_ARTICLES_PER_RUN,
            len(new_articles) - MAX_ARTICLES_PER_RUN,
        )

    RELEVANCE_THRESHOLD = 7

    summaries = summarize_batch(batch)

    results: list[tuple[Article, dict]] = []
    for article, summary in zip(batch, summaries):
        seen.add(article.url)  # mark as seen regardless of score
        if summary["score"] <= RELEVANCE_THRESHOLD:
            logger.info("Skipped (score %d/10): %s", summary["score"], article.title[:60])
            continue
        results.append((article, summary))

    if results:
        posted = await publish_all(results)
        logger.info("Published %d articles to Telegram", posted)
    else:
        logger.warning("No articles were successfully summarized")

    # Always save seen URLs, even if publishing failed for some,
    # to avoid re-summarizing the same articles next run
    save_seen(seen)
    logger.info("Done. Processed %d articles total.", len(results))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
