"""
notify.py — Sends daily current affairs via Telegram and email.

Telegram:
  - Summary message with headlines
  - PDF as document
  - Social media images as a media group

Email:
  - HTML email with article summaries
  - PDF attached
"""

from __future__ import annotations

import contextlib
import json
import os
import smtplib
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _tg(method: str, **kwargs) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {}
    url = TELEGRAM_API.format(token=token, method=method)
    try:
        r = requests.post(url, timeout=30, **kwargs)
        return r.json()
    except Exception as e:
        print(f"  Telegram error ({method}): {e}")
        return {}


def send_telegram(articles: list[dict], date_str: str, pdf_path: Path | None, image_paths: list[Path]):
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        print("⚠ TELEGRAM_CHAT_ID not set. Skipping Telegram.")
        return

    # ── 1. Summary message ────────────────────────────────────────────────────
    lines = [f"📰 *UPSC Current Affairs — {date_str}*\n"]
    for i, art in enumerate(articles, 1):
        fc = art.get("fact_check", {}).get("status", "")
        fc_icon = {"verified": "✅", "likely_accurate": "🔵", "unverified": "🟡", "suspicious": "🔴"}.get(fc, "⚪")
        topics = " · ".join(art.get("upsc_topics", [])[:2])
        lines.append(f"{i:02d}\\. {fc_icon} *{_esc(art['title'][:80])}*")
        lines.append(f"   _{_esc(topics)}_\n")

    site = os.environ.get("SITE_URL", "")
    if site:
        lines.append(f"\n🌐 [Full website]({site})")

    msg = "\n".join(lines)
    _tg("sendMessage", data={"chat_id": chat_id, "text": msg, "parse_mode": "MarkdownV2"})
    print("  ✅ Telegram summary sent")
    time.sleep(1)

    # ── 2. PDF document ───────────────────────────────────────────────────────
    if pdf_path and pdf_path.exists():
        with open(pdf_path, "rb") as f:
            _tg("sendDocument", data={
                "chat_id": chat_id,
                "caption": f"📄 UPSC Current Affairs PDF — {date_str}",
            }, files={"document": (pdf_path.name, f, "application/pdf")})
        print("  ✅ Telegram PDF sent")
        time.sleep(1)

    # ── 3. Images (batched in groups of 10) ──────────────────────────────────
    valid_imgs = [p for p in image_paths if p.exists()]
    for batch_start in range(0, len(valid_imgs), 10):
        batch = valid_imgs[batch_start:batch_start + 10]
        media = []
        files = {}

        # Use ExitStack so all file handles are guaranteed closed on error
        with contextlib.ExitStack() as stack:
            for j, img in enumerate(batch):
                key = f"img{j}"
                fh  = stack.enter_context(open(img, "rb"))
                media.append({"type": "photo", "media": f"attach://{key}"})
                files[key] = (img.name, fh, "image/png")

            media[0]["caption"] = f"🖼 Social media posts {batch_start + 1}–{batch_start + len(batch)}"
            _tg("sendMediaGroup", data={"chat_id": chat_id, "media": json.dumps(media)}, files=files)

        print(f"  ✅ Telegram images {batch_start + 1}–{batch_start + len(batch)} sent")
        time.sleep(2)


def _esc(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def send_email(articles: list[dict], date_str: str, pdf_path: Path | None):
    addr = os.environ.get("EMAIL_ADDRESS", "")
    pwd  = os.environ.get("EMAIL_PASSWORD", "")
    to   = os.environ.get("EMAIL_TO", addr)
    if not addr or not pwd:
        print("⚠ Email credentials not set. Skipping email.")
        return

    # ── HTML body ─────────────────────────────────────────────────────────────
    rows = ""
    for i, art in enumerate(articles, 1):
        fc     = art.get("fact_check", {})
        status = fc.get("status", "unverified")
        badge_colors = {
            "verified": "#27ae60", "likely_accurate": "#2980b9",
            "unverified": "#f39c12", "suspicious": "#e74c3c",
        }
        badge_color = badge_colors.get(status, "#888")
        topics  = " · ".join(art.get("upsc_topics", [])[:3])
        context = art.get("context", art.get("summary", ""))[:400]
        rows += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:16px 8px;vertical-align:top;width:36px;color:#FF9933;font-weight:bold;font-size:18px">{i:02d}</td>
          <td style="padding:16px 8px">
            <a href="{art.get('link','#')}" style="color:#0D1B2A;text-decoration:none;font-weight:bold;font-size:15px">{art['title']}</a>
            <p style="color:#555;font-size:13px;margin:6px 0">{context}</p>
            <span style="font-size:11px;color:#888">{art.get('source','')} · {art.get('published','')}</span>
            &nbsp;&nbsp;
            <span style="background:{badge_color};color:white;padding:2px 8px;border-radius:4px;font-size:10px">✓ {status}</span>
            <br><span style="color:#FF9933;font-size:11px">{topics}</span>
          </td>
        </tr>"""

    site = os.environ.get("SITE_URL", "")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:800px;margin:auto;background:#f9f9f9">
  <div style="background:#0D1B2A;padding:24px 32px">
    <h1 style="color:#FF9933;margin:0;font-size:22px">UPSC Current Affairs</h1>
    <p style="color:#aaa;margin:4px 0 0">{date_str} · Top {len(articles)} of the day</p>
    {f'<a href="{site}" style="color:#88aaff;font-size:12px">{site}</a>' if site else ''}
  </div>
  <table style="width:100%;background:white;border-collapse:collapse">{rows}</table>
  <p style="text-align:center;color:#aaa;font-size:11px;padding:16px">
    Generated automatically by UPSC CA Agent
  </p>
</body></html>"""

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"📰 UPSC Current Affairs — {date_str}"
    msg["From"]    = addr
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))

    if pdf_path and pdf_path.exists():
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=pdf_path.name)
        part["Content-Disposition"] = f'attachment; filename="{pdf_path.name}"'
        msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(addr, pwd)
            server.sendmail(addr, to, msg.as_string())
        print("  ✅ Email sent")
    except Exception as e:
        print(f"  ❌ Email failed: {e}")


def send_notifications(articles: list[dict], date_str: str, pdf_path: Path | None, image_paths: list[Path]):
    print("\n📣 Sending notifications...")
    send_telegram(articles, date_str, pdf_path, image_paths)
    send_email(articles, date_str, pdf_path)
