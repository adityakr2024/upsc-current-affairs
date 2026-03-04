"""
fetch_rss.py — Fetches and cleans articles from RSS feeds.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup

RSS_FEEDS = [
    {
        "url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "source": "The Hindu",
        "category": "National",
        "source_weight": 8,
    },
    {
        "url": "https://www.thehindu.com/news/international/feeder/default.rss",
        "source": "The Hindu",
        "category": "International",
        "source_weight": 7,
    },
    {
        "url": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1&reg=1",
        "source": "PIB",
        "category": "Government",
        "source_weight": 10,
    },
]


def clean_html(raw: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "lxml")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_published(entry) -> str:
    """Return ISO date string for the article publication time."""
    for field in ("published", "updated"):
        val = entry.get(field)
        if val:
            try:
                dt = parsedate_to_datetime(val)
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                pass
    return datetime.utcnow().strftime("%Y-%m-%d")


def fetch_all_feeds() -> list[dict]:
    """Fetch all configured RSS feeds and return a deduplicated article list."""
    articles: list[dict] = []
    seen_ids: set[str] = set()

    for config in RSS_FEEDS:
        try:
            # feedparser handles redirects and encoding automatically
            feed = feedparser.parse(
                config["url"],
                request_headers={"User-Agent": "UPSC-CA-Bot/1.0"},
            )
            if feed.bozo and not feed.entries:
                print(f"⚠ Feed parse error for {config['source']}: {feed.bozo_exception}")
                continue

            for entry in feed.entries:
                title = clean_html(entry.get("title", "")).strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue

                uid = hashlib.md5(link.encode()).hexdigest()[:10]
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)

                summary = clean_html(
                    entry.get("summary", "") or entry.get("description", "")
                )

                articles.append(
                    {
                        "id": uid,
                        "title": title,
                        "link": link,
                        "summary": summary[:800],   # cap length
                        "source": config["source"],
                        "category": config["category"],
                        "source_weight": config["source_weight"],
                        "published": parse_published(entry),
                    }
                )

            print(f"✅ {config['source']} ({config['category']}): {len(feed.entries)} entries")

        except Exception as exc:
            print(f"❌ Error fetching {config['url']}: {exc}")

    print(f"\n📦 Total articles fetched: {len(articles)}")
    return articles
