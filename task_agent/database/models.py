"""
SQLAlchemy ORM models voor de taak-assistent database.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    __allow_unmapped__ = True


def _new_uuid() -> str:
    return str(uuid.uuid4())[:8]


class Task(Base):
    __tablename__ = "tasks"

    id: str = Column(String(8), primary_key=True, default=_new_uuid)
    title: str = Column(String(255), nullable=False)
    description: Optional[str] = Column(Text, nullable=True)
    priority: str = Column(String(10), default="medium")   # low / medium / high
    category: str = Column(String(100), default="algemeen")
    due_date: Optional[str] = Column(String(20), nullable=True)    # "YYYY-MM-DD"
    done: bool = Column(Boolean, default=False)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    completed_at: Optional[datetime] = Column(DateTime, nullable=True)

    # Persoonlijke assistent velden
    recurrence: Optional[str] = Column(String(20), nullable=True)  # daily/weekly/monthly
    reminder_minutes: Optional[int] = Column(Integer, nullable=True)  # minuten voor deadline
    motivation_note: Optional[str] = Column(Text, nullable=True)   # persoonlijke motivatienoot
    streak_count: int = Column(Integer, default=0)                 # bijhouden van voltooide reeksen

    reminders: list["Reminder"] = relationship(
        "Reminder", back_populates="task", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "category": self.category,
            "due_date": self.due_date,
            "done": self.done,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "recurrence": self.recurrence,
            "reminder_minutes": self.reminder_minutes,
            "motivation_note": self.motivation_note,
            "streak_count": self.streak_count,
        }

    def __repr__(self) -> str:
        status = "✓" if self.done else "○"
        return f"<Task {self.id} [{status}] {self.title!r}>"


class Reminder(Base):
    __tablename__ = "reminders"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    task_id: str = Column(String(8), ForeignKey("tasks.id"), nullable=False)
    remind_at: datetime = Column(DateTime, nullable=False)
    message: Optional[str] = Column(Text, nullable=True)
    sent: bool = Column(Boolean, default=False)

    task: Task = relationship("Task", back_populates="reminders")

    def __repr__(self) -> str:
        return f"<Reminder task={self.task_id} at={self.remind_at}>"


class ConversationMessage(Base):
    __tablename__ = "conversations"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    role: str = Column(String(20), nullable=False)    # user / assistant / tool
    content: str = Column(Text, nullable=False)
    model_used: Optional[str] = Column(String(100), nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class UserPreference(Base):
    __tablename__ = "user_preferences"

    key: str = Column(String(100), primary_key=True)
    value: str = Column(Text, nullable=False)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
