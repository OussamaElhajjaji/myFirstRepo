#!/usr/bin/env python3
"""
Persoonlijke 24/7 Taak-Assistent
Aangedreven door Claude + Ollama (dynamische model-selectie)

Gebruik:
    python run_task_agent.py               # standaard (Ollama indien beschikbaar)
    python run_task_agent.py --no-ollama   # forceer Claude API

Vereiste omgevingsvariabele:
    ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# Logging (INFO naar stderr zodat stdout schoon blijft)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
    stream=sys.stderr,
)


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
_BANNER = """
╔════════════════════════════════════════════════════════════╗
║        Persoonlijke 24/7 Taak-Assistent                    ║
║        Claude + Ollama | SQLite | Motivatie | Reminders    ║
╠════════════════════════════════════════════════════════════╣
║  Voorbeelden:                                              ║
║   • "Voeg toe: rapport schrijven, hoog, deadline morgen"   ║
║   • "Toon al mijn taken"                                   ║
║   • "Markeer taak abc12345 als klaar"                      ║
║   • "briefing"  — volledig dagelijks overzicht             ║
║   • "motiveer me"  — een motivatie-boost                  ║
║   • "help"  — uitleg van alle commando's                   ║
║                                                            ║
║  Typ  'stop'  of  'doei'  om te stoppen.                   ║
╚════════════════════════════════════════════════════════════╝
"""

_HELP_TEXT = """
📚 **Beschikbare commando's:**

Taakbeheer:
  • Voeg toe: [titel], [prioriteit], [datum]
  • Toon taken / Lijst
  • Markeer [taak-ID] als klaar
  • Verwijder taak [taak-ID]
  • Update taak [taak-ID]: [veld] = [waarde]

Overzichten:
  • briefing          — dagelijks overzicht met motivatie
  • overzicht         — snelle samenvatting
  • achterstand       — alle verlopen taken

Persoonlijk:
  • motiveer me       — motivatie-boost
  • hoe gaat het      — check-in gesprek

Systeem:
  • help              — dit scherm
  • stop / doei       — afsluiten
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persoonlijke taak-assistent")
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Gebruik uitsluitend de Claude API (negeer Ollama)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Toon debug-logging",
    )
    return parser.parse_args()


def _check_env() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Fout: ANTHROPIC_API_KEY is niet ingesteld.\n"
            "Stel in met:  export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(1)


def _handle_local_command(user_input: str, agent) -> str | None:
    """
    Verwerk commando's die geen LLM-call nodig hebben.
    Geeft de respons terug, of None als het geen lokaal commando is.
    """
    lower = user_input.strip().lower()
    if lower in {"help", "hulp", "?"}:
        return _HELP_TEXT
    if lower in {"briefing", "dagelijks overzicht", "dag overzicht"}:
        return agent.daily_briefing()
    if lower in {"motiveer me", "motivatie", "help me"}:
        return agent._motivation.motivation_boost()
    return None


def main() -> None:
    args = _parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    _check_env()

    from task_agent.agent import TaskAgent

    try:
        agent = TaskAgent(prefer_ollama=not args.no_ollama)
    except EnvironmentError as e:
        print(f"Opstartfout: {e}", file=sys.stderr)
        sys.exit(1)

    print(_BANNER)

    # Welkomstbericht bij opstarten
    welcome = agent.welcome()
    print(f"Assistent:\n{welcome}\n")

    # Proactieve nudges voor achterstallige taken
    nudges = agent._motivation.overdue_nudges()
    if nudges:
        print("⚠️  Openstaande waarschuwingen:")
        for nudge in nudges:
            print(f"   {nudge}")
        print()

    # Hoofd chat-loop
    while True:
        try:
            user_input = input("Jij: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTot ziens! Succes vandaag! 💪")
            agent.shutdown()
            break

        if not user_input:
            continue

        if user_input.lower() in {"stop", "exit", "quit", "bye", "doei", "afsluiten"}:
            print("Assistent: Tot ziens! Je hebt het vandaag goed gedaan. 🌟")
            agent.shutdown()
            break

        # Probeer lokale commando's eerst (geen LLM-call nodig)
        local_response = _handle_local_command(user_input, agent)
        if local_response:
            print(f"Assistent:\n{local_response}\n")
            continue

        # LLM-call
        print("Assistent: ", end="", flush=True)
        try:
            reply = agent.chat(user_input)
            print(reply)
        except KeyboardInterrupt:
            print("\n[Onderbroken]")
        except Exception as exc:
            print(f"\n[Fout] {exc}")
            logging.exception("Fout bij agent.chat()")
        print()


if __name__ == "__main__":
    main()
