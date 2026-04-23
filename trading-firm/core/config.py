"""
Central configuration module. Reads all settings from environment variables.
Never hardcodes secrets. Auto-generates PORTFOLIO_HMAC_KEY on first run.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

# Load .env from project root (one level up from core/)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def _require(key: str) -> str:
    """Return env var value or raise if not set."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return val


def _auto_hmac_key() -> str:
    """Return existing PORTFOLIO_HMAC_KEY or generate and persist a new one."""
    existing = os.getenv("PORTFOLIO_HMAC_KEY")
    if existing:
        return existing
    new_key = secrets.token_hex(32)
    # Append to .env file
    with open(_ENV_PATH, "a") as fh:
        fh.write(f"\nPORTFOLIO_HMAC_KEY={new_key}\n")
    os.environ["PORTFOLIO_HMAC_KEY"] = new_key
    return new_key


@dataclass(frozen=True)
class RiskProfile:
    name: str
    max_position_usd: float
    max_open_positions: int
    circuit_breaker_pct: float


RISK_PROFILES: Dict[str, RiskProfile] = {
    "conservative": RiskProfile("conservative", 20.0, 5, 15.0),
    "moderate":     RiskProfile("moderate",     50.0, 10, 25.0),
    "aggressive":   RiskProfile("aggressive",  100.0, 20, 40.0),
}

ALLOWED_HOSTS = frozenset({
    "gamma-api.polymarket.com",
    "clob.polymarket.com",
    "api.polymarket.com",
    "polymarket.com",
    "strapi.polymarket.com",
})


@dataclass
class Config:
    """Immutable runtime configuration loaded from environment variables."""

    # --- Secrets (never log these) ---
    anthropic_api_key: str = field(default_factory=lambda: _require("ANTHROPIC_API_KEY"))
    polymarket_private_key: str = field(default_factory=lambda: os.getenv("POLYMARKET_PRIVATE_KEY", ""))
    polymarket_api_key: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_KEY", ""))
    polymarket_api_secret: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_SECRET", ""))
    polymarket_api_passphrase: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_PASSPHRASE", ""))
    wallet_address: str = field(default_factory=lambda: os.getenv("WALLET_ADDRESS", ""))
    portfolio_hmac_key: str = field(default_factory=_auto_hmac_key)

    # --- Risk profile ---
    risk_profile: RiskProfile = field(init=False)

    # --- Operational ---
    loop_interval_sec: int = field(default_factory=lambda: int(os.getenv("LOOP_INTERVAL_SEC", "120")))
    min_edge_threshold: float = field(default_factory=lambda: float(os.getenv("MIN_EDGE_THRESHOLD", "0.05")))
    min_consensus_score: float = field(default_factory=lambda: float(os.getenv("MIN_CONSENSUS_SCORE", "0.65")))
    paper_trading: bool = field(default_factory=lambda: os.getenv("PAPER_TRADING", "True").lower() != "false")
    log_dir: str = field(default_factory=lambda: os.getenv("LOG_DIR", "logs"))
    max_markets_per_run: int = field(default_factory=lambda: int(os.getenv("MAX_MARKETS_PER_RUN", "10")))
    starting_balance: float = field(default_factory=lambda: float(os.getenv("STARTING_BALANCE", "1000.0")))

    def __post_init__(self) -> None:
        profile_name = os.getenv("RISK_PROFILE", "moderate").lower()
        if profile_name not in RISK_PROFILES:
            profile_name = "moderate"
        object.__setattr__(self, "risk_profile", RISK_PROFILES[profile_name])

    @property
    def max_position_usd(self) -> float:
        return self.risk_profile.max_position_usd

    @property
    def max_open_positions(self) -> int:
        return self.risk_profile.max_open_positions

    @property
    def circuit_breaker_pct(self) -> float:
        return self.risk_profile.circuit_breaker_pct


# Singleton config instance
_config: Config | None = None


def get_config() -> Config:
    """Return the singleton Config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
