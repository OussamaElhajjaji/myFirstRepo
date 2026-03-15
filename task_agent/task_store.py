"""
Persistent JSON-based task storage.
"""
import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

TASKS_FILE = Path(__file__).parent.parent / "output" / "tasks.json"


def _load() -> list[dict]:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TASKS_FILE.exists():
        return []
    try:
        return json.loads(TASKS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save(tasks: list[dict]) -> None:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False))


def add_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    due_date: Optional[str] = None,
    category: str = "general",
) -> dict:
    tasks = _load()
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "description": description,
        "priority": priority,
        "due_date": due_date,
        "category": category,
        "done": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "completed_at": None,
    }
    tasks.append(task)
    _save(tasks)
    return task


def list_tasks(
    filter_done: Optional[bool] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
) -> list[dict]:
    tasks = _load()
    if filter_done is not None:
        tasks = [t for t in tasks if t["done"] == filter_done]
    if category:
        tasks = [t for t in tasks if t.get("category", "").lower() == category.lower()]
    if priority:
        tasks = [t for t in tasks if t.get("priority", "").lower() == priority.lower()]
    return tasks


def complete_task(task_id: str) -> Optional[dict]:
    tasks = _load()
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = True
            task["completed_at"] = datetime.now().isoformat(timespec="seconds")
            _save(tasks)
            return task
    return None


def update_task(task_id: str, **fields) -> Optional[dict]:
    allowed = {"title", "description", "priority", "due_date", "category"}
    tasks = _load()
    for task in tasks:
        if task["id"] == task_id:
            for k, v in fields.items():
                if k in allowed:
                    task[k] = v
            _save(tasks)
            return task
    return None


def delete_task(task_id: str) -> bool:
    tasks = _load()
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        return False
    _save(new_tasks)
    return True


def get_summary() -> dict:
    tasks = _load()
    today = date.today().isoformat()
    overdue = [
        t for t in tasks
        if not t["done"] and t.get("due_date") and t["due_date"] < today
    ]
    due_today = [
        t for t in tasks
        if not t["done"] and t.get("due_date") == today
    ]
    return {
        "total": len(tasks),
        "done": sum(1 for t in tasks if t["done"]),
        "pending": sum(1 for t in tasks if not t["done"]),
        "overdue": len(overdue),
        "due_today": len(due_today),
        "overdue_tasks": overdue,
        "due_today_tasks": due_today,
    }
