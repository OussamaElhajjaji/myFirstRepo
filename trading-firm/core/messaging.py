"""
In-process publish/subscribe message bus.
Topics are strings; handlers are synchronous callables.
History is kept per topic with a configurable cap.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.logger import get_logger

logger = get_logger("messaging")

# Canonical topic names
TOPIC_MARKET_FOUND = "market.found"
TOPIC_AGENT_OPINION = "agent.opinion"
TOPIC_CONSENSUS_REACHED = "consensus.reached"
TOPIC_TRADE_EXECUTED = "trade.executed"
TOPIC_POSITION_CLOSED = "position.closed"
TOPIC_ALERT_RISK = "alert.risk"
TOPIC_CYCLE_COMPLETE = "cycle.complete"
TOPIC_SECURITY_ALERT = "security.alert"
TOPIC_CIRCUIT_BREAKER = "circuit.breaker"

ALL_TOPICS = frozenset({
    TOPIC_MARKET_FOUND,
    TOPIC_AGENT_OPINION,
    TOPIC_CONSENSUS_REACHED,
    TOPIC_TRADE_EXECUTED,
    TOPIC_POSITION_CLOSED,
    TOPIC_ALERT_RISK,
    TOPIC_CYCLE_COMPLETE,
    TOPIC_SECURITY_ALERT,
    TOPIC_CIRCUIT_BREAKER,
})

Handler = Callable[[str, dict], None]


class MessageBus:
    """Thread-safe in-process pub/sub message bus."""

    MAX_HISTORY = 500  # per topic

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: Dict[str, List[Handler]] = {}
        self._history: Dict[str, deque] = {}

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register a handler for a topic."""
        with self._lock:
            self._handlers.setdefault(topic, []).append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        """Remove a handler from a topic."""
        with self._lock:
            if topic in self._handlers:
                try:
                    self._handlers[topic].remove(handler)
                except ValueError:
                    pass

    def publish(self, topic: str, payload: dict) -> None:
        """Publish a message. All handlers are called synchronously."""
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            handlers = list(self._handlers.get(topic, []))
            if topic not in self._history:
                self._history[topic] = deque(maxlen=self.MAX_HISTORY)
            self._history[topic].append((timestamp, payload))

        for handler in handlers:
            try:
                handler(topic, payload)
            except Exception as exc:
                logger.error("Bus handler error on topic %s: %s", topic, exc)

    def get_history(
        self, topic: str, limit: int = 50
    ) -> List[Tuple[str, dict]]:
        """Return up to `limit` most recent (timestamp, payload) pairs for a topic."""
        with self._lock:
            dq = self._history.get(topic, deque())
            items = list(dq)
        return items[-limit:]

    def get_all_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent messages across all topics, newest first."""
        all_events: List[Tuple[str, str, dict]] = []
        with self._lock:
            for topic, dq in self._history.items():
                for ts, payload in dq:
                    all_events.append((ts, topic, payload))
        all_events.sort(key=lambda x: x[0], reverse=True)
        return [
            {"timestamp": ts, "topic": topic, "payload": payload}
            for ts, topic, payload in all_events[:limit]
        ]


# Singleton bus instance
_bus: Optional[MessageBus] = None


def get_bus() -> MessageBus:
    """Return the singleton MessageBus instance."""
    global _bus
    if _bus is None:
        _bus = MessageBus()
    return _bus
