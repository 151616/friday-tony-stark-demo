"""Task persistence."""
import json
import logging
from typing import List, Optional
from pathlib import Path
from .models import TaskRecord

from friday.config import TASK_STATE_DIR

logger = logging.getLogger("friday-agent")

def create_task(task: TaskRecord) -> None:
    save_task(task)

def load_task(task_id: str) -> Optional[TaskRecord]:
    path = TASK_STATE_DIR / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TaskRecord(**data)
    except Exception as e:
        logger.error(f"Failed to load task {task_id}: {e}")
        return None

def save_task(task: TaskRecord) -> None:
    path = TASK_STATE_DIR / f"{task.task_id}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task.model_dump(), f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save task {task.task_id}: {e}")

def delete_task(task_id: str) -> None:
    path = TASK_STATE_DIR / f"{task_id}.json"
    if path.is_file():
        try:
            path.unlink()
        except OSError as e:
            logger.error(f"Failed to delete task {task_id}: {e}")

def list_active_tasks() -> List[TaskRecord]:
    tasks = []
    for path in TASK_STATE_DIR.glob("*.json"):
        task = load_task(path.stem)
        if task:
            tasks.append(task)
    return sorted(tasks, key=lambda t: t.created_at)

def cleanup_finished_tasks() -> None:
    finished_statuses = {"completed", "failed", "cancelled"}
    for task in list_active_tasks():
        if task.status in finished_statuses:
            delete_task(task.task_id)
