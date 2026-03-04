"""
generate_image.py — Creates social-media images (1080×1080) for each article.
Uses Pillow with system fonts (Noto / Liberation / DejaVu).
Design: Dark editorial style with saffron accent.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ─── Palette ─────────────────────────────────────────────────────────────────
BG_TOP    = (13, 17, 27)
BG_BOT    = (22, 32, 52)
SAFFRON   = (255, 153, 51)
WHITE     = (255, 255, 255)
LIGHT     = (210, 218, 235)
MUTED     = (120, 135, 160)
INDIA_GRN = (19, 136, 8)


# ─── Font helpers ─────────────────────────────────────────────────────────────
def _find_font(bold: bool = False, size: int = 32):
    """Find the best available system font. Always returns a usable font object."""
    candidates = (
        [
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)

    # Search system for any .ttf as last resort before load_default
    for pattern in ["/usr/share/fonts/**/*.ttf"]:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            try:
                return ImageFont.truetype(matches[0], size)
            except Exception:
                pass

    # Final fallback — load_default() returns a bitmap font (no size param in Pillow ≥10)
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    """Safely measure text width regardless of font type."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except Exception:
        return len(text) * 10   # rough fallback


def _line_height(font, default: int = 24) -> int:
    """Safely get line height for a font."""
    try:
        bbox = font.getbbox("Ag")
        return (bbox[3] - bbox[1]) + 6
    except Exception:
        return default


