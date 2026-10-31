"""Retry, deadline, rate-limit and budget policy (Spec 08, OD-56 / OD-58 / OD-59). Deterministic: no jitter."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .errors import BudgetExceeded, RateLimited
from .types import RunBudget


@dataclass
class Timing:
    """Clock and sleep, injectable so tests never wait for real time."""

    now: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    min_wait_s: float = 2.0
    max_wait_s: float = 10.0

    def backoff(self, attempt: int) -> float:
        """Wait after failed attempt number `attempt` (1-based): min, 2*min, 4*min ... capped at max."""
        return float(min(self.max_wait_s, self.min_wait_s * (2 ** (attempt - 1))))


@dataclass
class TokenBucket:
    """`rate_per_min` calls per minute with bursts of the same size, for one provider in one process."""

    rate_per_min: int
    timing: Timing = field(default_factory=Timing)

    def __post_init__(self) -> None:
        self.capacity = float(self.rate_per_min)
        self.refill_per_s = self.rate_per_min / 60.0
        self._tokens = self.capacity
        self._last = self.timing.now()

    def _refill(self) -> None:
        now = self.timing.now()
        self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.refill_per_s)
        self._last = now

    async def acquire(self, time_left_s: float, provider: str) -> None:
        """Take one token, waiting if needed; RateLimited when the wait does not fit `time_left_s`."""
        self._refill()
        if self._tokens >= 1.0 - 1e-9:
            self._tokens -= 1.0
            return
        wait = (1.0 - self._tokens) / self.refill_per_s
        if wait >= time_left_s:
            raise RateLimited(f"{provider} call not sent: local rate limit (rate_limited)")
        await self.timing.sleep(wait)
        self._refill()
        self._tokens = max(0.0, self._tokens - 1.0)


def estimate_tokens(chars: int) -> int:
    """Rough input-token estimate before sending (4 characters per token)."""
    return max(1, chars // 4)


def check_budget(
    budget: RunBudget | None,
    *,
    prompt_chars: int,
    max_tokens: int,
    price_in: float | None,
    price_out: float | None,
) -> None:
    """Refuse a call whose worst case (estimated input + max_tokens output) does not fit the run budget."""
    if budget is None:
        return
    if budget.calls_left < 1:
        raise BudgetExceeded("LLM call not sent: run call budget exhausted (budget_exceeded)")
    worst_tokens = estimate_tokens(prompt_chars) + max_tokens
    if worst_tokens > budget.tokens_left:
        raise BudgetExceeded("LLM call not sent: run token budget exhausted (budget_exceeded)")
    if budget.cost_left_usd is not None and price_in is not None and price_out is not None:
        worst_cost = (estimate_tokens(prompt_chars) * price_in + max_tokens * price_out) / 1_000_000
        if worst_cost > budget.cost_left_usd:
            raise BudgetExceeded("LLM call not sent: run cost budget exhausted (budget_exceeded)")


def cost_usd(input_tokens: int, output_tokens: int, price_in: float | None, price_out: float | None) -> float | None:
    if price_in is None or price_out is None:
        return None
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)
