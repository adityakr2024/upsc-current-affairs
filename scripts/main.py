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

sys.path.insert(0, str(Path(__file__).parent))

from fetch_rss import fetch_all_feeds
from filter_ca import filter_and_rank
from generate_content import generate_content
from generate_image import create_social_posts
from generate_pdf import create_pdf
from metrics import get_metrics, reset_metrics
from notify import send_notifications

DOCS_DATA = Path(__file__).parent.parent / "docs" / "data"


def save_website_data(articles: list[dict], today: str) -> None:
    DOCS_DATA.mkdir(parents=True, exist_ok=True)

    clean = [
        {k: v for k, v in art.items() if not k.startswith("_")}
        for art in articles
    ]

    daily_file = DOCS_DATA / f"{today}.json"
    daily_file.write_text(
        json.dumps({"date": today, "articles": clean}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    index_file = DOCS_DATA / "index.json"
    try:
        if index_file.exists():
            raw = index_file.read_text(encoding="utf-8").strip()
            if not raw:
                raise ValueError("empty")
            index = json.loads(raw)
            if not isinstance(index, dict) or "dates" not in index:
                raise ValueError("malformed")
        else:
            index = {"dates": []}
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"  ⚠ index.json reset ({exc})")
        index = {"dates": []}

    if today not in index["dates"]:
        index["dates"].insert(0, today)
    index["dates"] = sorted(set(index["dates"]), reverse=True)[:90]
    index_file.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  💾 Saved → {daily_file.name}")


def main() -> int:
    reset_metrics()
    m     = get_metrics()
    today = date.today().isoformat()

    print(f"\n{'='*60}")
    print(f"  UPSC Current Affairs Pipeline — {today}")
    print(f"{'='*60}\n")

    try:
        # ── Step 1: Fetch ─────────────────────────────────────────────────────
        t1 = m.start_step("1. Fetch RSS")
        print("📡 Step 1: Fetching RSS feeds...")
        articles = fetch_all_feeds()
        t1.stop(success=bool(articles))
        m.set_articles_fetched(len(articles))
        if not articles:
            print("❌ No articles fetched.")
            return 1

        # ── Step 2: Filter ────────────────────────────────────────────────────
        t2 = m.start_step("2. Filter & rank")
        print("\n🔍 Step 2: Filtering for UPSC current affairs...")
        top_articles = filter_and_rank(articles, top_n=15)
        t2.stop(success=bool(top_articles))
        m.set_articles_filtered(len(top_articles))
        if not top_articles:
            print("❌ No articles passed filter.")
            return 1

        # ── Step 3: AI Enrichment ─────────────────────────────────────────────
        t3 = m.start_step("3. AI enrichment")
        print("\n🤖 Step 3: AI enrichment...")
        enriched = generate_content(top_articles)
        t3.stop(success=bool(enriched))
        m.set_articles_enriched(len(enriched))
        if not enriched:
            print("❌ Enrichment failed.")
            return 1

        # ── Step 4: Save website data ─────────────────────────────────────────
        t4 = m.start_step("4. Save website data")
        print("\n💾 Step 4: Updating website data...")
        save_website_data(enriched, today)
        t4.stop()

        # ── Step 5: Social media images ───────────────────────────────────────
        t5 = m.start_step("5. Generate images")
        print("\n🖼  Step 5: Generating social media images...")
        image_paths = create_social_posts(enriched, today)
        m.set_images_generated(len(image_paths))
        t5.stop(success=bool(image_paths))

        # ── Step 6: Bilingual PDF ─────────────────────────────────────────────
        t6 = m.start_step("6. Generate PDF")
        print("\n📄 Step 6: Generating bilingual PDF...")
        pdf_path = create_pdf(enriched, today)
        t6.stop(success=pdf_path is not None)

        # ── Step 7: Notify ────────────────────────────────────────────────────
        t7 = m.start_step("7. Send notifications")
        send_notifications(enriched, today, pdf_path, image_paths, m)
        t7.stop()

        # ── Final summary ─────────────────────────────────────────────────────
        print(f"\n{'='*60}")
        print(m.telegram_report())
        print(f"{'='*60}\n")
        return 0

    except Exception:
        print("\n❌ FATAL PIPELINE ERROR:")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
