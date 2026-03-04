"""
ai_client.py — OpenRouter API wrapper using OpenAI-compatible interface.
Uses free models with automatic fallback, timeout, and retry hardening.
"""

from __future__ import annotations

import os
import time

import httpx
from openai import OpenAI

# Free models on OpenRouter (in preference order)
FREE_MODELS = [
    "google/gemma-3-27b-it:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]

# Hard limits — prevent a single call from hanging the GitHub Action
REQUEST_TIMEOUT   = 60    # seconds per API request
MAX_RETRIES       = 2     # retries per model before trying next model
RETRY_SLEEP       = 3     # seconds between retries

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


def chat(system: str, user: str, max_tokens: int = 900, temperature: float = 0.3) -> str:
    """
    Send a chat message and return the reply text.
    Tries each free model in order with per-model retries; raises only if ALL fail.
    """
    client     = get_client()
    last_error: Exception | None = None

    for model in FREE_MODELS:
        for attempt in range(1, MAX_RETRIES + 2):   # +2 so attempt range is 1..MAX_RETRIES+1
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError("Model returned empty content")
                return content.strip()

            except Exception as exc:
                last_error = exc
                if attempt <= MAX_RETRIES:
                    print(f"  ⚠ {model} attempt {attempt} failed: {exc}. Retrying in {RETRY_SLEEP}s…")
                    time.sleep(RETRY_SLEEP)
                else:
                    print(f"  ✗ {model} exhausted retries. Moving to next model.")
                    time.sleep(1)

    raise RuntimeError(f"All OpenRouter models failed. Last error: {last_error}")
