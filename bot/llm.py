"""
LLM integration via OpenRouter (OpenAI-compatible API).

Fetches the best available free model from shir-man.com/free-llm/,
then generates bilingual (UA + EN) summaries for each article.
"""

import json
import logging
import os

import httpx

from .parsers import Article

logger = logging.getLogger(__name__)

# Endpoint that returns the currently recommended free model.
# Expected response: JSON with a "model" key, e.g. {"model": "google/gemma-3-27b-it:free"}
# If the exact JSON endpoint is not available, we try the HTML page and fall back.
FREE_LLM_URL = "https://shir-man.com/free-llm/"
FALLBACK_MODEL = "openrouter/auto"


def get_best_model() -> str:
    """
    Fetch today's recommended free model from shir-man.com.

    Tries the page as JSON first. If that fails, attempts to parse the HTML
    for a model identifier. Falls back to 'openrouter/auto' on any error.
    """
    try:
        resp = httpx.get(FREE_LLM_URL, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")

        # Try JSON response first
        if "json" in content_type:
            data = resp.json()
            model = data.get("model", FALLBACK_MODEL)
            logger.info("Free LLM model (JSON): %s", model)
            return model

        # Try parsing as JSON even if content-type is wrong
        try:
            data = resp.json()
            model = data.get("model", FALLBACK_MODEL)
            logger.info("Free LLM model (parsed JSON): %s", model)
            return model
        except (json.JSONDecodeError, ValueError):
            pass

        # Fall back to HTML parsing — look for a model string in the page
        # Model strings typically look like "provider/model-name:free"
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "html.parser")
        # Look for code blocks, pre tags, or any text that looks like a model ID
        for tag in soup.select("code, pre, .model, #model"):
            text = tag.get_text(strip=True)
            if "/" in text and len(text) < 100:
                logger.info("Free LLM model (HTML parsed): %s", text)
                return text

        logger.warning(
            "Could not extract model from %s — using fallback", FREE_LLM_URL
        )
        return FALLBACK_MODEL
    except Exception as exc:
        logger.warning("Failed to fetch free LLM model: %s — using fallback", exc)
        return FALLBACK_MODEL


def summarize(article: Article) -> dict[str, str]:
    """
    Generate a bilingual summary for the given article.

    Returns a dict with keys 'ua' (Ukrainian) and 'en' (English),
    each containing a 2-3 sentence summary.

    Raises on API errors so the caller can decide how to handle failures.
    """
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = get_best_model()

    content_text = (
        article.snippet[:800]
        if article.snippet
        else "No content available, summarize based on title only."
    )

    prompt = (
        "You are an AI news summarizer. Summarize the following article "
        "in 2-3 sentences.\n"
        'Return a JSON object with two keys: "ua" (Ukrainian summary) '
        'and "en" (English summary).\n'
        "Only return the JSON, nothing else.\n\n"
        f"Title: {article.title}\n"
        f"Source: {article.source}\n"
        f"Content: {content_text}"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
    }

    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/ai-news-bot",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    response_data = resp.json()
    content = response_data["choices"][0]["message"]["content"]
    result = json.loads(content)

    if "ua" not in result or "en" not in result:
        raise ValueError(
            f"LLM response missing required keys 'ua'/'en': {list(result.keys())}"
        )

    logger.info("Summarized: %s [model=%s]", article.title[:60], model)
    return result
