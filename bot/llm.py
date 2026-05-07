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


SYSTEM_PROMPT = """You are a personal AI news analyst for a Head of Product & Quality who is deeply interested in:
- AI agents and multi-agent systems (AI factories, orchestration, autonomous workflows)
- LLMs, foundation models, new model releases and capabilities
- AI in product development and software engineering
- New trends shaping the AI industry

Your job:
1. Score the article's relevance (1-10) for this reader. Score > 7 means it's worth reading.
   - Score 8-10: directly about AI agents, LLMs, AI dev tools, AI industry shifts
   - Score 5-7: tangentially related (AI policy, funding, hardware)
   - Score 1-4: not relevant (unrelated tech, politics, sports)

2. If relevant (score > 7), write a short analytical summary:
   - 2-3 sentences max
   - Focus on: what happened + what it means for the AI industry / product teams
   - Not just facts — give insight: "This signals...", "This changes...", "Teams should pay attention because..."

Return ONLY a JSON object with these keys:
- "score": integer 1-10
- "ua": Ukrainian analytical summary (or empty string "" if score <= 7)
- "en": English analytical summary (or empty string "" if score <= 7)
"""


import time

BATCH_SYSTEM_PROMPT = SYSTEM_PROMPT + """
You will receive a numbered list of articles. Return a JSON object with key "results" —
an array where each element corresponds to the article at the same index:
[{"score": 8, "ua": "...", "en": "..."}, ...]

Return ONLY the JSON object, nothing else.
"""


def _call_openrouter(payload: dict, api_key: str) -> str:
    """Make one OpenRouter call with retry on 429 and null content."""
    for attempt in range(3):
        if attempt > 0:
            time.sleep(5 * attempt)

        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/ai-news-bot",
            },
            json=payload,
            timeout=60,
        )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            logger.warning("Rate limited, waiting %ds (attempt %d/3)", retry_after, attempt + 1)
            time.sleep(retry_after)
            continue

        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content")

        if content is None:
            logger.warning("Null content from model (attempt %d/3), retrying...", attempt + 1)
            continue

        return content

    raise ValueError("Failed to get valid response after 3 attempts")


def summarize_batch(articles: list[Article]) -> list[dict]:
    """
    Score and summarize a batch of articles in a single LLM call.

    Returns a list of dicts with keys: 'score' (int), 'ua' (str), 'en' (str).
    Falls back to per-article calls if batch parsing fails.
    """
    if not articles:
        return []

    api_key = os.environ["OPENROUTER_API_KEY"]
    model = get_best_model()
    logger.info("Using model: %s, batch size: %d", model, len(articles))

    # Build numbered article list for the prompt
    articles_text = "\n\n".join(
        f"[{i}] Title: {a.title}\nSource: {a.source}\n"
        f"Content: {a.snippet[:400] if a.snippet else 'No content.'}"
        for i, a in enumerate(articles)
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": BATCH_SYSTEM_PROMPT},
            {"role": "user", "content": articles_text},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 400 * len(articles),
    }

    try:
        content = _call_openrouter(payload, api_key)
        data = json.loads(content)
        results_raw = data.get("results", [])

        if len(results_raw) != len(articles):
            raise ValueError(
                f"Expected {len(articles)} results, got {len(results_raw)}"
            )

        results = []
        for i, (article, r) in enumerate(zip(articles, results_raw)):
            score = int(r.get("score", 0))
            logger.info("Scored %d/10: %s", score, article.title[:60])
            results.append({"score": score, "ua": r.get("ua", ""), "en": r.get("en", "")})
        return results

    except Exception as exc:
        logger.warning("Batch failed (%s), falling back to per-article calls", exc)
        return _summarize_one_by_one(articles, api_key, model)


def _summarize_one_by_one(articles: list[Article], api_key: str, model: str) -> list[dict]:
    """Fallback: summarize articles one by one."""
    results = []
    for i, article in enumerate(articles):
        if i > 0:
            time.sleep(3)
        try:
            content_text = article.snippet[:800] if article.snippet else "No content."
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Title: {article.title}\nSource: {article.source}\nContent: {content_text}"},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 400,
            }
            content = _call_openrouter(payload, api_key)
            r = json.loads(content)
            score = int(r.get("score", 0))
            logger.info("Scored %d/10: %s", score, article.title[:60])
            results.append({"score": score, "ua": r.get("ua", ""), "en": r.get("en", "")})
        except Exception as exc:
            logger.error("Failed to summarize '%s': %s", article.title[:60], exc)
            results.append({"score": 0, "ua": "", "en": ""})
    return results
