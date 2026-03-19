"""
Polymarket API client.
All HTTP calls go through validate → assert_safe_url → requests.Session.
Paper trading mode is the safe default.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from core.config import get_config
from core.logger import get_logger
from core.security import (
    assert_safe_url,
    get_rate_limiter,
    safe_json_from_response,
    validate_market_id,
    validate_outcome,
    validate_price,
    validate_usd_amount,
)

logger = get_logger("polymarket")

_BASE_GAMMA = "https://gamma-api.polymarket.com"
_BASE_CLOB = "https://clob.polymarket.com"

# Rate limits (calls per window_seconds)
_MARKET_LIMIT = 120
_MARKET_WINDOW = 60.0
_ORDER_LIMIT = 10
_ORDER_WINDOW = 60.0

_rl = get_rate_limiter()


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Market:
    """A Polymarket prediction market."""

    id: str
    question: str
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    end_date: str
    condition_id: str
    token_ids: List[str]
    description: str = ""
    category: str = ""

    def __post_init__(self) -> None:
        validate_market_id(self.id)
        self.yes_price = validate_price(self.yes_price)
        self.no_price = validate_price(self.no_price)
        self.volume = validate_usd_amount(self.volume)
        self.liquidity = validate_usd_amount(self.liquidity)
        price_sum = self.yes_price + self.no_price
        if not (0.85 <= price_sum <= 1.15):
            raise ValueError(
                f"Market {self.id} price sum {price_sum:.3f} outside [0.85, 1.15]"
            )

    @property
    def days_to_end(self) -> float:
        """Approximate days remaining until market ends."""
        try:
            end = datetime.fromisoformat(self.end_date.replace("Z", "+00:00"))
            delta = end - datetime.now(timezone.utc)
            return max(0.0, delta.total_seconds() / 86400)
        except Exception:
            return 0.0


@dataclass
class OrderResult:
    """Result of a buy order."""

    success: bool
    order_id: str
    market_id: str
    outcome: str
    size_usd: float
    price: float
    paper: bool
    error: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PolymarketClient:
    """HTTP client for Polymarket APIs with retry, rate limiting, and validation."""

    def __init__(self) -> None:
        self._cfg = get_config()
        self._session = requests.Session()
        self._session.verify = True
        self._session.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: Optional[dict] = None) -> Any:
        """Rate-limited GET with retry and safe JSON parsing."""
        assert_safe_url(url)
        _rl.wait_if_needed("market_data", _MARKET_LIMIT, _MARKET_WINDOW)

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt, delay in enumerate([1, 2, 4]):
            try:
                resp = self._session.get(url, params=params, timeout=15)
                resp.raise_for_status()
                return safe_json_from_response(resp)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                logger.warning("GET %s failed (attempt %d): %s", url, attempt + 1, exc)
                time.sleep(delay)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code < 500:
                    raise  # client errors: don't retry
                last_exc = exc
                logger.warning("HTTP error %s (attempt %d)", exc, attempt + 1)
                time.sleep(delay)
        raise last_exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_markets(self, limit: int = 30) -> List[Market]:
        """Fetch active markets from Gamma API."""
        url = f"{_BASE_GAMMA}/markets"
        params = {"limit": min(limit, 100), "active": "true", "closed": "false"}
        try:
            data = self._get(url, params)
        except Exception as exc:
            logger.error("get_markets failed: %s", exc)
            return []

        markets: List[Market] = []
        raw_list: list = data if isinstance(data, list) else data.get("markets", [])
        for item in raw_list:
            try:
                market = self._parse_market(item)
                markets.append(market)
            except Exception as exc:
                logger.debug("Skipping malformed market entry: %s", exc)
        return markets

    def get_market_by_id(self, market_id: str) -> Optional[Market]:
        """Fetch a single market by ID."""
        try:
            validate_market_id(market_id)
        except ValueError as exc:
            logger.warning("get_market_by_id rejected invalid id: %s", exc)
            return None
        url = f"{_BASE_GAMMA}/markets/{market_id}"
        try:
            data = self._get(url)
            return self._parse_market(data)
        except Exception as exc:
            logger.error("get_market_by_id(%s) failed: %s", market_id, exc)
            return None

    def get_wallet_balance(self, address: str) -> float:
        """Return USDC balance for a wallet address (paper: returns starting balance)."""
        if self._cfg.paper_trading:
            return self._cfg.starting_balance
        # Live: query Polygon USDC balance via Polymarket API
        url = f"{_BASE_CLOB}/balance"
        try:
            data = self._get(url, {"address": address})
            return float(data.get("balance", 0.0))
        except Exception as exc:
            logger.error("get_wallet_balance failed: %s", exc)
            return 0.0

    def buy(
        self,
        market: Market,
        outcome: str,
        size_usd: float,
    ) -> OrderResult:
        """Place a buy order. In paper mode, simulates execution."""
        validate_outcome(outcome)
        size_usd = validate_usd_amount(size_usd)
        cfg = self._cfg

        # Final paper-trading guard
        if cfg.paper_trading:
            price = market.yes_price if outcome == "YES" else market.no_price
            logger.info(
                "[PAPER] BUY_%s on %s — $%.2f @ %.3f",
                outcome,
                market.id,
                size_usd,
                price,
            )
            return OrderResult(
                success=True,
                order_id=f"paper-{uuid.uuid4().hex[:12]}",
                market_id=market.id,
                outcome=outcome,
                size_usd=size_usd,
                price=price,
                paper=True,
            )

        # Live order
        if not cfg.polymarket_private_key:
            return OrderResult(
                success=False,
                order_id="",
                market_id=market.id,
                outcome=outcome,
                size_usd=size_usd,
                price=0.0,
                paper=False,
                error="POLYMARKET_PRIVATE_KEY not set — cannot place live order.",
            )

        _rl.wait_if_needed("live_orders", _ORDER_LIMIT, _ORDER_WINDOW)
        price = market.yes_price if outcome == "YES" else market.no_price
        token_id = market.token_ids[0] if outcome == "YES" else (
            market.token_ids[1] if len(market.token_ids) > 1 else market.token_ids[0]
        )
        url = f"{_BASE_CLOB}/order"
        assert_safe_url(url)

        payload = {
            "tokenID": token_id,
            "price": price,
            "side": "BUY",
            "size": size_usd,
        }

        last_exc: Exception = RuntimeError("No attempts")
        for attempt, delay in enumerate([2, 4]):
            try:
                resp = self._session.post(url, json=payload, timeout=20)
                resp.raise_for_status()
                result = safe_json_from_response(resp)
                order_id = result.get("orderID", result.get("id", ""))
                actual_price = float(result.get("price", price))
                return OrderResult(
                    success=True,
                    order_id=order_id,
                    market_id=market.id,
                    outcome=outcome,
                    size_usd=size_usd,
                    price=actual_price,
                    paper=False,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning("Live buy attempt %d failed: %s", attempt + 1, exc)
                if attempt < 1:
                    time.sleep(delay)

        return OrderResult(
            success=False,
            order_id="",
            market_id=market.id,
            outcome=outcome,
            size_usd=size_usd,
            price=0.0,
            paper=False,
            error=str(last_exc),
        )

    def get_open_orders(self) -> List[dict]:
        """Return list of open orders."""
        if self._cfg.paper_trading:
            return []
        url = f"{_BASE_CLOB}/orders"
        try:
            data = self._get(url)
            return data if isinstance(data, list) else data.get("orders", [])
        except Exception as exc:
            logger.error("get_open_orders failed: %s", exc)
            return []

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if self._cfg.paper_trading:
            return True
        url = f"{_BASE_CLOB}/order/{order_id}"
        assert_safe_url(url)
        try:
            resp = self._session.delete(url, timeout=15)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("cancel_order(%s) failed: %s", order_id, exc)
            return False

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_market(item: dict) -> Market:
        """Parse a raw API dict into a validated Market object."""
        tokens = item.get("tokens", [])
        token_ids: List[str] = [t.get("token_id", "") for t in tokens if t.get("token_id")]

        yes_price = 0.5
        no_price = 0.5
        for tok in tokens:
            outcome_raw = tok.get("outcome", "").upper()
            raw_price = tok.get("price", 0.5)
            try:
                p = validate_price(raw_price)
            except ValueError:
                p = 0.5
            if outcome_raw == "YES":
                yes_price = p
            elif outcome_raw == "NO":
                no_price = p

        return Market(
            id=item.get("id", item.get("conditionId", "unknown")),
            question=item.get("question", ""),
            yes_price=yes_price,
            no_price=no_price,
            volume=float(item.get("volume", 0) or 0),
            liquidity=float(item.get("liquidity", 0) or 0),
            end_date=item.get("endDate", item.get("end_date", "")),
            condition_id=item.get("conditionId", ""),
            token_ids=token_ids,
            description=item.get("description", ""),
            category=item.get("category", ""),
        )
