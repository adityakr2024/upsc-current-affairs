"""
ai_client.py — OpenRouter API wrapper using OpenAI-compatible interface.
Uses free models with automatic fallback, timeout, and retry hardening.
"""

from __future__ import annotations

import os
import time

import httpx
from openai import OpenAI

# Free models on OpenRouter (in preference order, verified working 2025)
# Each entry: (model_id, supports_system_role)
FREE_MODELS: list[tuple[str, bool]] = [
    ("deepseek/deepseek-chat-v3-0324:free",           True),
    ("meta-llama/llama-3.2-3b-instruct:free",         True),
    ("meta-llama/llama-3.3-70b-instruct:free",        True),
    ("google/gemma-2-9b-it:free",                     True),
    ("mistralai/mistral-small-3.1-24b-instruct:free", True),
    ("qwen/qwen-2.5-7b-instruct:free",                True),
    ("microsoft/phi-3-mini-128k-instruct:free",       True),
    ("google/gemma-3-12b-it:free",                    False),  # no system role
]

# Hard limits — prevent a single call from hanging the GitHub Action
REQUEST_TIMEOUT   = 60    # seconds per API request
MAX_RETRIES       = 1     # retries per model before trying next model
RETRY_SLEEP       = 2     # seconds between retries

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set.")
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=REQUEST_TIMEOUT,
            # httpx transport with connection-level timeout and retry
            http_client=httpx.Client(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=REQUEST_TIMEOUT,
                    write=10.0,
                    pool=5.0,
                ),
                transport=httpx.HTTPTransport(retries=MAX_RETRIES),
            ),
            default_headers={
                "HTTP-Referer": os.environ.get("SITE_URL", "https://upsc-ca.github.io"),
                "X-Title": "UPSC Current Affairs",
            },
        )
    return _client


def _build_messages(system: str, user: str, supports_system: bool) -> list[dict]:
    """Build message list — merge system into user content if model doesn't support system role."""
    if supports_system:
        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
    # Fallback: prepend system instructions into the user message
    return [
        {"role": "user", "content": f"{system}\n\n---\n{user}"}
    ]


def chat(system: str, user: str, max_tokens: int = 900, temperature: float = 0.3) -> str:
    """
    Send a chat message and return the reply text.
    Tries each free model in order with per-model retries; raises only if ALL fail.
    """
    client     = get_client()
    last_error: Exception | None = None

    for model, supports_system in FREE_MODELS:
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=_build_messages(system, user, supports_system),
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError("Model returned empty content")
                return content.strip()

            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                # Skip immediately on 404 (model gone) — no point retrying
                if "404" in err_str or "No endpoints" in err_str:
                    print(f"  ✗ {model} not available (404). Skipping.")
                    break
                if attempt <= MAX_RETRIES:
                    print(f"  ⚠ {model} attempt {attempt} failed: {exc}. Retrying in {RETRY_SLEEP}s…")
                    time.sleep(RETRY_SLEEP)
                else:
                    print(f"  ✗ {model} exhausted retries. Moving to next model.")
                    time.sleep(1)

    raise RuntimeError(f"All OpenRouter models failed. Last error: {last_error}")
