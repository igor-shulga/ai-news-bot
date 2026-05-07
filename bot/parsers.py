"""
Parsers for AI news sources.

Fetches articles from RSS feeds (VentureBeat, TechCrunch, The Decoder)
and HTML pages (Anthropic, Karpathy). Returns a flat list of Article objects
for articles published within the last 24 hours.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CUTOFF_HOURS = 48

RSS_SOURCES = {
    "VentureBeat AI": "https://feeds.feedburner.com/venturebeat/SZYF",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Decoder": "https://the-decoder.com/feed/",
}


@dataclass
class Article:
    """A single news article with metadata."""

    title: str
    url: str
    snippet: str
    source: str


def is_recent(entry) -> bool:
    """Check if a feedparser entry was published within the last CUTOFF_HOURS."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - pub < timedelta(hours=CUTOFF_HOURS)
    # Include the article if there is no publication date
    return True


def fetch_rss(name: str, url: str) -> list[Article]:
    """Fetch articles from an RSS feed, filtering to recent entries only."""
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries:
            if not is_recent(entry):
                continue
            snippet = ""
            if hasattr(entry, "summary"):
                soup = BeautifulSoup(entry.summary, "html.parser")
                snippet = soup.get_text()[:500]
            articles.append(
                Article(
                    title=entry.title,
                    url=entry.link,
                    snippet=snippet,
                    source=name,
                )
            )
        logger.info("RSS [%s]: fetched %d recent articles", name, len(articles))
        return articles
    except Exception as exc:
        logger.error("RSS [%s]: failed to fetch — %s", name, exc)
        return []


def fetch_anthropic_news() -> list[Article]:
    """
    Scrape anthropic.com/news for recent blog posts.

    NOTE: The CSS selectors below are based on the Anthropic site structure
    as of 2026-05. If the site is redesigned, these selectors may need
    manual adjustment. Check the logs if zero articles are returned.
    """
    try:
        resp = httpx.get("https://www.anthropic.com/news", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []
        # Anthropic news cards — links containing /news/ in href
        for card in soup.select("a[href*='/news/']")[:10]:
            title_el = card.select_one("h3, h2, .title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = card.get("href", "")
            if not href:
                continue
            url = (
                "https://www.anthropic.com" + href
                if href.startswith("/")
                else href
            )
            articles.append(
                Article(title=title, url=url, snippet="", source="Anthropic")
            )
        logger.info("Anthropic: fetched %d articles", len(articles))
        return articles
    except Exception as exc:
        logger.error("Anthropic: failed to fetch — %s", exc)
        return []


def fetch_karpathy() -> list[Article]:
    """
    Scrape karpathy.ai for blog posts.

    NOTE: Site structure is unknown and may change. This parser is wrapped
    in a try/except and will fail silently, returning an empty list.
    The selectors are a best-effort guess and may need manual adjustment.
    """
    try:
        resp = httpx.get("https://karpathy.ai/", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []
        for link in soup.select("a[href*='blog'], a[href*='post']")[:5]:
            title = link.get_text(strip=True)
            if not title:
                continue
            href = link.get("href", "")
            url = (
                href
                if href.startswith("http")
                else "https://karpathy.ai" + href
            )
            articles.append(
                Article(title=title, url=url, snippet="", source="Karpathy")
            )
        logger.info("Karpathy: fetched %d articles", len(articles))
        return articles
    except Exception:
        logger.warning("Karpathy: site unreachable or parsing failed — skipping")
        return []


def fetch_all() -> list[Article]:
    """Fetch articles from all configured sources and return a combined list."""
    articles: list[Article] = []
    for name, url in RSS_SOURCES.items():
        articles.extend(fetch_rss(name, url))
    articles.extend(fetch_anthropic_news())
    articles.extend(fetch_karpathy())
    logger.info("Total articles fetched: %d", len(articles))
    return articles
