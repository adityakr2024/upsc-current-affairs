"""
generate_pdf.py — Bilingual two-column A4 PDF using ReportLab.
Left column: English  |  Right column: Hindi (Devanagari)

FIXED: removed duplicate BaseDocTemplate + double story population bug.
"""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ─── Colours ─────────────────────────────────────────────────────────────────
SAFFRON   = colors.HexColor("#FF9933")
NAVY      = colors.HexColor("#0D1B2A")
INDIA_GRN = colors.HexColor("#138808")
MID_GRAY  = colors.HexColor("#888888")
TEXT_DARK = colors.HexColor("#1C1C1C")

# ─── Font paths ───────────────────────────────────────────────────────────────
_NOTO_EN  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
_NOTO_ENB = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
_NOTO_HI_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]
_NOTO_HIB_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]

_FONTS_REGISTERED = False


def _first(paths: list[str]) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def register_fonts() -> tuple[str, str, str, str]:
    """Register fonts and return (en, en_bold, hi, hi_bold) font names."""
    global _FONTS_REGISTERED

    registered = pdfmetrics.getRegisteredFontNames()

    en_name  = "NotoEn"
    enb_name = "NotoEnBold"
    hi_name  = "NotoHi"
    hib_name = "NotoHiBold"

    if not _FONTS_REGISTERED:
        if _first([_NOTO_EN]) and en_name not in registered:
            pdfmetrics.registerFont(TTFont(en_name, _first([_NOTO_EN])))
        if _first([_NOTO_ENB]) and enb_name not in registered:
            pdfmetrics.registerFont(TTFont(enb_name, _first([_NOTO_ENB])))
        hi_path = _first(_NOTO_HI_CANDIDATES)
        if hi_path and hi_name not in registered:
            pdfmetrics.registerFont(TTFont(hi_name, hi_path))
        hib_path = _first(_NOTO_HIB_CANDIDATES)
        if hib_path and hib_name not in registered:
            pdfmetrics.registerFont(TTFont(hib_name, hib_path))
        _FONTS_REGISTERED = True

    registered = pdfmetrics.getRegisteredFontNames()
    return (
        en_name  if en_name  in registered else "Helvetica",
        enb_name if enb_name in registered else "Helvetica-Bold",
        hi_name  if hi_name  in registered else "Helvetica",
        hib_name if hib_name in registered else "Helvetica-Bold",
    )


def _build_styles(en: str, enb: str, hi: str, hib: str) -> dict:
    return {
        "num":     ParagraphStyle("num",     fontName=enb, fontSize=9,  textColor=SAFFRON, spaceAfter=2),
        "title_en":ParagraphStyle("title_en",fontName=enb, fontSize=11, textColor=TEXT_DARK, spaceAfter=4, leading=15),
        "body_en": ParagraphStyle("body_en", fontName=en,  fontSize=9,  textColor=TEXT_DARK, spaceAfter=3, leading=13),
        "kp_en":   ParagraphStyle("kp_en",   fontName=en,  fontSize=8.5,textColor=colors.HexColor("#333"),leftIndent=8, spaceAfter=2, leading=12),
        "meta_en": ParagraphStyle("meta_en", fontName=en,  fontSize=7.5,textColor=MID_GRAY, spaceAfter=2),
        "title_hi":ParagraphStyle("title_hi",fontName=hib, fontSize=11, textColor=TEXT_DARK, spaceAfter=4, leading=16),
        "body_hi": ParagraphStyle("body_hi", fontName=hi,  fontSize=9,  textColor=TEXT_DARK, spaceAfter=3, leading=14),
        "kp_hi":   ParagraphStyle("kp_hi",   fontName=hi,  fontSize=8.5,textColor=colors.HexColor("#333"),leftIndent=8, spaceAfter=2, leading=13),
    }