def _wrap(text: str, font, max_w: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Word-wrap text to fit within max_w pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if _text_width(draw, test, font) <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        ratio = y / h
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * ratio)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * ratio)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def create_article_image(
    article: dict,
    index: int,
    total: int,
    output_path: Path,
    site_url: str = "",
) -> Path:
    """Render a single 1080×1080 social-media card."""
    W, H = 1080, 1080
    PAD = 72

    # Background
    img  = _gradient(W, H)
    draw = ImageDraw.Draw(img, "RGBA")

    # Diagonal grid
    for x in range(0, W + H, 80):
        draw.line([(x, 0), (x - H, H)], fill=(255, 255, 255, 12), width=1)

    # ── Tricolor strip ────────────────────────────────────────────────────────
    draw.rectangle([0, 0,  W, 8],  fill=SAFFRON)
    draw.rectangle([0, 8,  W, 13], fill=WHITE)
    draw.rectangle([0, 13, W, 18], fill=INDIA_GRN)

    # ── Load fonts ────────────────────────────────────────────────────────────
    f_label  = _find_font(bold=True,  size=22)
    f_meta   = _find_font(bold=False, size=20)
    f_number = _find_font(bold=True,  size=52)
    f_head   = _find_font(bold=True,  size=46)
    f_body   = _find_font(bold=False, size=30)
    f_tag    = _find_font(bold=True,  size=22)
    f_foot   = _find_font(bold=False, size=22)

    # ── Header row ────────────────────────────────────────────────────────────
    y = 42
    draw.text((PAD, y), "UPSC CURRENT AFFAIRS", font=f_label, fill=SAFFRON)
    from datetime import date as _date
    date_str = article.get("published", _date.today().isoformat())
    draw.text((W - PAD - 160, y), date_str, font=f_meta, fill=MUTED)

    y += 38
    draw.rectangle([PAD, y, W - PAD, y + 2], fill=(SAFFRON[0], SAFFRON[1], SAFFRON[2], 80))

    # ── Number badge ──────────────────────────────────────────────────────────
    y += 22
    bx, by = PAD, y
    draw.ellipse([bx, by, bx + 72, by + 72], fill=SAFFRON)
    num_txt = str(index)
    try:
        nb  = draw.textbbox((0, 0), num_txt, font=f_number)
        nx  = bx + (72 - (nb[2] - nb[0])) // 2
        ny  = by + (72 - (nb[3] - nb[1])) // 2
    except Exception:
        nx, ny = bx + 18, by + 14
    draw.text((nx, ny), num_txt, font=f_number, fill=BG_TOP)
    draw.text((bx + 84, by + 18), f"of {total}", font=f_meta, fill=MUTED)

    # ── Source tag ────────────────────────────────────────────────────────────
    src_txt = f"  {article.get('source','')} · {article.get('category','')}  "
    src_w   = _text_width(draw, src_txt, f_tag) + 16
    sx      = W - PAD - src_w
    draw.rounded_rectangle([sx, by + 10, sx + src_w, by + 48],
                           radius=8, fill=(SAFFRON[0], SAFFRON[1], SAFFRON[2], 40))
    draw.text((sx + 8, by + 14), src_txt, font=f_tag, fill=SAFFRON)

    # ── Headline ──────────────────────────────────────────────────────────────
    y = by + 100
    lh_head  = _line_height(f_head, 58)
    for line in _wrap(article["title"], f_head, W - 2 * PAD, draw)[:4]:
        draw.text((PAD, y), line, font=f_head, fill=WHITE)
        y += lh_head
    y += 10

    draw.rectangle([PAD, y, W - PAD, y + 2], fill=(255, 255, 255, 30))
    y += 20

    # ── Context ───────────────────────────────────────────────────────────────
    context = article.get("context", article.get("summary", ""))[:400]
    lh_body = _line_height(f_body, 42)
    for line in _wrap(context, f_body, W - 2 * PAD, draw)[:6]:
        draw.text((PAD, y), line, font=f_body, fill=LIGHT)
        y += lh_body
    y += 16

    # ── Key points ────────────────────────────────────────────────────────────
    points = article.get("key_points", [])[:3]
    if points and y < H - 220:
        draw.text((PAD, y), "KEY POINTS", font=f_tag, fill=SAFFRON)
        y += 30
        lh_meta = _line_height(f_meta, 28)
        for pt in points:
            if y > H - 160:
                break
            for pl in _wrap(f"▸ {pt}", f_meta, W - 2 * PAD - 20, draw)[:2]:
                draw.text((PAD + 10, y), pl, font=f_meta, fill=LIGHT)
                y += lh_meta

    # ── Topic tags ────────────────────────────────────────────────────────────
    tag_y, tag_x = H - 130, PAD
    for topic in article.get("upsc_topics", [])[:3]:
        t_w = _text_width(draw, f" {topic} ", f_tag) + 12
        draw.rounded_rectangle([tag_x, tag_y, tag_x + t_w, tag_y + 36],
                               radius=6, outline=SAFFRON, width=1)
        draw.text((tag_x + 6, tag_y + 6), f" {topic} ", font=f_tag, fill=SAFFRON)
        tag_x += t_w + 12

    # ── Fact-check badge ──────────────────────────────────────────────────────
    status = article.get("fact_check", {}).get("status", "unverified")
    fc_colors = {
        "verified": (50, 200, 80), "likely_accurate": (100, 180, 255),
        "unverified": (200, 200, 50), "suspicious": (255, 80, 80),
    }
    draw.text((W - PAD - 220, tag_y + 4),
              f"✓ {status.replace('_', ' ').title()}",
              font=f_tag, fill=fc_colors.get(status, MUTED))

    # ── Footer ────────────────────────────────────────────────────────────────
    draw.rectangle([0, H - 72, W, H], fill=(10, 15, 25))
    draw.text((PAD, H - 50), f"🌐 {site_url or 'upsc-ca.github.io'}", font=f_foot, fill=MUTED)
    draw.text((W - PAD - 280, H - 50), "Daily UPSC Current Affairs", font=f_foot, fill=MUTED)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG", optimize=True)
    return output_path


def create_social_posts(articles: list[dict], date_str: str) -> list[Path]:
    """Generate one image per article. Returns list of image paths."""
    site_url = os.environ.get("SITE_URL", "upsc-ca.github.io")
    out_dir  = Path("/tmp") / "upsc_images" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    total = len(articles)

    print(f"\n🖼  Generating {total} social media images...")
    for i, article in enumerate(articles, 1):
        out_path = out_dir / f"{date_str}_{i:02d}.png"
        try:
            create_article_image(article, i, total, out_path, site_url)
            paths.append(out_path)
            print(f"  ✅ Image {i}/{total}: {out_path.name}")
        except Exception as e:
            print(f"  ❌ Image {i} failed: {e}")
    return paths
