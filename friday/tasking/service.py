"""High-level task orchestration."""
import asyncio
import logging
from datetime import datetime
from uuid import uuid4

from .models import TaskRecord
from .store import create_task, load_task
from .executor import set_completion_callback

logger = logging.getLogger("friday-agent")

_GLOBAL_TOOLSET = None
_WATCHER_TASK = None

# Track tasks we've launched so the file-watcher knows which to monitor,
# and which have already had their callback fired.
_TRACKED_TASKS: dict[str, str] = {}   # task_id → last-seen status

_POLL_INTERVAL = 3.0  # seconds between file-system polls

def register_toolset(toolset):
    """Register the MCP toolset so background executors can use it."""
    global _GLOBAL_TOOLSET
    _GLOBAL_TOOLSET = toolset


async def _file_watcher_loop():
    """Poll task JSON files for status transitions to completed/failed.

    The standalone executor (running in a separate CMD window) writes the
    final status back to the JSON file.  This loop detects that change and
    fires the completion callback so FRIDAY can speak the summary.
    """
    import inspect
    from . import executor   # module ref so we always read the live _CALLBACK

    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            for task_id, prev_status in list(_TRACKED_TASKS.items()):
                if prev_status in ("completed", "failed"):
                    continue  # already handled

                task = load_task(task_id)
                if not task:
                    continue

                if task.status in ("completed", "failed"):
                    _TRACKED_TASKS[task_id] = task.status
                    logger.info("File-watcher: task %s → %s", task_id, task.status)

                    cb = executor._CALLBACK
                    if cb:
                        try:
                            if inspect.iscoroutinefunction(cb):
                                await cb(task)
                            else:
                                cb(task)
                        except Exception as e:
                            logger.error("Task completion callback error for %s: %s",
                                         task_id, e)
                elif task.status != prev_status:
                    _TRACKED_TASKS[task_id] = task.status
        except Exception as e:
            logger.error("File-watcher loop error: %s", e)


def start_worker():
    """Start the background file-watcher loop."""
    global _WATCHER_TASK
    if _WATCHER_TASK is None:
        _WATCHER_TASK = asyncio.create_task(_file_watcher_loop())

def start_task(goal: str, source: str = "voice") -> str:
    """Creates a new TaskRecord, launches the standalone executor in a visible
    CMD window, and registers it with the file-watcher for completion callback."""
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

    # Register with the file-watcher so we get a callback when done.
    _TRACKED_TASKS[task_id] = "pending"

    # Launch a detached visible terminal window running the standalone executor.
    import os
    import sys
    cmd = f'start cmd /k "{sys.executable} -m friday.tasking.standalone_executor {task_id}"'
    os.system(cmd)

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
