"""High-level task orchestration."""
import asyncio
import logging
from datetime import datetime
from uuid import uuid4

from .models import TaskRecord
from .store import create_task, load_task
from .executor import execute_task, set_completion_callback

logger = logging.getLogger("friday-agent")

_TASK_QUEUE = asyncio.Queue()
_GLOBAL_TOOLSET = None
_WORKER_TASK = None

def register_toolset(toolset):
    """Register the MCP toolset so background executors can use it."""
    global _GLOBAL_TOOLSET
    _GLOBAL_TOOLSET = toolset

async def _worker_loop():
    while True:
        task_id = await _TASK_QUEUE.get()
        try:
            await execute_task(task_id, _GLOBAL_TOOLSET)
        except Exception as e:
            logger.error(f"Task executor queue failed for {task_id}: {e}")
        finally:
            _TASK_QUEUE.task_done()

def start_worker():
    """Start the background orchestrator loop."""
    global _WORKER_TASK
    if _WORKER_TASK is None:
        _WORKER_TASK = asyncio.create_task(_worker_loop())

def start_task(goal: str, source: str = "voice") -> str:
    """Creates a new TaskRecord and pushes it onto the executor queue."""
    task_id = f"task_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:6]}"
    
    task = TaskRecord(
        task_id=task_id,
        goal=goal,
        status="pending",
        mode="planner",
        source=source,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        steps=[]
    )
    create_task(task)
    _TASK_QUEUE.put_nowait(task_id)
    return task_id

def get_task_status(task_id: str) -> TaskRecord | None:
    return load_task(task_id)

def summarize_task(task_id: str) -> str:
    task = load_task(task_id)
    if not task:
        return "I couldn't find that task."
    if task.final_summary:
        return task.final_summary
    return f"Task is currently {task.status}."
