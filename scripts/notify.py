"""
notify.py — Sends daily current affairs + metrics via Telegram and email.
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
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from metrics import Metrics

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


def _esc(text: str) -> str:
    """Escape for Telegram MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def send_telegram(
    articles: list[dict],
    date_str: str,
    pdf_path: Path | None,
    image_paths: list[Path],
    metrics: "Metrics | None" = None,
) -> None:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        print("⚠ TELEGRAM_CHAT_ID not set. Skipping Telegram.")
        return

    # ── Message 1: Headlines ──────────────────────────────────────────────────
    lines = [f"📰 *UPSC Current Affairs — {_esc(date_str)}*\n"]
    for i, art in enumerate(articles, 1):
        fc      = art.get("fact_check", {}).get("status", "")
        fc_icon = {"verified": "✅", "likely_accurate": "🔵",
                   "unverified": "🟡", "suspicious": "🔴"}.get(fc, "⚪")
        topics  = " · ".join(art.get("upsc_topics", [])[:2])
        lines.append(f"{i:02d}\\. {fc_icon} *{_esc(art['title'][:80])}*")
        if topics:
            lines.append(f"   _{_esc(topics)}_")
        lines.append("")

    site = os.environ.get("SITE_URL", "")
    if site:
        lines.append(f"🌐 [View on website]({site})")

    _tg("sendMessage", data={"chat_id": chat_id, "text": "\n".join(lines), "parse_mode": "MarkdownV2"})
    print("  ✅ Telegram: headlines sent")
    time.sleep(1)

    # ── Message 2: Metrics report ─────────────────────────────────────────────
    if metrics:
        report = metrics.telegram_report()
        _tg("sendMessage", data={
            "chat_id": chat_id,
            "text": f"<pre>{report}</pre>",
            "parse_mode": "HTML",
        })
        print("  ✅ Telegram: metrics report sent")
        time.sleep(1)

    # ── Message 3: PDF ────────────────────────────────────────────────────────
    if pdf_path and pdf_path.exists():
        with open(pdf_path, "rb") as f:
            _tg("sendDocument", data={
                "chat_id": chat_id,
                "caption": f"📄 UPSC Current Affairs — {date_str}",
            }, files={"document": (pdf_path.name, f, "application/pdf")})
        print("  ✅ Telegram: PDF sent")
        time.sleep(1)

    # ── Messages 4+: Images (batches of 10) ───────────────────────────────────
    valid_imgs = [p for p in image_paths if p.exists()]
    for start in range(0, len(valid_imgs), 10):
        batch = valid_imgs[start:start + 10]
        media, files = [], {}
        with contextlib.ExitStack() as stack:
            for j, img in enumerate(batch):
                key = f"img{j}"
                fh  = stack.enter_context(open(img, "rb"))
                media.append({"type": "photo", "media": f"attach://{key}"})
                files[key] = (img.name, fh, "image/png")
            media[0]["caption"] = f"🖼 Posts {start+1}–{start+len(batch)} of {len(valid_imgs)}"
            _tg("sendMediaGroup", data={"chat_id": chat_id, "media": json.dumps(media)}, files=files)
        print(f"  ✅ Telegram: images {start+1}–{start+len(batch)} sent")
        time.sleep(2)


