"""
Claude-powered task tracking agent with tool use.
"""
import json
from typing import Any

import anthropic

from task_agent import task_store

client = anthropic.Anthropic()
MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = """Je bent een vriendelijke en efficiënte taakbeheerder.
Je helpt de gebruiker om hun dagelijkse taken bij te houden via natuurlijke taal.

Gebruik de beschikbare tools om taken toe te voegen, te voltooien, bij te werken of te verwijderen.
Geef altijd een beknopte samenvatting na elke actie.

Datums schrijf je als YYYY-MM-DD. Prioriteiten zijn: low, medium, high.
Categorieën zijn vrij te kiezen (bijv. werk, privé, sport, administratie).

Vandaag is: {today}
"""


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "add_task",
        "description": "Voeg een nieuwe taak toe aan de lijst.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Korte naam van de taak"},
                "description": {"type": "string", "description": "Optionele beschrijving"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Prioriteit (standaard: medium)",
                },
                "due_date": {
                    "type": "string",
                    "description": "Vervaldatum in formaat YYYY-MM-DD (optioneel)",
                },
                "category": {
                    "type": "string",
                    "description": "Categorie, bijv. werk, privé, sport (standaard: general)",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_tasks",
        "description": "Bekijk de takenlijst, optioneel gefilterd.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter_done": {
                    "type": "boolean",
                    "description": "true = alleen voltooide taken, false = alleen openstaande",
                },
                "category": {"type": "string", "description": "Filter op categorie"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Filter op prioriteit",
                },
            },
        },
    },
    {
        "name": "complete_task",
        "description": "Markeer een taak als voltooid op basis van het ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Het 8-karakter taak-ID"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "update_task",
        "description": "Pas een bestaande taak aan (titel, beschrijving, prioriteit, vervaldatum of categorie).",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Het 8-karakter taak-ID"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                "category": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Verwijder een taak permanent op basis van het ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Het 8-karakter taak-ID"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_summary",
        "description": "Geef een overzicht: totaal, voltooid, openstaand, verlopen en vandaag vervallende taken.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ── Tool executor ─────────────────────────────────────────────────────────────

def _execute_tool(name: str, inputs: dict) -> Any:
    if name == "add_task":
        result = task_store.add_task(**inputs)
        return {"success": True, "task": result}

    if name == "list_tasks":
        tasks = task_store.list_tasks(**inputs)
        return {"tasks": tasks, "count": len(tasks)}

    if name == "complete_task":
        task = task_store.complete_task(inputs["task_id"])
        if task:
            return {"success": True, "task": task}
        return {"success": False, "error": f"Taak met ID '{inputs['task_id']}' niet gevonden."}

    if name == "update_task":
        task_id = inputs.pop("task_id")
        task = task_store.update_task(task_id, **inputs)
        if task:
            return {"success": True, "task": task}
        return {"success": False, "error": f"Taak met ID '{task_id}' niet gevonden."}

    if name == "delete_task":
        deleted = task_store.delete_task(inputs["task_id"])
        return {"success": deleted, "task_id": inputs["task_id"]}

    if name == "get_summary":
        return task_store.get_summary()

    return {"error": f"Onbekend tool: {name}"}


# ── Agent ─────────────────────────────────────────────────────────────────────

class TaskAgent:
    def __init__(self):
        self.messages: list[dict] = []

    def chat(self, user_input: str) -> str:
        from datetime import date

        self.messages.append({"role": "user", "content": user_input})
        system = SYSTEM_PROMPT.format(today=date.today().isoformat())

        # Agentic loop
        while True:
            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=system,
                tools=TOOLS,
                messages=self.messages,
            ) as stream:
                response = stream.get_final_message()

            # Collect text blocks for the final reply
            text_blocks = [b.text for b in response.content if b.type == "text"]

            if response.stop_reason == "end_turn":
                # No more tool calls — return the final text
                reply = "\n".join(text_blocks).strip()
                self.messages.append({"role": "assistant", "content": response.content})
                return reply

            if response.stop_reason == "tool_use":
                # Execute all requested tools
                self.messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = _execute_tool(block.name, dict(block.input))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                self.messages.append({"role": "user", "content": tool_results})
                # Loop back to get Claude's response after tool execution
                continue

            # Unexpected stop reason
            reply = "\n".join(text_blocks).strip()
            self.messages.append({"role": "assistant", "content": response.content})
            return reply
