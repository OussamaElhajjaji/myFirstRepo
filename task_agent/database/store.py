"""
Repository-laag: alle database-toegang via één gecontroleerde interface.
Scheidt datapersistentie volledig van bedrijfslogica.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, and_
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Task, Reminder, ConversationMessage, UserPreference


_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "output",
    "assistant.db",
)


def _get_engine():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)
    Base.metadata.create_all(engine)
    return engine


_engine = _get_engine()
_SessionFactory = sessionmaker(bind=_engine)


def get_session() -> Session:
    return _SessionFactory()


# ---------------------------------------------------------------------------
# Task repository
# ---------------------------------------------------------------------------

class TaskStore:

    @staticmethod
    def add(
        title: str,
        description: str = "",
        priority: str = "medium",
        category: str = "algemeen",
        due_date: str = "",
        recurrence: str = "",
        reminder_minutes: Optional[int] = None,
        motivation_note: str = "",
    ) -> Task:
        with get_session() as session:
            task = Task(
                id=_new_id(),
                title=title,
                description=description or None,
                priority=priority,
                category=category,
                due_date=due_date or None,
                recurrence=recurrence or None,
                reminder_minutes=reminder_minutes,
                motivation_note=motivation_note or None,
            )
            session.add(task)
            session.commit()
            session.refresh(task)

            if reminder_minutes is not None and due_date:
                ReminderStore.schedule_for_task(task, session)
                session.commit()

            return task.to_dict()

    @staticmethod
    def list(
        show_done: bool = False,
        category: str = "",
        priority: str = "",
    ) -> list[dict]:
        with get_session() as session:
            query = session.query(Task)
            if not show_done:
                query = query.filter(Task.done == False)
            if category:
                query = query.filter(Task.category.ilike(f"%{category}%"))
            if priority:
                query = query.filter(Task.priority == priority)
            return [t.to_dict() for t in query.order_by(Task.created_at).all()]

    @staticmethod
    def get(task_id: str) -> Optional[dict]:
        with get_session() as session:
            task = session.get(Task, task_id)
            return task.to_dict() if task else None

    @staticmethod
    def complete(task_id: str) -> dict:
        with get_session() as session:
            task = session.get(Task, task_id)
            if not task:
                return {"success": False, "error": f"Taak {task_id} niet gevonden."}
            task.done = True
            task.completed_at = datetime.utcnow()
            task.streak_count += 1
            session.commit()
            return {"success": True, "task": task.to_dict()}

    @staticmethod
    def update(task_id: str, **fields) -> dict:
        with get_session() as session:
            task = session.get(Task, task_id)
            if not task:
                return {"success": False, "error": f"Taak {task_id} niet gevonden."}
            allowed = {
                "title", "description", "priority", "category",
                "due_date", "recurrence", "reminder_minutes", "motivation_note",
            }
            for key, value in fields.items():
                if key in allowed and value is not None:
                    setattr(task, key, value)
            session.commit()
            return {"success": True, "task": task.to_dict()}

    @staticmethod
    def delete(task_id: str) -> dict:
        with get_session() as session:
            task = session.get(Task, task_id)
            if not task:
                return {"success": False, "error": f"Taak {task_id} niet gevonden."}
            session.delete(task)
            session.commit()
            return {"success": True}

    @staticmethod
    def summary() -> dict:
        with get_session() as session:
            today = datetime.utcnow().date().isoformat()
            all_tasks = session.query(Task).all()
            total = len(all_tasks)
            done = sum(1 for t in all_tasks if t.done)
            overdue = sum(
                1 for t in all_tasks
                if not t.done and t.due_date and t.due_date < today
            )
            due_today = sum(
                1 for t in all_tasks
                if not t.done and t.due_date == today
            )
            return {
                "total": total,
                "done": done,
                "pending": total - done,
                "overdue": overdue,
                "due_today": due_today,
            }


# ---------------------------------------------------------------------------
# Reminder repository
# ---------------------------------------------------------------------------

class ReminderStore:

    @staticmethod
    def schedule_for_task(task: Task, session: Session) -> None:
        """Maak een herinnering aan op basis van due_date en reminder_minutes."""
        if not task.due_date or task.reminder_minutes is None:
            return
        due = datetime.fromisoformat(f"{task.due_date}T09:00:00")
        from datetime import timedelta
        remind_at = due - timedelta(minutes=task.reminder_minutes)
        reminder = Reminder(
            task_id=task.id,
            remind_at=remind_at,
            message=f"Herinnering: '{task.title}' is over {task.reminder_minutes} minuten gepland.",
        )
        session.add(reminder)

    @staticmethod
    def get_due() -> list[dict]:
        """Haal alle herinneringen op die nu verzonden moeten worden."""
        with get_session() as session:
            now = datetime.utcnow()
            reminders = (
                session.query(Reminder)
                .filter(and_(Reminder.remind_at <= now, Reminder.sent == False))
                .all()
            )
            result = []
            for r in reminders:
                r.sent = True
                result.append({
                    "id": r.id,
                    "task_id": r.task_id,
                    "message": r.message,
                    "task_title": r.task.title if r.task else "?",
                })
            session.commit()
            return result

    @staticmethod
    def add_manual(task_id: str, remind_at: datetime, message: str) -> dict:
        with get_session() as session:
            reminder = Reminder(task_id=task_id, remind_at=remind_at, message=message)
            session.add(reminder)
            session.commit()
            return {"id": reminder.id, "remind_at": reminder.remind_at.isoformat()}


# ---------------------------------------------------------------------------
# Conversation history repository
# ---------------------------------------------------------------------------

class ConversationStore:

    @staticmethod
    def append(role: str, content: str, model_used: str = "") -> None:
        with get_session() as session:
            msg = ConversationMessage(
                role=role,
                content=content if isinstance(content, str) else str(content),
                model_used=model_used or None,
            )
            session.add(msg)
            session.commit()

    @staticmethod
    def recent(limit: int = 20) -> list[dict]:
        """Geef de laatste N berichten terug als [{role, content}]."""
        with get_session() as session:
            msgs = (
                session.query(ConversationMessage)
                .order_by(ConversationMessage.id.desc())
                .limit(limit)
                .all()
            )
            return [m.to_dict() for m in reversed(msgs)]


# ---------------------------------------------------------------------------
# User preferences repository
# ---------------------------------------------------------------------------

class PreferenceStore:

    @staticmethod
    def get(key: str, default: str = "") -> str:
        with get_session() as session:
            pref = session.get(UserPreference, key)
            return pref.value if pref else default

    @staticmethod
    def set(key: str, value: str) -> None:
        with get_session() as session:
            pref = session.get(UserPreference, key)
            if pref:
                pref.value = value
                pref.updated_at = datetime.utcnow()
            else:
                session.add(UserPreference(key=key, value=value))
            session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]
