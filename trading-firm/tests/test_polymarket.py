"""
Polymarket client tests — all HTTP mocked, no real API calls.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("PORTFOLIO_HMAC_KEY", "d" * 64)
os.environ.setdefault("STARTING_BALANCE", "1000")
os.environ.setdefault("PAPER_TRADING", "True")


def _mock_market_dict(
    market_id: str = "mkt-ok",
    yes_price: float = 0.6,
    no_price: float = 0.4,
    volume: float = 50000.0,
    liquidity: float = 10000.0,
) -> dict:
    return {
        "id": market_id,
        "question": "Will this test pass?",
        "volume": volume,
        "liquidity": liquidity,
        "endDate": "2025-12-31T00:00:00Z",
        "conditionId": "0x" + "a" * 64,
        "tokens": [
            {"outcome": "YES", "token_id": "tok-yes", "price": yes_price},
            {"outcome": "NO", "token_id": "tok-no", "price": no_price},
        ],
        "description": "A test market.",
        "category": "test",
    }


def _make_mock_response(data: dict, content_type: str = "application/json") -> MagicMock:
    raw = json.dumps(data).encode()
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": content_type}
    mock_resp.iter_content.return_value = [raw]
    mock_resp.raise_for_status.return_value = None
    return mock_resp


# ---------------------------------------------------------------------------
# get_markets
# ---------------------------------------------------------------------------

def test_get_markets_validates_each_market():
    with patch("requests.Session") as MockSession:
        mock_session = MagicMock()
        MockSession.return_value = mock_session
        mock_session.get.return_value = _make_mock_response([
            _mock_market_dict("mkt-1"),
            _mock_market_dict("mkt-2"),
        ])

        from core.polymarket import PolymarketClient
        client = PolymarketClient()
        markets = client.get_markets(limit=2)

    assert len(markets) == 2
    assert all(m.id in ("mkt-1", "mkt-2") for m in markets)


def test_get_markets_skips_malformed_entries():
    malformed = {"id": "bad-id", "question": "test"}  # missing required fields → bad prices

    with patch("requests.Session") as MockSession:
        mock_session = MagicMock()
        MockSession.return_value = mock_session
        mock_session.get.return_value = _make_mock_response([
            malformed,
            _mock_market_dict("mkt-good"),
        ])

        from core.polymarket import PolymarketClient
        client = PolymarketClient()
        markets = client.get_markets(limit=5)

    # Only the valid one should be returned
    ids = [m.id for m in markets]
    assert "mkt-good" in ids


def test_get_market_by_id_blocks_path_traversal():
    from core.polymarket import PolymarketClient
    client = PolymarketClient()
    result = client.get_market_by_id("../etc/passwd")
    assert result is None


def test_oversized_response_raises():
    from core.security import safe_json_from_response
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.iter_content.return_value = [b"x" * (6 * 1024 * 1024)]
    with pytest.raises(ValueError, match="5 MB"):
        safe_json_from_response(mock_resp)


def test_buy_paper_mode_returns_success_without_api_call():
    os.environ["PAPER_TRADING"] = "True"
    import core.config as cfg_mod
    cfg_mod._config = None  # reset singleton

    from core.polymarket import Market, PolymarketClient
    client = PolymarketClient()
    market = Market(
        id="mkt-paper",
        question="Paper trade test",
        yes_price=0.6,
        no_price=0.4,
        volume=10000.0,
        liquidity=5000.0,
        end_date="2025-12-31T00:00:00Z",
        condition_id="0x" + "b" * 64,
        token_ids=["tok-y", "tok-n"],
    )

    result = client.buy(market, "YES", 10.0)
    assert result.success
    assert result.paper
    assert result.size_usd == 10.0


def test_buy_live_blocked_without_clob_client():
    os.environ["PAPER_TRADING"] = "False"
    os.environ.pop("POLYMARKET_PRIVATE_KEY", None)
    import core.config as cfg_mod
    cfg_mod._config = None

    from core.polymarket import Market, PolymarketClient
    client = PolymarketClient()
    market = Market(
        id="mkt-live",
        question="Live trade test",
        yes_price=0.6,
        no_price=0.4,
        volume=10000.0,
        liquidity=5000.0,
        end_date="2025-12-31T00:00:00Z",
        condition_id="0x" + "c" * 64,
        token_ids=["tok-y", "tok-n"],
    )

    result = client.buy(market, "YES", 10.0)
    assert not result.success
    assert "POLYMARKET_PRIVATE_KEY" in result.error

    # Restore paper trading
    os.environ["PAPER_TRADING"] = "True"
    cfg_mod._config = None


def test_price_sum_sanity_check_rejects_bad_market():
    from core.polymarket import Market
    with pytest.raises(ValueError, match="price sum"):
        Market(
            id="mkt-bad-sum",
            question="Bad price sum market",
            yes_price=0.9,
            no_price=0.8,  # sum = 1.7 — way off
            volume=1000.0,
            liquidity=500.0,
            end_date="2025-12-31T00:00:00Z",
            condition_id="0x" + "e" * 64,
            token_ids=["tok-y", "tok-n"],
        )
