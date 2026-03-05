"""
ai_client.py — Multi-provider AI client with smart rotation, fallback & metrics.

Providers (5 total, used in round-robin):
  • Groq 1      — llama-3.1-8b-instant    (14,400 req/day free)
  • Gemini 1    — gemini-2.0-flash-lite   (1,500 req/day free)
  • Groq 2      — gemma2-9b-it            (14,400 req/day free, 2nd key)
  • Gemini 2    — gemini-2.0-flash-lite   (1,500 req/day free, 2nd key)
  • Gemini 3    — gemini-1.5-flash        (1,500 req/day free, 3rd key)
  • OpenRouter  — llama-3.2-3b:free       (50 req/day — emergency only)

Rules:
  • Max 2 consecutive calls per provider → forced rotation
  • 429 rate limit  → cooldown 65s, move to next
  • 404 / dead model → skip for session
  • 401/403 bad key  → skip for session + warn
  • All metrics recorded via metrics.py
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from openai import OpenAI

from metrics import get_metrics

REQUEST_TIMEOUT = 45    # seconds per call
COOLDOWN        = 65    # seconds after 429 before retrying
MAX_CONSEC      = 2     # max consecutive calls to same provider


# ─────────────────────────────────────────────────────────────────────────────
# Provider dataclass
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Provider:
    name:            str
    base_url:        str
    key_env:         str
    model:           str
    rpm:             int     # conservative req/min limit
    rpd:             int     # req/day limit
    supports_system: bool = True
    priority:        int  = 5   # lower = preferred

    # Runtime state
    _client:         Optional[OpenAI] = field(default=None, repr=False, init=False)
    _last_call:      float = field(default=0.0, repr=False, init=False)
    _calls_session:  int   = field(default=0,   repr=False, init=False)
    _cooldown_until: float = field(default=0.0, repr=False, init=False)
    _dead:           bool  = field(default=False,repr=False, init=False)

    @property
    def key(self) -> str | None:
        v = os.environ.get(self.key_env, "").strip()
        return v if v else None

    @property
    def min_interval(self) -> float:
        return 60.0 / self.rpm

    @property
    def is_available(self) -> bool:
        if self._dead:                    return False
        if not self.key:                  return False
        if time.time() < self._cooldown_until: return False
        return True

    def wait_if_needed(self) -> None:
        gap = self.min_interval - (time.time() - self._last_call)
        if gap > 0:
            time.sleep(gap)

    def get_client(self) -> OpenAI:
        if self._client is None:
            extra_headers: dict[str, str] = {}
            if "openrouter" in self.base_url:
                extra_headers = {
                    "HTTP-Referer": os.environ.get("SITE_URL", "https://upsc-ca.github.io"),
                    "X-Title": "UPSC Current Affairs",
                }
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.key or "NO_KEY",
                timeout=REQUEST_TIMEOUT,
                http_client=httpx.Client(
                    timeout=httpx.Timeout(connect=10, read=REQUEST_TIMEOUT, write=10, pool=5),
                    transport=httpx.HTTPTransport(retries=1),
                ),
                default_headers=extra_headers,
            )
        return self._client

    def call(self, messages: list[dict], max_tokens: int, temperature: float) -> tuple[str, int, int]:
        """
        Make the API call.
        Returns (content, prompt_tokens, completion_tokens).
        """
        self.wait_if_needed()
        t0       = time.time()
        client   = self.get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency = time.time() - t0
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise ValueError("Model returned empty response")

        # Extract token usage (may be None on some providers)
        usage     = response.usage
        p_tok     = usage.prompt_tokens     if usage else 0
        c_tok     = usage.completion_tokens if usage else max_tokens // 2
        self._last_call     = time.time()
        self._calls_session += 1

        # Record in metrics
        get_metrics().record_call(self.name, p_tok, c_tok, latency)
        return content.strip(), p_tok, c_tok

    def mark_cooldown(self, duration: float = COOLDOWN) -> None:
        self._cooldown_until = time.time() + duration
        get_metrics().record_error(self.name)
        print(f"    ⏸  {self.name}: rate-limited — cooling {duration:.0f}s")

    def mark_dead(self, reason: str = "") -> None:
        self._dead = True
        get_metrics().record_error(self.name)
        print(f"    💀 {self.name}: dead{' — ' + reason if reason else ''}")


# ─────────────────────────────────────────────────────────────────────────────
# Provider definitions — order = priority (best first)
# ─────────────────────────────────────────────────────────────────────────────
PROVIDERS: list[Provider] = [
    Provider(
        name="groq_1", priority=1,
        base_url="https://api.groq.com/openai/v1",
        key_env="GROQ_API_KEY",
        model="llama-3.1-8b-instant",
        rpm=20, rpd=14400,
    ),
    Provider(
        name="groq_2", priority=2,
        base_url="https://api.groq.com/openai/v1",
        key_env="GROQ_API_KEY_2",
        model="llama-3.3-70b-versatil",          # gemma2-9b-it decommissioned → replaced
        rpm=20, rpd=14400,
    ),
    Provider(
        name="gemini_1", priority=3,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        key_env="GEMINI_API_KEY_1",
        model="gemini-2.0-flash-lite",
        rpm=5, rpd=1500,                  # conservative — free tier bursts aggressively
    ),
    Provider(
        name="gemini_2", priority=4,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        key_env="GEMINI_API_KEY_2",
        model="gemini-2.0-flash-lite",
        rpm=5, rpd=1500,
    ),
    Provider(
        name="gemini_3", priority=5,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        key_env="GEMINI_API_KEY_3",
        model="gemini-1.5-flash",
        rpm=5, rpd=1500,
    ),
    Provider(
        name="openrouter", priority=6,
        base_url="https://openrouter.ai/api/v1",
        key_env="OPENROUTER_API_KEY",
        model="meta-llama/llama-3.2-3b-instruct:free",
        rpm=8, rpd=48,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Round-robin pool with smart rotation
# ─────────────────────────────────────────────────────────────────────────────
class ProviderPool:
    def __init__(self, providers: list[Provider]):
        self._providers  = sorted(providers, key=lambda p: p.priority)
        self._index      = 0
        self._last_name  = ""
        self._consec     = 0

    def _pick(self, skip_consec_check: bool = False) -> Provider | None:
        """Pick next available provider, respecting MAX_CONSEC rotation."""
        n = len(self._providers)
        for i in range(n):
            p = self._providers[(self._index + i) % n]
            if not p.is_available:
                continue
            if not skip_consec_check and p.name == self._last_name and self._consec >= MAX_CONSEC:
                continue
            self._index = (self._index + i + 1) % n
            return p

        # Relax consec constraint if nothing else available
        if not skip_consec_check:
            return self._pick(skip_consec_check=True)
        return None

    def _wait_for_cooldown(self) -> None:
        """Wait for the soonest cooling provider to recover."""
        candidates = [
            p._cooldown_until
            for p in self._providers
            if not p._dead and p.key and p._cooldown_until > time.time()
        ]
        if candidates:
            wait = max(0, min(candidates) - time.time()) + 1
            print(f"    ⏳ All providers cooling — waiting {wait:.0f}s…")
            time.sleep(wait)

    def chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.3,
    ) -> str:
        attempted: list[str] = []
        last_err: Exception | None = None

        for _round in range(len(self._providers) + 1):
            p = self._pick()
            if p is None:
                self._wait_for_cooldown()
                p = self._pick(skip_consec_check=True)
            if p is None or p.name in attempted:
                break

            attempted.append(p.name)
            messages = _build_messages(system, user, p.supports_system)

            try:
                content, p_tok, c_tok = p.call(messages, max_tokens, temperature)

                # Update rotation tracking
                if p.name == self._last_name:
                    self._consec += 1
                else:
                    self._consec    = 1
                    self._last_name = p.name

                print(
                    f"    ✅ {p.name:12s} | "
                    f"↑{p_tok:4d} tok  ↓{c_tok:4d} tok | "
                    f"session calls: {p._calls_session}"
                )
                return content

            except Exception as exc:
                last_err = exc
                e = str(exc)

                # ── Classify error ────────────────────────────────────────────
                is_rate   = ("429" in e or "quota" in e.lower()
                             or "resource_exhausted" in e.lower()
                             or "too many requests" in e.lower())
                is_dead   = ("404" in e or "No endpoints" in e
                             or "not found" in e.lower()
                             or "decommissioned" in e.lower()
                             or "deprecated" in e.lower())
                is_auth   = ("401" in e or "403" in e
                             or ("api key" in e.lower() and "invalid" in e.lower()))
                is_pay    = "402" in e
                # 400 with model error → dead; 400 generic → cooldown
                is_bad_model = ("400" in e and (
                    "decommissioned" in e.lower() or "not supported" in e.lower()
                    or "invalid model" in e.lower() or "model_not_found" in e.lower()
                ))

                if is_dead or is_bad_model:
                    p.mark_dead("model not available")
                elif is_auth:
                    p.mark_dead(f"auth error — check secret {p.key_env}")
                elif is_pay:
                    p.mark_dead("spend limit reached")
                elif is_rate:
                    # If a Gemini provider hits 429, cool ALL Gemini providers
                    # (they share project quota on free tier)
                    if "gemini" in p.name:
                        for other in self._providers:
                            if "gemini" in other.name and other.name != p.name:
                                other.mark_cooldown(duration=120)
                        p.mark_cooldown(duration=120)
                    else:
                        p.mark_cooldown()
                else:
                    print(f"    ⚠  {p.name}: {exc}")
                    p.mark_cooldown()

        raise RuntimeError(
            f"All providers exhausted. Tried: {attempted}. Last error: {last_err}"
        )

    def status_lines(self) -> list[str]:
        lines = ["Provider Pool Status:"]
        for p in self._providers:
            if not p.key:
                state = "⬜ no key configured"
            elif p._dead:
                state = "💀 dead this session"
            elif time.time() < p._cooldown_until:
                rem = p._cooldown_until - time.time()
                state = f"⏸  cooldown {rem:.0f}s remaining"
            else:
                state = f"✅ available | session calls: {p._calls_session}"
            lines.append(f"  {p.name:12s} {state}")
        return lines


def _build_messages(system: str, user: str, supports_system: bool) -> list[dict]:
    if supports_system:
        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
    return [{"role": "user", "content": f"{system}\n\n---\n{user}"}]


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────
_pool: ProviderPool | None = None


def _get_pool() -> ProviderPool:
    global _pool
    if _pool is None:
        _pool = ProviderPool(PROVIDERS)
        configured = [p.name for p in PROVIDERS if p.key]
        missing    = [p.key_env for p in PROVIDERS if not p.key]
        print(f"\n🔌 AI Provider Pool ready")
        print(f"   Active  : {', '.join(configured) or 'NONE — add secrets!'}")
        if missing:
            print(f"   Missing : {', '.join(missing)}")
        print()
    return _pool


def chat(system: str, user: str, max_tokens: int = 800, temperature: float = 0.3) -> str:
    """Public entry point — routes to best available provider with full metrics."""
    return _get_pool().chat(system, user, max_tokens, temperature)


def provider_status() -> str:
    if _pool is None:
        return "Pool not initialised yet"
    return "\n".join(_pool.status_lines())
