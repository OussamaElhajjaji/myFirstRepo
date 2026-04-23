"""
Core security module. All validation, sanitization, HMAC signing,
rate limiting, and circuit-breaker logic lives here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import requests

from core.config import ALLOWED_HOSTS, get_config
from core.logger import get_logger, scrub_secrets

logger = get_logger("security")

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_MARKET_ID_RE = re.compile(r"^[a-zA-Z0-9\-_]{1,128}$")


def validate_market_id(s: str) -> str:
    """Validate a Polymarket market ID. Raises ValueError on failure."""
    if not isinstance(s, str) or not _MARKET_ID_RE.match(s):
        raise ValueError(f"Invalid market_id: {s!r}")
    return s


def validate_price(v: Any) -> float:
    """Validate a price is a float strictly between 0.001 and 0.999."""
    try:
        f = float(v)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Price must be numeric, got {v!r}") from exc
    if math.isnan(f) or math.isinf(f):
        raise ValueError(f"Price must be finite, got {v!r}")
    if not (0.001 <= f <= 0.999):
        raise ValueError(f"Price {f} out of range [0.001, 0.999]")
    return f


def validate_usd_amount(v: Any) -> float:
    """Validate a USD amount is a float between 0 and 1,000,000."""
    try:
        f = float(v)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"USD amount must be numeric, got {v!r}") from exc
    if math.isnan(f) or math.isinf(f):
        raise ValueError(f"USD amount must be finite, got {v!r}")
    if not (0.0 <= f <= 1_000_000.0):
        raise ValueError(f"USD amount {f} out of range [0, 1_000_000]")
    return f


_VALID_ACTIONS = frozenset({"BUY_YES", "BUY_NO", "SKIP"})


def validate_action(s: str) -> str:
    """Return action if valid, otherwise 'SKIP'."""
    return s if s in _VALID_ACTIONS else "SKIP"


_VALID_CONFIDENCES = frozenset({"low", "medium", "high"})


def validate_confidence(s: str) -> str:
    """Return confidence string if valid, otherwise 'low'."""
    return s if s in _VALID_CONFIDENCES else "low"


_VALID_OUTCOMES = frozenset({"YES", "NO"})


def validate_outcome(s: str) -> str:
    """Validate outcome is YES or NO. Raises ValueError if not."""
    if s not in _VALID_OUTCOMES:
        raise ValueError(f"Invalid outcome: {s!r}")
    return s


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

# Prompt injection / jailbreak patterns to strip
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+\w+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|.*?\|>"),  # special tokens
    re.compile(r"\[INST\]|\[/INST\]|\[SYS\]|\[/SYS\]"),
    re.compile(r"act\s+as\s+if\s+you\s+are", re.IGNORECASE),
    re.compile(r"(pretend|imagine)\s+you\s+(are|have no)", re.IGNORECASE),
    re.compile(r"DAN\b", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"prompt\s+injection", re.IGNORECASE),
]

_NULL_BYTES_RE = re.compile(r"\x00")


def sanitize_string(s: Any, max_len: int = 4096) -> str:
    """Coerce to str, strip null bytes, truncate to max_len."""
    text = str(s)
    text = _NULL_BYTES_RE.sub("", text)
    return text[:max_len]


def sanitize_for_prompt(s: Any, field: str = "input") -> str:
    """Sanitize a value for inclusion in a Claude prompt."""
    text = sanitize_string(s)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning("Prompt injection pattern detected in field %s", field)
            text = pattern.sub("[REMOVED]", text)
    return text


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def assert_safe_url(url: str) -> None:
    """Raise ValueError if URL is not https or not from an allowed host."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS URLs allowed, got scheme '{parsed.scheme}'")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Host '{parsed.hostname}' not in allowed list")


# ---------------------------------------------------------------------------
# Safe JSON loading from HTTP response
# ---------------------------------------------------------------------------

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


def safe_json_from_response(resp: requests.Response) -> Any:
    """
    Stream response body up to 5 MB, check Content-Type, then parse JSON.
    Raises ValueError on oversized or wrong content type.
    """
    content_type = resp.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        raise ValueError(f"Expected JSON content-type, got: {content_type}")

    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            raise ValueError("Response body exceeds 5 MB limit")
        chunks.append(chunk)
    body = b"".join(chunks)
    return json.loads(body)


# ---------------------------------------------------------------------------
# Secret scrubbing (re-export from logger for convenience)
# ---------------------------------------------------------------------------

scrub_secrets = scrub_secrets  # noqa: F811 — already imported above


# ---------------------------------------------------------------------------
# HMAC signing / verification
# ---------------------------------------------------------------------------


def _hmac_key() -> bytes:
    return get_config().portfolio_hmac_key.encode()


def sign_state(data: dict) -> str:
    """Return HMAC-SHA256 hex digest of the JSON-serialised data dict."""
    payload = json.dumps(data, sort_keys=True, default=str).encode()
    return hmac.new(_hmac_key(), payload, hashlib.sha256).hexdigest()


def verify_state(data: dict, sig: str) -> bool:
    """Return True iff sig matches the HMAC of data."""
    expected = sign_state(data)
    return hmac.compare_digest(expected, sig)


# ---------------------------------------------------------------------------
# Rate limiter — sliding window
# ---------------------------------------------------------------------------


class RateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: Dict[str, deque] = {}

    def check(self, key: str, limit: int, window: float) -> bool:
        """Return True if the call is within rate limit."""
        now = time.monotonic()
        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()
            dq = self._windows[key]
            # Evict old entries
            while dq and dq[0] < now - window:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True

    def wait_if_needed(self, key: str, limit: int, window: float) -> None:
        """Block until the call is within rate limit."""
        while not self.check(key, limit, window):
            time.sleep(0.1)


# Shared rate limiter instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """
    Trips (raises RuntimeError) when equity has drawn down by more than
    circuit_breaker_pct from the starting balance.
    """

    def __init__(self, starting_balance: float, circuit_breaker_pct: float) -> None:
        self.starting_balance = starting_balance
        self.circuit_breaker_pct = circuit_breaker_pct
        self._tripped = False
        self._lock = threading.Lock()

    def check(self, equity: float) -> None:
        """Raise RuntimeError if circuit breaker should trip."""
        with self._lock:
            if self._tripped:
                raise RuntimeError("Circuit breaker already tripped — trading halted.")
            drawdown_pct = (self.starting_balance - equity) / self.starting_balance * 100
            if drawdown_pct >= self.circuit_breaker_pct:
                self._tripped = True
                logger.critical(
                    "CIRCUIT BREAKER TRIPPED: drawdown %.1f%% >= threshold %.1f%%",
                    drawdown_pct,
                    self.circuit_breaker_pct,
                )
                raise RuntimeError(
                    f"Circuit breaker tripped: drawdown {drawdown_pct:.1f}% "
                    f">= {self.circuit_breaker_pct:.1f}%"
                )

    @property
    def tripped(self) -> bool:
        with self._lock:
            return self._tripped

    def reset(self) -> None:
        """Manually reset after human review."""
        with self._lock:
            self._tripped = False
        logger.warning("Circuit breaker RESET manually.")
