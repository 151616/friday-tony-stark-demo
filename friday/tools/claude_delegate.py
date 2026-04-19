"""
Headless Claude CLI delegation — Phase 6b.

Launches `claude -p "<prompt>"` as a background subprocess with file-write
permissions scoped to `runtime/claude_output/`.  Writes the result to a task
JSON so the file-watcher in service.py fires the completion callback and
FRIDAY speaks a summary of what Claude did.
"""

import logging
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from friday.config import TASK_STATE_DIR
from friday.tasking.models import TaskRecord
from friday.tasking.store import create_task, save_task

logger = logging.getLogger("friday-agent")

_REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_OUTPUT_DIR = _REPO_ROOT / "runtime" / "claude_output"
CLAUDE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Imported lazily by the tool so the module can load without circular deps.
_TRACKED_TASKS = None


def _get_tracked_tasks():
    global _TRACKED_TASKS
    if _TRACKED_TASKS is None:
        from friday.tasking.service import _TRACKED_TASKS as ts
        _TRACKED_TASKS = ts
    return _TRACKED_TASKS


def _list_files_before(directory: Path) -> set[str]:
    """Snapshot filenames in a directory."""
    if not directory.exists():
        return set()
    return {f.name for f in directory.iterdir() if f.is_file()}


def _run_claude(task_id: str, prompt: str):
    """Run claude CLI in a background thread and update the task JSON."""
    task = None
    try:
        from friday.tasking.store import load_task as _load
        task = _load(task_id)
        if not task:
            logger.error("ask_claude: task %s not found", task_id)
            return

        task.status = "running"
        task.updated_at = datetime.now().isoformat()
        save_task(task)

        # Snapshot files before Claude runs so we can detect new ones.
        files_before = _list_files_before(CLAUDE_OUTPUT_DIR)

        # Augment prompt to tell Claude where to save files.
        full_prompt = (
            f"{prompt}\n\n"
            f"IMPORTANT: Save any files you create to this directory: "
            f"{CLAUDE_OUTPUT_DIR}\n"
            f"After you are done, output a short summary of what you created "
            f"and where you saved it. Keep the summary under 3 sentences."
        )

        result = subprocess.run(
            [
                "claude", "-p", full_prompt,
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(CLAUDE_OUTPUT_DIR),
            env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "cli"},
        )

        output = (result.stdout or "").strip()
        if result.returncode != 0 and not output:
            output = (result.stderr or "").strip() or "Claude returned no output."

        # Detect new files created.
        files_after = _list_files_before(CLAUDE_OUTPUT_DIR)
        new_files = files_after - files_before

        # Build a spoken-friendly summary.
        summary_parts = []
        if new_files:
            file_list = ", ".join(sorted(new_files))
            summary_parts.append(
                f"Created {len(new_files)} file(s) in runtime/claude_output: {file_list}."
            )
        if output:
            summary_parts.append(output[:1500])

        final_summary = " ".join(summary_parts) if summary_parts else "Claude finished but produced no output."

        task.status = "completed"
        task.final_summary = final_summary[:2000]
        logger.info("ask_claude: task %s completed, new files: %s", task_id, new_files or "none")

    except subprocess.TimeoutExpired:
        logger.error("ask_claude: task %s timed out", task_id)
        if task:
            task.status = "failed"
            task.final_summary = "Claude took too long and was stopped after 3 minutes."
    except Exception as e:
        logger.error("ask_claude: task %s failed: %s", task_id, e)
        if task:
            task.status = "failed"
            task.final_summary = f"Claude delegation failed: {e}"
    finally:
        if task:
            task.updated_at = datetime.now().isoformat()
            save_task(task)


def register(mcp):
    @mcp.tool()
    def ask_claude(prompt: str) -> str:
        """Delegate a complex question or task to Claude Code running in the
        background. Use this for deep analysis, code generation, research
        synthesis, or anything that benefits from Claude's reasoning.
        FRIDAY will speak the result when Claude finishes."""

        task_id = f"claude_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:6]}"

        task = TaskRecord(
            task_id=task_id,
            goal=f"Claude delegation: {prompt[:200]}",
            status="pending",
            mode="planner",
            source="voice",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            steps=[],
        )
        create_task(task)

        # Register with the file-watcher for completion callback.
        _get_tracked_tasks()[task_id] = "pending"

        # Run in a background thread so the tool returns immediately.
        thread = threading.Thread(
            target=_run_claude, args=(task_id, prompt), daemon=True
        )
        thread.start()

        return f"Delegated to Claude (task {task_id}). I'll report back when it's done."
