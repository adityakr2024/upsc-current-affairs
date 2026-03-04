"""
filter_ca.py — Smart UPSC current-affairs filter.

Algorithm:
  1. Hard-exclude articles matching noise keywords (sports, entertainment, etc.)
  2. Score each article across UPSC syllabus topics using weighted keyword matching.
  3. Bonus scores for government actions, institutions, treaties, PIB source.
  4. Apply topic diversity cap (max 3 per topic) to ensure broad coverage.
  5. Return top N articles sorted by score.

Threshold: score >= 15 to qualify as current affairs.
"""

from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# UPSC Syllabus Topic Map
# Each topic has keywords and a weight (max score contribution per article).
# ─────────────────────────────────────────────────────────────────────────────
UPSC_TOPICS: dict[str, dict] = {
    "Polity & Governance": {
        "weight": 10,
        "keywords": [
            "constitution", "constitutional", "supreme court", "high court", "parliament",
            "lok sabha", "rajya sabha", "president", "governor", "cabinet", "ministry",
            "legislation", "amendment", "ordinance", "judicial", "fundamental rights",
            "directive principles", "preamble", "federalism", "centre-state",
            "tribunal", "election commission", "comptroller", "accountant general",
            "attorney general", "advocate general", "ombudsman", "lokpal", "cag",
        ],
    },
    "Economy": {
        "weight": 9,
        "keywords": [
            "gdp", "inflation", "rbi", "monetary policy", "repo rate", "fiscal deficit",
            "budget", "tax", "gst", "fdi", "forex", "balance of payments", "trade deficit",
            "export", "import", "msme", "startup", "banking", "nbfc", "sebi",
            "niti aayog", "economic survey", "recession", "growth rate", "unemployment",
            "pli scheme", "disinvestment", "privatisation", "sovereign", "debt",
        ],
    },
    "International Relations": {
        "weight": 9,
        "keywords": [
            "bilateral", "multilateral", "treaty", "agreement", "summit", "united nations",
            "un", "who", "imf", "world bank", "nato", "brics", "sco", "g20", "g7",
            "asean", "saarc", "quad", "foreign policy", "diplomatic", "sanctions",
            "geopolitics", "mou", "protocol", "convention", "accord",
            "india-us", "india-china", "india-russia", "india-pakistan", "india-japan",
        ],
    },
    "Environment & Ecology": {
        "weight": 8,
        "keywords": [
            "climate change", "carbon", "emission", "biodiversity", "wildlife", "forest",
            "pollution", "renewable energy", "solar", "green hydrogen", "cop", "unfccc",
            "ngt", "protected area", "tiger reserve", "elephant corridor", "wetland",
            "ramsar", "mangrove", "coral reef", "deforestation", "ozone", "glacier",
            "disaster management", "cyclone", "flood", "drought", "earthquake",
        ],
    },
    "Science & Technology": {
        "weight": 8,
        "keywords": [
            "isro", "drdo", "space", "missile", "satellite", "nuclear", "artificial intelligence",
            "machine learning", "5g", "6g", "semiconductor", "quantum", "biotechnology",
            "genome", "vaccine", "drug", "clinical trial", "patent", "research", "iit",
            "iiser", "csir", "dbt", "dst", "technology policy", "digital", "cyber",
            "launch vehicle", "chandrayaan", "aditya", "gaganyaan",
        ],
    },
    "Social Issues": {
        "weight": 7,
        "keywords": [
            "poverty", "education policy", "health policy", "nutrition", "malnutrition",
            "welfare scheme", "women empowerment", "child", "tribal", "scheduled caste",
            "scheduled tribe", "obc", "reservation", "nfhs", "census", "human development",
            "gender", "disability", "labour rights", "minimum wage", "social security",
            "ayushman", "pm-jan dhan", "beti bachao", "poshan",
        ],
    },
    "Defence & Security": {
        "weight": 8,
        "keywords": [
            "army", "navy", "air force", "coast guard", "defence ministry", "military",
            "border security", "lac", "loc", "ceasefire", "joint exercise", "procurement",
            "indigenisation", "atmanirbhar defence", "terrorism", "naxal", "maoism",
            "internal security", "crpf", "bsf", "cisf", "intelligence",
        ],
    },
    "Agriculture & Rural": {
        "weight": 7,
        "keywords": [
            "farmer", "agriculture", "horticulture", "crop", "msp", "irrigation",
            "kisan", "rural", "food security", "fci", "pds", "fertilizer", "organic farming",
            "pm-kisan", "soil health", "cold storage", "agri infrastructure", "animal husbandry",
            "fisheries", "aquaculture", "e-nam", "fpo",
        ],
    },
    "Infrastructure": {
        "weight": 6,
        "keywords": [
            "highway", "expressway", "railway", "bullet train", "metro", "port", "airport",
            "sagarmala", "bharatmala", "dedicated freight corridor", "logistics", "pm gati shakti",
            "smart city", "amrut", "urban", "housing", "pradhan mantri awas",
        ],
    },
    "Schemes & Initiatives": {
        "weight": 9,
        "keywords": [
            "scheme", "mission", "programme", "yojana", "abhiyan", "campaign", "initiative",
            "launches", "launched", "inaugurated", "inaugurates", "roll out", "implement",
            "approved by cabinet", "cabinet approves", "cabinet clears",
        ],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Hard-exclude patterns — articles matching ANY of these are dropped immediately
# ─────────────────────────────────────────────────────────────────────────────
EXCLUDE_PATTERNS: list[str] = [
    r"\bcricket\b", r"\bipl\b", r"\btest match\b", r"\bone[- ]day\b", r"\bodi\b",
    r"\bbollywood\b", r"\bfilm\b", r"\bmovie\b", r"\bactor\b", r"\bactress\b",
    r"\bentertainment\b", r"\bgossip\b", r"\blifestyle\b", r"\bhoroscope\b",
    r"\brecipe\b", r"\bfashion week\b", r"\bcelebrity\b",
    r"\bstock market\b", r"\bsensex\b", r"\bnifty\b", r"\bshare price\b",
    r"\bweather forecast\b", r"\btraffic jam\b",
    r"\bcrime\b.*\bgang\b",   # gang crime (not policy)
    r"\bhit[- ]and[- ]run\b",
    r"\bfootball\b.*\bleague\b", r"\bchampions league\b",
]

# ─────────────────────────────────────────────────────────────────────────────
# Government-action phrases that strongly signal current-affairs relevance
# ─────────────────────────────────────────────────────────────────────────────
ACTION_PHRASES: list[str] = [
    "cabinet approves", "parliament passes", "lok sabha passes", "rajya sabha passes",
    "president assents", "government launches", "government announces", "india signs",
    "mou signed", "agreement signed", "bill introduced", "bill tabled", "bill passed",
    "ordinance promulgated", "policy announced", "scheme launched", "mission launched",
    "act notified", "amendment introduced", "inaugural", "inaugurates",
]

INSTITUTIONS: list[str] = [
    "supreme court", "high court", "niti aayog", "rbi", "sebi", "cci", "nhrc", "ncw",
    "election commission", "isro", "drdo", "nhpc", "ail", "ngt", "cag", "cbi", "ed",
    "upsc", "ssc", "uidai", "trai", "irda", "pfrda", "fssai", "cpcb",
]


# ─────────────────────────────────────────────────────────────────────────────
# Scoring logic
# ─────────────────────────────────────────────────────────────────────────────
def _text(article: dict) -> str:
    return (article["title"] + " " + article.get("summary", "")).lower()


def _title(article: dict) -> str:
    return article["title"].lower()


def is_excluded(article: dict) -> bool:
    """Return True if the article matches any hard-exclude pattern."""
    text = _text(article)
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def score_article(article: dict) -> tuple[int, list[str]]:
    """
    Returns (score, matched_topics).
    Higher score = more relevant to UPSC current affairs.
    """
    text = _text(article)
    title = _title(article)
    score = 0
    matched_topics: list[str] = []

    # ── Source bonus ──────────────────────────────────────────────────────────
    score += article.get("source_weight", 0)

    # ── Government-action phrases in title (strong signal) ───────────────────
    for phrase in ACTION_PHRASES:
        if phrase in title:
            score += 8
            break  # Count once

    # ── Institutions mentioned anywhere ──────────────────────────────────────
    for inst in INSTITUTIONS:
        if inst in text:
            score += 3
            break

    # ── UPSC topic keyword matching ───────────────────────────────────────────
    for topic_name, data in UPSC_TOPICS.items():
        hits = sum(1 for kw in data["keywords"] if kw in text)
        if hits > 0:
            contribution = min(hits * 2, data["weight"])
            score += contribution
            matched_topics.append(topic_name)

    # ── India-relevance bonus for international news ──────────────────────────
    if article["category"] == "International" and "india" in text:
        score += 4

    return score, matched_topics


def filter_and_rank(articles: list[dict], top_n: int = 15) -> list[dict]:
    """
    Apply UPSC filter, score, enforce topic diversity, return top N.
    """
    SCORE_THRESHOLD = 15
    MAX_PER_TOPIC = 4   # Diversity cap per primary topic

    scored: list[tuple[int, list[str], dict]] = []

    for article in articles:
        if is_excluded(article):
            continue
        sc, topics = score_article(article)
        if sc >= SCORE_THRESHOLD:
            article["_score"] = sc
            article["upsc_topics"] = topics[:3]   # Top 3 matched topics
            scored.append((sc, topics, article))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Topic diversity: don't flood with one topic
    topic_count: dict[str, int] = {}
    selected: list[dict] = []

    for sc, topics, article in scored:
        primary_topic = topics[0] if topics else "General"
        if topic_count.get(primary_topic, 0) >= MAX_PER_TOPIC:
            continue
        topic_count[primary_topic] = topic_count.get(primary_topic, 0) + 1
        selected.append(article)
        if len(selected) >= top_n:
            break

    print(f"\n🎯 Current Affairs selected: {len(selected)} / {len(scored)} qualified")
    for i, a in enumerate(selected, 1):
        print(f"  {i:02}. [{a['_score']:3d}] {a['source']:4} | {a['title'][:80]}")

    return selected
