"""
Logging configuration for the trading firm.
ScrubbingFilter removes secrets from all log records before emit.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
from pathlib import Path
from typing import Optional


# Patterns that identify secrets in log strings
_SECRET_PATTERNS = [
    # Anthropic API keys  sk-ant-...
    re.compile(r"sk-ant-[a-zA-Z0-9\-_]{10,}", re.ASCII),
    # Generic EVM private keys (64 hex chars, optionally prefixed 0x)
    re.compile(r"(0x)?[0-9a-fA-F]{64}"),
    # HMAC-like tokens (hex ≥40 chars)
    re.compile(r"\b[0-9a-fA-F]{40,}\b"),
]

_REDACTED = "[REDACTED]"


def scrub_secrets(text: str) -> str:
    """Replace known secret patterns with [REDACTED]."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


class ScrubbingFilter(logging.Filter):
    """A logging.Filter that scrubs secrets from every log record before emit."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub_secrets(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: scrub_secrets(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(scrub_secrets(str(a)) for a in record.args)
        return True


def _ensure_log_dir(log_dir: str) -> Path:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(log_dir: str = "logs", level: int = logging.INFO) -> None:
    """Configure root logger with file + console handlers, both with ScrubbingFilter."""
    _ensure_log_dir(log_dir)
    scrubber = ScrubbingFilter()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.addFilter(scrubber)

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(scrubber)
    root.addHandler(console)

    # Main rotating log file
    main_file = logging.handlers.RotatingFileHandler(
        Path(log_dir) / "agent.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    main_file.setFormatter(fmt)
    main_file.addFilter(scrubber)
    root.addHandler(main_file)

    # Security-specific log
    sec_logger = logging.getLogger("security")
    sec_file = logging.handlers.RotatingFileHandler(
        Path(log_dir) / "security.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    sec_file.setFormatter(fmt)
    sec_file.addFilter(scrubber)
    sec_logger.addHandler(sec_file)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. setup_logging() must have been called first."""
    return logging.getLogger(name)