def send_email(
    articles: list[dict],
    date_str: str,
    pdf_path: Path | None,
    metrics: "Metrics | None" = None,
) -> None:
    addr = os.environ.get("EMAIL_ADDRESS", "")
    pwd  = os.environ.get("EMAIL_PASSWORD", "")
    to   = os.environ.get("EMAIL_TO", addr)
    if not addr or not pwd:
        print("⚠ Email credentials not set. Skipping.")
        return

    # Build metrics section for email
    metrics_html = ""
    if metrics:
        m = metrics
        metrics_html = f"""
        <div style="background:#0D1B2A;color:#ccc;padding:20px 24px;margin-top:16px;border-radius:6px;font-family:monospace;font-size:12px">
          <div style="color:#FF9933;font-weight:bold;margin-bottom:10px">📊 Pipeline Metrics</div>
          <table style="border-collapse:collapse;width:100%">
            <tr><td style="padding:2px 12px 2px 0;color:#aaa">Run time</td>
                <td style="color:#fff">{int(m.pipeline_duration//60)}m {int(m.pipeline_duration%60)}s</td></tr>
            <tr><td style="padding:2px 12px 2px 0;color:#aaa">Articles fetched</td>
                <td style="color:#fff">{m._articles_fetched}</td></tr>
            <tr><td style="padding:2px 12px 2px 0;color:#aaa">Filtered (UPSC)</td>
                <td style="color:#fff">{m._articles_filtered}</td></tr>
            <tr><td style="padding:2px 12px 2px 0;color:#aaa">Total API calls</td>
                <td style="color:#fff">{m.total_calls}</td></tr>
            <tr><td style="padding:2px 12px 2px 0;color:#aaa">Total errors</td>
                <td style="color:#fff">{m.total_errors}</td></tr>
            <tr><td style="padding:2px 12px 2px 0;color:#aaa">Prompt tokens</td>
                <td style="color:#fff">{m.total_prompt_tokens:,}</td></tr>
            <tr><td style="padding:2px 12px 2px 0;color:#aaa">Output tokens</td>
                <td style="color:#fff">{m.total_comp_tokens:,}</td></tr>
            <tr><td style="padding:2px 12px 2px 0;color:#aaa">Total tokens</td>
                <td style="color:#fff"><strong style="color:#FF9933">{m.total_tokens:,}</strong></td></tr>
          </table>
          <div style="margin-top:12px;color:#FF9933;font-weight:bold">Per Provider</div>
          {''.join(
            f"<div style='margin-top:4px'><span style='color:#88aaff'>{name}</span>"
            f" — calls:{p['calls']} errors:{p['errors']} tokens:{p['total_tokens']:,}"
            f" avg:{p['avg_latency_s']}s</div>"
            for name, p in m.to_dict().get('providers', {}).items()
          )}
        </div>"""

    rows = ""
    for i, art in enumerate(articles, 1):
        status = art.get("fact_check", {}).get("status", "unverified")
        colors = {"verified":"#27ae60","likely_accurate":"#2980b9","unverified":"#f39c12","suspicious":"#e74c3c"}
        bc     = colors.get(status, "#888")
        topics = " · ".join(art.get("upsc_topics", [])[:3])
        ctx    = art.get("context", art.get("summary", ""))[:350]
        rows  += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:14px 8px;vertical-align:top;width:32px;color:#FF9933;font-weight:bold;font-size:16px">{i:02d}</td>
          <td style="padding:14px 8px">
            <a href="{art.get('link','#')}" style="color:#0D1B2A;text-decoration:none;font-weight:bold;font-size:14px">{art['title']}</a>
            <p style="color:#555;font-size:12px;margin:5px 0 4px">{ctx}</p>
            <span style="font-size:10px;color:#888">{art.get('source','')} · {art.get('published','')}</span>&nbsp;
            <span style="background:{bc};color:white;padding:1px 7px;border-radius:3px;font-size:10px">✓ {status}</span>
            <br><span style="color:#FF9933;font-size:10px">{topics}</span>
          </td>
        </tr>"""

    site = os.environ.get("SITE_URL", "")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:800px;margin:auto;background:#f5f5f5">
  <div style="background:#0D1B2A;padding:20px 28px">
    <h1 style="color:#FF9933;margin:0;font-size:20px">📰 UPSC Current Affairs</h1>
    <p style="color:#aaa;margin:4px 0 0;font-size:13px">{date_str} · {len(articles)} articles</p>
    {f'<a href="{site}" style="color:#88aaff;font-size:11px">{site}</a>' if site else ''}
  </div>
  <table style="width:100%;background:white;border-collapse:collapse">{rows}</table>
  {metrics_html}
  <p style="text-align:center;color:#aaa;font-size:10px;padding:12px">UPSC CA Agent — auto-generated</p>
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


def send_notifications(
    articles: list[dict],
    date_str: str,
    pdf_path: Path | None,
    image_paths: list[Path],
    metrics: "Metrics | None" = None,
) -> None:
    print("\n📣 Sending notifications...")
    send_telegram(articles, date_str, pdf_path, image_paths, metrics)
    send_email(articles, date_str, pdf_path, metrics)
