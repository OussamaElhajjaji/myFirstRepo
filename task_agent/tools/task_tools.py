"""
Tool-definities die aan het LLM worden aangeboden, plus de dispatcher
die het resultaat teruggeeft als een platte dict.
"""

from __future__ import annotations

import json
from typing import Any

from ..database.store import TaskStore
from ..llm.base import ToolDefinition


# ---------------------------------------------------------------------------
# Tool-definities (volgen JSON Schema)
# ---------------------------------------------------------------------------

TASK_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="add_task",
        description="Voeg een nieuwe taak toe aan de takenlijst.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Korte naam voor de taak."},
                "description": {"type": "string", "description": "Optionele toelichting."},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Urgentie: low / medium / high.",
                },
                "category": {"type": "string", "description": "Thema of project."},
                "due_date": {"type": "string", "description": "Deadline als YYYY-MM-DD."},
                "recurrence": {
                    "type": "string",
                    "enum": ["", "daily", "weekly", "monthly"],
                    "description": "Herhaling van de taak.",
                },
                "reminder_minutes": {
                    "type": "integer",
                    "description": "Stuur een herinnering N minuten vóór de deadline.",
                },
                "motivation_note": {
                    "type": "string",
                    "description": "Persoonlijke notitie ter motivatie.",
                },
            },
            "required": ["title"],
        },
    ),
    ToolDefinition(
        name="list_tasks",
        description="Geef een overzicht van alle openstaande (of voltooide) taken.",
        parameters={
            "type": "object",
            "properties": {
                "show_done": {
                    "type": "boolean",
                    "description": "true = toon ook voltooide taken.",
                },
                "category": {"type": "string", "description": "Filter op categorie."},
                "priority": {
                    "type": "string",
                    "enum": ["", "low", "medium", "high"],
                    "description": "Filter op prioriteit.",
                },
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="complete_task",
        description="Markeer een taak als voltooid aan de hand van het ID.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Het 8-karakter ID van de taak.",
                }
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="update_task",
        description="Wijzig één of meer velden van een bestaande taak.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID van de taak."},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "category": {"type": "string"},
                "due_date": {"type": "string"},
                "motivation_note": {"type": "string"},
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="delete_task",
        description="Verwijder een taak permanent.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID van de taak."}
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="get_summary",
        description="Geef een statussamenvatting: totaal, gedaan, openstaand, te laat.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool-dispatcher
# ---------------------------------------------------------------------------

def execute_tool(name: str, input_data: dict) -> Any:
    """
    Voer een tool uit op basis van naam + parameters.
    Geeft altijd een JSON-serialiseerbaar resultaat terug.
    """
    dispatch = {
        "add_task": _add_task,
        "list_tasks": _list_tasks,
        "complete_task": _complete_task,
        "update_task": _update_task,
        "delete_task": _delete_task,
        "get_summary": _get_summary,
    }
    handler = dispatch.get(name)
    if not handler:
        return {"error": f"Onbekende tool: {name}"}
    return handler(input_data)


# ---------------------------------------------------------------------------
# Handler-functies
# ---------------------------------------------------------------------------

def _add_task(data: dict) -> dict:
    return TaskStore.add(
        title=data["title"],
        description=data.get("description", ""),
        priority=data.get("priority", "medium"),
        category=data.get("category", "algemeen"),
        due_date=data.get("due_date", ""),
        recurrence=data.get("recurrence", ""),
        reminder_minutes=data.get("reminder_minutes"),
        motivation_note=data.get("motivation_note", ""),
    )


def _list_tasks(data: dict) -> list:
    return TaskStore.list(
        show_done=data.get("show_done", False),
        category=data.get("category", ""),
        priority=data.get("priority", ""),
    )


def _complete_task(data: dict) -> dict:
    return TaskStore.complete(data["task_id"])


def _update_task(data: dict) -> dict:
    task_id = data.pop("task_id")
    return TaskStore.update(task_id, **data)


def _delete_task(data: dict) -> dict:
    return TaskStore.delete(data["task_id"])


def _get_summary(data: dict) -> dict:
    return TaskStore.summary()
