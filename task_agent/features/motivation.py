"""
Motivatie-engine — houdt bij hoe de gebruiker presteert en geeft
gepersonaliseerde aanmoedigingen, vieringen en zachte duwtjes.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

from ..database.store import TaskStore, PreferenceStore


# ---------------------------------------------------------------------------
# Berichten-bank (Nederlands)
# ---------------------------------------------------------------------------

_WELCOME_MORNING = [
    "Goedemorgen! Een nieuwe dag, nieuwe kansen. Laten we er iets moois van maken.",
    "Goed dat je er bent! Vandaag is de dag om iets af te ronden dat al te lang wacht.",
    "Rise and shine! Je hebt dit. Klaar om de dag te domineren?",
]

_WELCOME_AFTERNOON = [
    "Goedemiddag! Hoe loopt de dag tot nu toe? Nog iets dat je van je to-do lijst wil afhalen?",
    "Middag check-in: ben je nog op schema? Ik help je graag de rest van de dag te plannen.",
    "Hé! De middag is perfect om je ochtendtaken door te nemen en de avond voor te bereiden.",
]

_WELCOME_EVENING = [
    "Goedenavond! Bijna tijd om te rusten — maar laten we eerst even kijken wat je vandaag hebt bereikt.",
    "Avond! Dit is het moment om terug te blikken en morgen alvast klaar te leggen.",
]

_TASK_COMPLETED = [
    "Geweldig! Je hebt '{title}' afgerond. Zo werk je naar je doelen!",
    "Top! '{title}' — check! Elke voltooide taak brengt je dichter bij je beste zelf.",
    "Bravo! '{title}' is gedaan. Geef jezelf een schouderklop — je verdient het.",
    "Uitstekend! '{title}' is afgevinkt. Momentum opbouwen, zo doe je dat!",
]

_STREAK_MILESTONE = [
    "WOW — {streak} taken op rij afgerond! Je bent onstopbaar.",
    "Streak van {streak}! Je bent in de zone. Houd dit vast!",
    "{streak} taken achter elkaar — dat is pure discipline. Je bent een machine!",
]

_OVERDUE_NUDGE = [
    "Even een vriendelijke herinnering: '{title}' had al klaar moeten zijn. Wil je er nu aan beginnen?",
    "'{title}' staat al een tijdje open. Geen oordeel — maar samen kunnen we dit aanpakken.",
    "Ik zie dat '{title}' wacht. Misschien is nu een goed moment om er 10 minuten aan te besteden?",
]

_EMPTY_LIST = [
    "Je to-do lijst is leeg! Geniet van het gevoel — je hebt alles gedaan.",
    "Niets meer te doen! Dit is het gevoel waar je voor werkt. Fijn verdiende rust.",
    "Alles afgerond! Klasse. Wil je alvast taken voor morgen inplannen?",
]

_MOTIVATION_BOOST = [
    "Je hoeft niet perfect te zijn — je moet alleen beginnen.",
    "Een kleine stap is beter dan geen stap. Wat is het allerkleinste ding dat je nu kunt doen?",
    "Moeilijkheden zijn tijdelijk. Kwaliteit van je inspanning is voor altijd.",
    "Elke taak die je uitstelt, kost je meer energie dan hem gewoon doen.",
    "Je toekomstige zelf bedankt je voor wat je vandaag doet.",
    "Discipline is je jezelf opnieuw committeren nadat je het moeilijk hebt gevonden.",
]

_DAILY_QUOTES = [
    "\"De geheime sleutel is om te beginnen.\" — Mark Twain",
    "\"Je bent wat je herhaaldelijk doet.\" — Aristoteles",
    "\"Kleine stappen brengen je ver.\" — Lao Tzu",
    "\"Done is better than perfect.\" — Sheryl Sandberg",
    "\"Het enige dat telt is of je het deed.\" — Elbert Hubbard",
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class MotivationEngine:
    """Genereert contextuele motivatie-berichten op basis van taakstatus."""

    def welcome_message(self) -> str:
        """Groet afhankelijk van dagdeel, met een dagelijkse samenvatting."""
        hour = datetime.now().hour
        if hour < 12:
            greeting = random.choice(_WELCOME_MORNING)
        elif hour < 18:
            greeting = random.choice(_WELCOME_AFTERNOON)
        else:
            greeting = random.choice(_WELCOME_EVENING)

        summary = TaskStore.summary()
        summary_text = self._format_summary(summary)
        quote = random.choice(_DAILY_QUOTES)

        return f"{greeting}\n\n{summary_text}\n\n💬 {quote}"

    def on_task_completed(self, task_title: str, streak: int) -> str:
        """Geef een felicitatiebericht na het voltooien van een taak."""
        msg = random.choice(_TASK_COMPLETED).format(title=task_title)
        if streak > 0 and streak % 5 == 0:
            milestone = random.choice(_STREAK_MILESTONE).format(streak=streak)
            msg = f"{msg}\n\n🔥 {milestone}"
        return msg

    def overdue_nudges(self) -> list[str]:
        """Geef zachte herinneringen voor achterstallige taken."""
        today = datetime.utcnow().date().isoformat()
        tasks = TaskStore.list(show_done=False)
        overdue = [t for t in tasks if t.get("due_date") and t["due_date"] < today]
        return [
            random.choice(_OVERDUE_NUDGE).format(title=t["title"])
            for t in overdue[:3]   # maximaal 3 tegelijk
        ]

    def motivation_boost(self) -> str:
        """Willekeurige motivatie-quote."""
        return random.choice(_MOTIVATION_BOOST)

    def daily_briefing(self) -> str:
        """Volledige dagstart samenvatting met motivatie en openstaande taken."""
        summary = TaskStore.summary()
        tasks = TaskStore.list(show_done=False)
        today = datetime.utcnow().date().isoformat()

        due_today = [t for t in tasks if t.get("due_date") == today]
        high_prio = [t for t in tasks if t.get("priority") == "high"]
        overdue = [t for t in tasks if t.get("due_date") and t["due_date"] < today]

        lines = ["📋 **Jouw dagelijkse briefing**\n"]
        lines.append(self._format_summary(summary))

        if due_today:
            lines.append("\n⏰ **Vandaag te doen:**")
            for t in due_today[:5]:
                lines.append(f"  • [{t['priority'].upper()}] {t['title']}")

        if high_prio and not due_today:
            lines.append("\n🔴 **Hoge prioriteit:**")
            for t in high_prio[:3]:
                lines.append(f"  • {t['title']}")

        if overdue:
            lines.append(f"\n⚠️  {len(overdue)} taak/taken zijn te laat:")
            for t in overdue[:3]:
                lines.append(f"  • {t['title']} (was {t['due_date']})")

        if not tasks:
            lines.append(f"\n🎉 {random.choice(_EMPTY_LIST)}")
        else:
            lines.append(f"\n💪 {random.choice(_MOTIVATION_BOOST)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @staticmethod
    def _format_summary(summary: dict) -> str:
        total = summary["total"]
        done = summary["done"]
        pending = summary["pending"]
        overdue = summary["overdue"]
        due_today = summary["due_today"]

        pct = int((done / total * 100) if total else 0)
        bar = _progress_bar(pct)

        lines = [
            f"📊 Voortgang: {done}/{total} taken klaar  {bar}  {pct}%",
            f"   Openstaand: {pending}  |  Vandaag: {due_today}  |  Te laat: {overdue}",
        ]
        return "\n".join(lines)


def _progress_bar(pct: int, width: int = 10) -> str:
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)
