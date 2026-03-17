"""
Reminder daemon — draait als achtergrond-thread en controleert elke minuut
of er herinneringen verzonden moeten worden. Afgedrukt naar de console.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from ..database.store import ReminderStore, TaskStore

logger = logging.getLogger(__name__)

# Type alias voor de callback waarmee de daemon berichten toont
NotifyCallback = Callable[[str], None]


class ReminderDaemon:
    """
    Lichtgewicht achtergrond-daemon die:
      1. Elke minuut de database controleert op verschuldigde herinneringen.
      2. Proactief de gebruiker waarschuwt voor taken die bijna over de deadline zijn.
      3. Een dagelijkse briefing stuurt bij de eerste start van de dag.
    """

    def __init__(
        self,
        notify: NotifyCallback,
        check_interval: int = 60,
    ):
        self._notify = notify
        self._interval = check_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_briefing_date: Optional[str] = None

    # ------------------------------------------------------------------
    # Publieke interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start de daemon-thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ReminderDaemon",
            daemon=True,
        )
        self._thread.start()
        logger.info("ReminderDaemon gestart (interval=%ds).", self._interval)

    def stop(self) -> None:
        """Stop de daemon netjes."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("ReminderDaemon gestopt.")

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_reminders()
                self._check_morning_briefing()
            except Exception:
                logger.exception("Fout in ReminderDaemon._run()")
            self._stop_event.wait(timeout=self._interval)

    def _check_reminders(self) -> None:
        due = ReminderStore.get_due()
        for reminder in due:
            self._notify(
                f"\n🔔 HERINNERING: {reminder['message']}\n"
                f"   Taak ID: {reminder['task_id']} — typ 'klaar {reminder['task_id']}' als je klaar bent.\n"
            )

    def _check_morning_briefing(self) -> None:
        """Stuur één keer per dag een ochtendbriefing tussen 07:00–09:00."""
        now = datetime.now()
        today = now.date().isoformat()
        if self._last_briefing_date == today:
            return
        if not (7 <= now.hour < 9):
            return

        self._last_briefing_date = today
        summary = TaskStore.summary()
        if summary["pending"] > 0:
            self._notify(
                f"\n☀️  Goedemorgen! Je hebt {summary['pending']} openstaande taken."
                f" {summary['overdue']} zijn te laat. Typ 'briefing' voor een overzicht.\n"
            )
