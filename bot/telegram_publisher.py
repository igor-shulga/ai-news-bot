"""
Telegram publisher for AI news digests.

Posts bilingual article summaries to a public Telegram channel
using python-telegram-bot v21 (async API).
"""

import asyncio
import logging
import os

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from .parsers import Article

logger = logging.getLogger(__name__)

# Delay between messages to respect Telegram's rate limits
RATE_LIMIT_DELAY_SECONDS = 2


def _escape_markdown(text: str) -> str:
    """Escape special Markdown characters in text to prevent formatting errors."""
    # For Markdown (not MarkdownV2), we only need to escape a few characters
    # inside regular text. We leave []() for links and _ for italic intact.
    return text.replace("`", "'")


async def post_article(
    bot: Bot, channel_id: str, article: Article, summary: dict[str, str]
) -> None:
    """Post a single article summary to the Telegram channel."""
    # Escape article title for Markdown link safety — replace [ and ] in title
    safe_title = article.title.replace("[", "(").replace("]", ")")

    text = (
        f"\U0001f1fa\U0001f1e6 {summary['ua']}\n\n"
        f"\U0001f1ec\U0001f1e7 {summary['en']}\n\n"
        f"\U0001f517 [{safe_title}]({article.url})\n"
        f"\U0001f4F0 _{article.source}_"
    )

    try:
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
        )
        logger.info("Posted: %s", article.title[:60])
    except RetryAfter as exc:
        logger.warning(
            "Telegram rate limit hit, waiting %d seconds", exc.retry_after
        )
        await asyncio.sleep(exc.retry_after)
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
        )
        logger.info("Posted (after retry): %s", article.title[:60])
    except TelegramError as exc:
        logger.error(
            "Failed to post '%s': %s. Skipping this article.",
            article.title[:60],
            exc,
        )


async def publish_all(
    articles_with_summaries: list[tuple[Article, dict[str, str]]],
) -> int:
    """
    Post all article summaries to the Telegram channel.

    Returns the number of successfully posted articles.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]
    bot = Bot(token=token)

    posted = 0
    for article, summary in articles_with_summaries:
        await post_article(bot, channel_id, article, summary)
        posted += 1
        # Respect Telegram rate limits
        if posted < len(articles_with_summaries):
            await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)

    logger.info("Published %d/%d articles", posted, len(articles_with_summaries))
    return posted
