"""
main.py — UPSC Current Affairs Daily Pipeline Orchestrator
Runs daily via GitHub Actions at 6 AM IST.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import date
from pathlib import Path

# ── Add scripts dir to path ───────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from fetch_rss         import fetch_all_feeds
from filter_ca         import filter_and_rank
from generate_content  import generate_content
from generate_image    import create_social_posts
from generate_pdf      import create_pdf
from notify            import send_notifications


DOCS_DATA = Path(__file__).parent.parent / "docs" / "data"


def save_website_data(articles: list[dict], today: str) -> None:
    """Write JSON data consumed by the static website."""
    DOCS_DATA.mkdir(parents=True, exist_ok=True)

    # Sanitise: strip internal scoring keys before writing to public JSON
    clean = [
        {k: v for k, v in art.items() if not k.startswith("_")}
        for art in articles
    ]

    # Daily file
    daily_file = DOCS_DATA / f"{today}.json"
    daily_file.write_text(
        json.dumps({"date": today, "articles": clean}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Update the index (most recent 90 days).
    # Wrapped in try/except so a corrupt/missing index.json never kills the pipeline.
    index_file = DOCS_DATA / "index.json"
    try:
        if index_file.exists():
            raw = index_file.read_text(encoding="utf-8").strip()
            if not raw:
                raise ValueError("Empty index.json")
            index = json.loads(raw)
            if not isinstance(index, dict) or "dates" not in index:
                raise ValueError("Malformed index.json structure")
        else:
            index = {"dates": []}
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"  ⚠ index.json unreadable ({exc}) — resetting to empty.")
        index = {"dates": []}

    if today not in index["dates"]:
        index["dates"].insert(0, today)
    index["dates"] = sorted(set(index["dates"]), reverse=True)[:90]

    index_file.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n💾 Website data saved → {daily_file}")


def main() -> int:
    """Run the full pipeline. Returns 0 on success, non-zero on failure."""
    today = date.today().isoformat()
    print(f"\n{'='*60}")
    print(f"  UPSC Current Affairs Pipeline — {today}")
    print(f"{'='*60}\n")

    try:
        # ── Step 1: Fetch RSS ─────────────────────────────────────────────────
        print("📡 Step 1: Fetching RSS feeds...")
        articles = fetch_all_feeds()
        if not articles:
            print("❌ No articles fetched. Aborting.")
            return 1

        # ── Step 2: Filter & rank ─────────────────────────────────────────────
        print("\n🔍 Step 2: Filtering for UPSC current affairs...")
        top_articles = filter_and_rank(articles, top_n=15)
        if not top_articles:
            print("❌ No articles passed the UPSC filter. Aborting.")
            return 1

        # ── Step 3: AI enrichment ─────────────────────────────────────────────
        print("\n🤖 Step 3: AI enrichment (context / key points / Hindi / fact-check)...")
        enriched = generate_content(top_articles)
        if not enriched:
            print("❌ Enrichment returned empty list. Aborting.")
            return 1

        # ── Step 4: Save website JSON ─────────────────────────────────────────
        print("\n💾 Step 4: Updating website data...")
        save_website_data(enriched, today)

        # ── Step 5: Social-media images ───────────────────────────────────────
        print("\n🖼  Step 5: Generating social media images...")
        image_paths = create_social_posts(enriched, today)

        # ── Step 6: Bilingual PDF ─────────────────────────────────────────────
        print("\n📄 Step 6: Generating bilingual PDF...")
        pdf_path = create_pdf(enriched, today)

        # ── Step 7: Notify ────────────────────────────────────────────────────
        send_notifications(enriched, today, pdf_path, image_paths)

        print(f"\n{'='*60}")
        print(f"  ✨ Pipeline complete for {today}")
        print(f"{'='*60}\n")
        return 0

    except Exception:
        print("\n❌ FATAL PIPELINE ERROR:")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
