#!/usr/bin/env python3
"""
Dagelijkse taaktracker — aangedreven door Claude Opus 4.6

Gebruik:
    python run_task_agent.py

Vereiste omgevingsvariabele:
    ANTHROPIC_API_KEY
"""
import os
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))


def _check_env():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Fout: ANTHROPIC_API_KEY is niet ingesteld.")
        print("Stel de variabele in met:  export ANTHROPIC_API_KEY=sk-...")
        sys.exit(1)


BANNER = """
╔══════════════════════════════════════════════════════╗
║         Dagelijkse Taaktracker — Claude AI           ║
╠══════════════════════════════════════════════════════╣
║  Typ je opdracht in gewone taal, bijv.:              ║
║   • "Voeg toe: rapport schrijven, hoog, morgen"      ║
║   • "Toon alle openstaande taken"                    ║
║   • "Markeer taak abc12345 als klaar"                ║
║   • "Geef me een dagelijks overzicht"                ║
║                                                      ║
║  Typ  'quit' of  'exit'  om te stoppen.              ║
╚══════════════════════════════════════════════════════╝
"""


def main():
    _check_env()
    from task_agent.agent import TaskAgent

    agent = TaskAgent()
    print(BANNER)

    # Greet with a daily summary on startup
    print("Bezig met ophalen van je dagelijks overzicht...\n")
    greeting = agent.chat("Geef me een vriendelijk dagelijks overzicht van mijn taken.")
    print(f"Assistent: {greeting}\n")

    while True:
        try:
            user_input = input("Jij: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTot ziens!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "stop", "bye", "doei"}:
            print("Tot ziens! Succes vandaag!")
            break

        print("Assistent: ", end="", flush=True)
        try:
            reply = agent.chat(user_input)
            print(reply)
        except Exception as exc:
            print(f"\n[Fout] {exc}")
        print()


if __name__ == "__main__":
    main()
