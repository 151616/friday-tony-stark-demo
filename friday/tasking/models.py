"""Data models for Phase 0.5 Task Orchestration."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class TaskStep(BaseModel):
    id: int
    title: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    tool: Optional[str] = None
    args_preview: Optional[str] = None
    result_summary: Optional[str] = None

class TaskRecord(BaseModel):
    task_id: str
    goal: str
    status: Literal["pending", "running", "waiting_for_confirmation", "waiting_for_external_work", "completed", "failed", "cancelled"] = "pending"
    mode: Literal["fast", "planner"] = "planner"
    source: Literal["voice", "telegram", "discord", "other"] = "voice"
    created_at: str
    updated_at: str
    current_step: Optional[int] = None
    steps: List[TaskStep] = Field(default_factory=list)
    last_tool_result: Optional[str] = None
    final_summary: Optional[str] = None
