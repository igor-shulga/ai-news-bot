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


def summarize(article: Article) -> dict:
    """
    Score article relevance and generate bilingual analytical summary.

    Returns dict with keys: 'score' (int), 'ua' (str), 'en' (str).
    If score <= 7, 'ua' and 'en' will be empty strings.

    Raises on API errors so the caller can decide how to handle failures.
    """
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = get_best_model()

    content_text = (
        article.snippet[:800]
        if article.snippet
        else "No content available, analyze based on title only."
    )

    user_prompt = (
        f"Title: {article.title}\n"
        f"Source: {article.source}\n"
        f"Content: {content_text}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 400,
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

    if "score" not in result or "ua" not in result or "en" not in result:
        raise ValueError(
            f"LLM response missing required keys: {list(result.keys())}"
        )

    score = int(result["score"])
    logger.info(
        "Scored %d/10: %s [model=%s]", score, article.title[:60], model
    )
    return {"score": score, "ua": result["ua"], "en": result["en"]}
