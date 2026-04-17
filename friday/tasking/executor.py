"""Executes background task steps."""
import asyncio
import logging
from datetime import datetime
import inspect

from livekit.agents import llm
from friday.providers import build_llm
from .store import load_task, save_task
from .planner import plan_steps

logger = logging.getLogger("friday-agent")

_CALLBACK = None

def set_completion_callback(cb):
    global _CALLBACK
    _CALLBACK = cb

async def execute_task(task_id: str, toolset):
    task = load_task(task_id)
    if not task:
        return

    task.status = "running"
    task.updated_at = datetime.now().isoformat()
    save_task(task)

    try:
        if not task.steps:
            task.steps = await plan_steps(task.goal)
            task.updated_at = datetime.now().isoformat()
            save_task(task)
            
        llm_idx = build_llm(mode="fast")
        ctx = llm.ChatContext()
        ctx.append(role="system", content="You are executing a background task. Use your tools to achieve the goal.")
        ctx.append(role="user", content=f"Goal: {task.goal}. Keep your final response concise.")
        
        response_text = ""
        
        # We let the LLM loop handle internal tool calls automatically by processing the stream
        msg_stream = await llm_idx.chat(chat_ctx=ctx, fnc_ctx=toolset)
        
        # Standard chat iteration - the LLM SDK internally traps tool calls and forwards them to fnc_ctx tools
        async for chunk in msg_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                response_text += chunk.choices[0].delta.content
        
        task.status = "completed"
        task.final_summary = response_text.strip() if response_text.strip() else "Task completed."
        for s in task.steps:
            s.status = "completed"
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        task.status = "failed"
        task.final_summary = f"I ran into an error while working on that: {e}"
    finally:
        task.updated_at = datetime.now().isoformat()
        save_task(task)
        
        if _CALLBACK and inspect.iscoroutinefunction(_CALLBACK):
            await _CALLBACK(task)
