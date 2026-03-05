"""
metrics.py — Pipeline metrics tracker.

Tracks per-provider and total stats:
  - API calls made
  - Tokens used (prompt + completion)
  - Latency per call
  - Errors and fallbacks
  - Pipeline step durations

All data is accumulated in a singleton and exported at end of pipeline
for Telegram report and JSON logging.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Per-provider stats
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ProviderStats:
    name:          str
    calls:         int   = 0
    errors:        int   = 0
    prompt_tokens: int   = 0
    comp_tokens:   int   = 0
    total_tokens:  int   = 0
    total_latency: float = 0.0   # seconds

    @property
    def avg_latency(self) -> float:
        return (self.total_latency / self.calls) if self.calls else 0.0

    @property
    def success_rate(self) -> float:
        total = self.calls + self.errors
        return (self.calls / total * 100) if total else 0.0

    def record_call(self, prompt_tok: int, comp_tok: int, latency: float) -> None:
        self.calls         += 1
        self.prompt_tokens += prompt_tok
        self.comp_tokens   += comp_tok
        self.total_tokens  += prompt_tok + comp_tok
        self.total_latency += latency

    def record_error(self) -> None:
        self.errors += 1


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline step timer
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StepTimer:
    name:       str
    start:      float = field(default_factory=time.time)
    end:        float = 0.0
    success:    bool  = True

    def stop(self, success: bool = True) -> float:
        self.end     = time.time()
        self.success = success
        return self.duration

    @property
    def duration(self) -> float:
        return (self.end or time.time()) - self.start


# ─────────────────────────────────────────────────────────────────────────────
# Main metrics registry (singleton)
# ─────────────────────────────────────────────────────────────────────────────
class Metrics:
    def __init__(self):
        self._providers:  dict[str, ProviderStats] = {}
        self._steps:      list[StepTimer]          = []
        self._pipeline_start: float                = time.time()
        self._articles_fetched:   int = 0
        self._articles_filtered:  int = 0
        self._articles_enriched:  int = 0
        self._images_generated:   int = 0
        self._fallbacks_used:     int = 0

    # ── Provider call recording ───────────────────────────────────────────────
    def record_call(
        self,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency: float,
    ) -> None:
        if provider not in self._providers:
            self._providers[provider] = ProviderStats(name=provider)
        self._providers[provider].record_call(prompt_tokens, completion_tokens, latency)

    def record_error(self, provider: str) -> None:
        if provider not in self._providers:
            self._providers[provider] = ProviderStats(name=provider)
        self._providers[provider].record_error()

    def record_fallback(self) -> None:
        self._fallbacks_used += 1

    # ── Pipeline counters ─────────────────────────────────────────────────────
    def set_articles_fetched(self, n: int)   -> None: self._articles_fetched  = n
    def set_articles_filtered(self, n: int)  -> None: self._articles_filtered = n
    def set_articles_enriched(self, n: int)  -> None: self._articles_enriched = n
    def set_images_generated(self, n: int)   -> None: self._images_generated  = n

    # ── Step timers ───────────────────────────────────────────────────────────
    def start_step(self, name: str) -> StepTimer:
        t = StepTimer(name=name)
        self._steps.append(t)
        return t

    # ── Computed totals ───────────────────────────────────────────────────────
    @property
    def total_calls(self) -> int:
        return sum(p.calls for p in self._providers.values())

    @property
    def total_errors(self) -> int:
        return sum(p.errors for p in self._providers.values())

    @property
    def total_prompt_tokens(self) -> int:
        return sum(p.prompt_tokens for p in self._providers.values())

    @property
    def total_comp_tokens(self) -> int:
        return sum(p.comp_tokens for p in self._providers.values())

    @property
    def total_tokens(self) -> int:
        return sum(p.total_tokens for p in self._providers.values())

    @property
    def pipeline_duration(self) -> float:
        return time.time() - self._pipeline_start

    # ── Formatted Telegram report ─────────────────────────────────────────────
    def telegram_report(self) -> str:
        """Return a compact Telegram-safe plain-text report (no MarkdownV2 special chars)."""
        dur  = self.pipeline_duration
        mins = int(dur // 60)
        secs = int(dur % 60)

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📊 PIPELINE METRICS REPORT",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"🕐 Run time      : {mins}m {secs}s",
            f"📰 Fetched       : {self._articles_fetched} articles",
            f"🎯 Filtered      : {self._articles_filtered} current affairs",
            f"🤖 Enriched      : {self._articles_enriched} articles",
            f"🖼  Images made  : {self._images_generated}",
            f"🔄 Fallbacks     : {self._fallbacks_used}",
            "",
            "── TOTAL API USAGE ──────────",
            f"📞 Total calls   : {self.total_calls}",
            f"❌ Total errors  : {self.total_errors}",
            f"📥 Prompt tokens : {self.total_prompt_tokens:,}",
            f"📤 Output tokens : {self.total_comp_tokens:,}",
            f"🔢 Total tokens  : {self.total_tokens:,}",
            "",
        ]

        if self._providers:
            lines.append("── PER PROVIDER ─────────────")
            for p in sorted(self._providers.values(), key=lambda x: x.calls, reverse=True):
                if p.calls == 0 and p.errors == 0:
                    continue
                lines.append(
                    f"  {p.name}"
                )
                lines.append(
                    f"    calls={p.calls}  err={p.errors}  "
                    f"tokens={p.total_tokens:,}  "
                    f"avg={p.avg_latency:.1f}s"
                )
            lines.append("")

        if self._steps:
            lines.append("── STEP DURATIONS ───────────")
            for s in self._steps:
                icon = "✅" if s.success else "❌"
                lines.append(f"  {icon} {s.name:<28} {s.duration:.1f}s")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Export as dict for JSON logging."""
        return {
            "pipeline_duration_s": round(self.pipeline_duration, 1),
            "articles_fetched":    self._articles_fetched,
            "articles_filtered":   self._articles_filtered,
            "articles_enriched":   self._articles_enriched,
            "images_generated":    self._images_generated,
            "fallbacks_used":      self._fallbacks_used,
            "total_calls":         self.total_calls,
            "total_errors":        self.total_errors,
            "total_tokens":        self.total_tokens,
            "prompt_tokens":       self.total_prompt_tokens,
            "completion_tokens":   self.total_comp_tokens,
            "providers": {
                name: {
                    "calls":         p.calls,
                    "errors":        p.errors,
                    "total_tokens":  p.total_tokens,
                    "prompt_tokens": p.prompt_tokens,
                    "comp_tokens":   p.comp_tokens,
                    "avg_latency_s": round(p.avg_latency, 2),
                    "success_rate":  round(p.success_rate, 1),
                }
                for name, p in self._providers.items()
            },
            "steps": [
                {
                    "name":       s.name,
                    "duration_s": round(s.duration, 1),
                    "success":    s.success,
                }
                for s in self._steps
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Global singleton
# ─────────────────────────────────────────────────────────────────────────────
_metrics: Optional[Metrics] = None


def get_metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics


def reset_metrics() -> None:
    global _metrics
    _metrics = Metrics()
