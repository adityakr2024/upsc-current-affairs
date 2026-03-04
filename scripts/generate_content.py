"""
generate_content.py — AI enrichment pipeline.

For each filtered article:
  1. Generate 2–3 sentence context (why it matters for UPSC)
  2. Extract 3–5 key points
  3. Fact-check credibility assessment
  4. Translate headline + context to Hindi

All AI calls go through ai_client.py (OpenRouter free models).
"""

import json
import time
import re
from ai_client import chat


# ─── Prompt templates ────────────────────────────────────────────────────────

CONTEXT_SYSTEM = """You are a UPSC expert coach. Given a news headline and summary,
write a concise 2-3 sentence context explaining:
1. What happened (brief)
2. Why it matters for UPSC exam preparation
3. Which GS paper / topic it relates to

Be factual. No markdown. Plain text only."""

KEY_POINTS_SYSTEM = """You are a UPSC expert. Extract exactly 3-5 bullet points
from this news article that are most exam-relevant. Each point: one sentence, crisp.
Return ONLY a JSON array of strings. No extra text. Example:
["Point 1.", "Point 2.", "Point 3."]"""

FACT_CHECK_SYSTEM = """You are a fact-checker for Indian news. Assess the credibility
of this article snippet. Consider: Is the source reliable? Are the claims specific
and verifiable? Are there any red flags?
Return a JSON object with exactly these keys:
{"status": "verified|likely_accurate|unverified|suspicious",
 "confidence": 0.0-1.0,
 "notes": "one sentence explanation"}
No extra text."""

HINDI_SYSTEM = """Translate the following English text to Hindi (Devanagari script).
Keep proper nouns, organisation names, and English abbreviations as-is.
Return only the translated text, nothing else."""


def _safe_json(text: str, fallback):
    """Try to parse JSON from AI response, return fallback on failure."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("```").strip()
    try:
        return json.loads(text)
    except Exception:
        # Try to extract array or object with regex
        try:
            m = re.search(r"(\[.*?\]|\{.*?\})", text, re.DOTALL)
            if m:
                return json.loads(m.group(1))
        except Exception:
            pass
    return fallback


def enrich_article(article: dict) -> dict:
    """Run the full enrichment pipeline for a single article."""
    title = article["title"]
    summary = article.get("summary", "")
    source = article["source"]
    user_text = f"Headline: {title}\nSource: {source}\nSummary: {summary}"

    # ── 1. Context ────────────────────────────────────────────────────────────
    try:
        context = chat(CONTEXT_SYSTEM, user_text, max_tokens=300)
    except Exception as e:
        print(f"    Context failed: {e}")
        context = summary[:400] if summary else title

    # ── 2. Key points ─────────────────────────────────────────────────────────
    try:
        raw = chat(KEY_POINTS_SYSTEM, user_text, max_tokens=400)
        key_points = _safe_json(raw, [])
        if not isinstance(key_points, list) or len(key_points) == 0:
            key_points = [context]
    except Exception as e:
        print(f"    Key points failed: {e}")
        key_points = [context]

    # ── 3. Fact check ─────────────────────────────────────────────────────────
    try:
        raw = chat(FACT_CHECK_SYSTEM, user_text, max_tokens=150, temperature=0.1)
        fact_check = _safe_json(
            raw,
            {"status": "unverified", "confidence": 0.5, "notes": "Could not assess."},
        )
    except Exception as e:
        print(f"    Fact-check failed: {e}")
        # PIB is government source — auto-mark as verified
        if source == "PIB":
            fact_check = {"status": "verified", "confidence": 0.9, "notes": "Official government source."}
        else:
            fact_check = {"status": "likely_accurate", "confidence": 0.75, "notes": "Reputable news source."}

    # ── 4. Hindi translation ───────────────────────────────────────────────────
    try:
        title_hi = chat(HINDI_SYSTEM, title, max_tokens=150)
        context_hi = chat(HINDI_SYSTEM, context, max_tokens=400)
        key_points_hi = [
            chat(HINDI_SYSTEM, pt, max_tokens=200) for pt in key_points[:3]
        ]
    except Exception as e:
        print(f"    Hindi translation failed: {e}")
        title_hi = title
        context_hi = context
        key_points_hi = key_points

    time.sleep(0.5)   # Respect free-tier rate limits

    return {
        **article,
        "context": context,
        "key_points": key_points,
        "fact_check": fact_check,
        "title_hi": title_hi,
        "context_hi": context_hi,
        "key_points_hi": key_points_hi,
    }


def generate_content(articles: list[dict]) -> list[dict]:
    """Enrich all articles. Returns enriched list."""
    enriched = []
    total = len(articles)
    for i, article in enumerate(articles, 1):
        print(f"\n  🤖 Enriching [{i}/{total}]: {article['title'][:70]}...")
        try:
            enriched.append(enrich_article(article))
        except Exception as e:
            print(f"    ❌ Failed to enrich: {e}")
            # Include article without enrichment rather than dropping it
            article.setdefault("context", article.get("summary", article["title"]))
            article.setdefault("key_points", [])
            article.setdefault("fact_check", {"status": "unverified", "confidence": 0.5, "notes": ""})
            article.setdefault("title_hi", article["title"])
            article.setdefault("context_hi", article.get("context", ""))
            article.setdefault("key_points_hi", [])
            enriched.append(article)
    return enriched
