"""
generate_content.py — AI enrichment pipeline.

OPTIMISED: Single AI call per article returns ALL fields at once:
  - context (why it matters for UPSC)
  - key_points (3-5 exam-relevant bullets)
  - fact_check (credibility assessment)
  - title_hi + context_hi + key_points_hi (Hindi translations)

This reduces API calls from 4×N to 1×N, staying well within free-tier limits.
Rate limit: 5s sleep between articles to respect 8 req/min free-tier cap.
"""

from __future__ import annotations

import json
import re
import time

from ai_client import chat

# Sleep between articles — must be >= slowest provider's min_interval
# Groq: 60/20 = 3s, Gemini: 60/5 = 12s → use 13s to be safe
INTER_ARTICLE_SLEEP = 13  # seconds

BATCH_SYSTEM = """You are a UPSC expert coach and Hindi translator.
Given a news headline, source, and summary — return a single JSON object with ALL these fields:

{
  "context": "2-3 sentences: what happened and why it matters for UPSC exam preparation. Mention which GS paper it relates to.",
  "key_points": ["Point 1.", "Point 2.", "Point 3.", "Point 4."],
  "fact_check": {
    "status": "verified|likely_accurate|unverified|suspicious",
    "confidence": 0.0,
    "notes": "One sentence explanation."
  },
  "title_hi": "Hindi translation of headline in Devanagari script",
  "context_hi": "Hindi translation of the context field in Devanagari script",
  "key_points_hi": ["Hindi point 1.", "Hindi point 2.", "Hindi point 3."]
}

Rules:
- key_points: exactly 3-5 items, each one crisp exam-relevant sentence
- fact_check.status: "verified" for PIB/government sources, "likely_accurate" for reputable press
- Hindi: keep English abbreviations (RBI, UPSC, GDP etc.) as-is, translate rest to Devanagari
- Return ONLY the raw JSON object. No markdown, no code fences, no extra text."""


def _safe_parse(raw: str, source: str) -> dict:
    """Parse AI JSON response safely with multiple fallback strategies."""
    # Strip markdown fences if present
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    # Try direct parse
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON object with regex
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    # Return safe fallback
    return {}


def _build_fallback(article: dict) -> dict:
    """Build fallback values when AI call fails entirely."""
    title   = article.get("title", "")
    summary = article.get("summary", "")[:300]
    source  = article.get("source", "")
    is_pib  = source == "PIB"
    return {
        "context":       summary or title,
        "key_points":    [title],
        "fact_check":    {
            "status":     "verified" if is_pib else "likely_accurate",
            "confidence": 0.9 if is_pib else 0.75,
            "notes":      "Official government source." if is_pib else "Reputable news source.",
        },
        "title_hi":      title,
        "context_hi":    summary or title,
        "key_points_hi": [title],
    }


def _validate_and_merge(parsed: dict, fallback: dict) -> dict:
    """Ensure all required fields exist and have correct types."""
    result = {}

    # context — string
    ctx = parsed.get("context", "")
    result["context"] = ctx if isinstance(ctx, str) and ctx.strip() else fallback["context"]

    # key_points — list of strings
    kp = parsed.get("key_points", [])
    if isinstance(kp, list) and len(kp) >= 1:
        result["key_points"] = [str(p) for p in kp[:5]]
    else:
        result["key_points"] = fallback["key_points"]

    # fact_check — dict with required keys
    fc = parsed.get("fact_check", {})
    valid_statuses = {"verified", "likely_accurate", "unverified", "suspicious"}
    if isinstance(fc, dict) and fc.get("status") in valid_statuses:
        result["fact_check"] = {
            "status":     fc["status"],
            "confidence": float(fc.get("confidence", 0.7)),
            "notes":      str(fc.get("notes", "")),
        }
    else:
        result["fact_check"] = fallback["fact_check"]

    # Hindi fields — strings / lists
    result["title_hi"]      = str(parsed.get("title_hi", "")).strip() or fallback["title_hi"]
    result["context_hi"]    = str(parsed.get("context_hi", "")).strip() or fallback["context_hi"]
    kp_hi = parsed.get("key_points_hi", [])
    result["key_points_hi"] = [str(p) for p in kp_hi[:5]] if isinstance(kp_hi, list) and kp_hi else fallback["key_points_hi"]

    return result


def enrich_article(article: dict) -> dict:
    """Single AI call enrichment for one article."""
    title   = article["title"]
    summary = article.get("summary", "")[:600]
    source  = article["source"]

    user_prompt = f"Headline: {title}\nSource: {source}\nSummary: {summary}"
    fallback    = _build_fallback(article)

    try:
        raw    = chat(BATCH_SYSTEM, user_prompt, max_tokens=900, temperature=0.3)
        parsed = _safe_parse(raw, source)
        fields = _validate_and_merge(parsed, fallback)
    except Exception as exc:
        print(f"    ⚠ AI call failed: {exc} — using fallback values")
        fields = fallback

    return {**article, **fields}


def generate_content(articles: list[dict]) -> list[dict]:
    """Enrich all articles with a single AI call each. Returns enriched list."""
    enriched: list[dict] = []
    total = len(articles)

    print(f"  ℹ Using 1 AI call per article = {total} total calls (free-tier safe)")
    print(f"  ℹ Sleeping {INTER_ARTICLE_SLEEP}s between articles to respect rate limits\n")

    for i, article in enumerate(articles, 1):
        print(f"  🤖 [{i:02d}/{total}] {article['title'][:70]}…")
        try:
            enriched.append(enrich_article(article))
            print(f"         ✅ done")
        except Exception as exc:
            print(f"         ❌ Failed: {exc} — including with fallback")
            enriched.append({**article, **_build_fallback(article)})

        # Rate limit guard — skip sleep after last article
        if i < total:
            time.sleep(INTER_ARTICLE_SLEEP)

    return enriched