def _make_on_page(date_str: str, site_url: str):
    """Returns a ReportLab onPage callback for header/footer."""
    def on_page(canvas, doc):
        canvas.saveState()
        w, h = A4
        # Tricolor strip
        canvas.setFillColor(SAFFRON);      canvas.rect(0, h - 8,  w, 8,  fill=1, stroke=0)
        canvas.setFillColor(colors.white); canvas.rect(0, h - 13, w, 5,  fill=1, stroke=0)
        canvas.setFillColor(INDIA_GRN);    canvas.rect(0, h - 18, w, 5,  fill=1, stroke=0)
        # Header band
        canvas.setFillColor(NAVY);         canvas.rect(0, h - 50, w, 32, fill=1, stroke=0)
        canvas.setFillColor(colors.white); canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(1.5 * cm, h - 43, "UPSC CURRENT AFFAIRS")
        canvas.setFont("Helvetica", 10)
        canvas.drawRightString(w - 1.5 * cm, h - 43, date_str)
        # Column labels
        canvas.setFillColor(SAFFRON); canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(1.5 * cm,       h - 60, "ENGLISH")
        canvas.drawString(w / 2 + 0.5 * cm, h - 60, "हिन्दी")
        # Centre divider line
        canvas.setStrokeColor(colors.HexColor("#DDDDDD")); canvas.setLineWidth(0.5)
        canvas.line(w / 2, h - 64, w / 2, 1.4 * cm)
        # Footer
        canvas.setFillColor(MID_GRAY); canvas.setFont("Helvetica", 7)
        canvas.drawString(1.5 * cm, 0.7 * cm, f"{site_url}")
        canvas.drawCentredString(w / 2, 0.7 * cm, f"Page {doc.page}")
        canvas.drawRightString(w - 1.5 * cm, 0.7 * cm, "UPSC CA Agent")
        canvas.restoreState()
    return on_page


def create_pdf(articles: list[dict], date_str: str) -> Path | None:
    """Build the bilingual PDF and return its path."""
    en, enb, hi, hib = register_fonts()
    site_url = os.environ.get("SITE_URL", "upsc-ca.github.io")
    S = _build_styles(en, enb, hi, hib)

    out_dir  = Path("/tmp") / "upsc_pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"UPSC_CurrentAffairs_{date_str}.pdf"

    w, h         = A4
    top_margin   = 3.4 * cm
    bot_margin   = 1.4 * cm
    side_margin  = 1.4 * cm
    col_w_inner  = (w - 2 * side_margin - 0.6 * cm) / 2   # half width minus gutter

    # Single full-width frame — content is a Table with two columns
    frame = Frame(
        side_margin, bot_margin,
        w - 2 * side_margin, h - top_margin - bot_margin,
        id="main", showBoundary=0,
    )
    template = PageTemplate(id="main", frames=[frame], onPage=_make_on_page(date_str, site_url))
    doc = BaseDocTemplate(str(out_path), pagesize=A4, pageTemplates=[template])

    # ── Build story ───────────────────────────────────────────────────────────
    story = []

    for i, art in enumerate(articles, 1):
        # ── English cell ──────────────────────────────────────────────────────
        en_cell = [
            Paragraph(f"#{i:02d}  ·  {art.get('source', '')}", S["num"]),
            Paragraph(art.get("title", ""), S["title_en"]),
            Paragraph(art.get("context", art.get("summary", ""))[:600], S["body_en"]),
        ]
        for kp in art.get("key_points", [])[:4]:
            en_cell.append(Paragraph(f"▸ {kp}", S["kp_en"]))
        fc_status = art.get("fact_check", {}).get("status", "unverified")
        topics    = ", ".join(art.get("upsc_topics", [])[:3])
        en_cell.append(Paragraph(
            f"Topics: {topics}  |  ✓ {fc_status}",
            S["meta_en"]
        ))

        # ── Hindi cell ────────────────────────────────────────────────────────
        hi_cell = [
            Paragraph(f"#{i:02d}", S["num"]),
            Paragraph(art.get("title_hi", art.get("title", "")), S["title_hi"]),
            Paragraph(art.get("context_hi", art.get("context", ""))[:600], S["body_hi"]),
        ]
        for kp in art.get("key_points_hi", [])[:4]:
            hi_cell.append(Paragraph(f"▸ {kp}", S["kp_hi"]))

        # ── Two-column table row ──────────────────────────────────────────────
        tbl = Table(
            [[en_cell, hi_cell]],
            colWidths=[col_w_inner, col_w_inner],
            splitByRow=True,
        )
        tbl.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (0, -1),  12),   # gutter on EN side
            ("RIGHTPADDING",  (1, 0), (1, -1),  0),
            ("LINEAFTER",     (0, 0), (0, -1),  0.5, colors.HexColor("#DDDDDD")),
            ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
        ]))

        story.append(tbl)
        story.append(HRFlowable(
            width="100%", thickness=1,
            color=colors.HexColor("#ECECEC"),
            spaceBefore=6, spaceAfter=6,
        ))

    doc.build(story)

    size_kb = out_path.stat().st_size // 1024
    print(f"\n📄 PDF saved: {out_path}  ({size_kb} KB)")
    return out_path
