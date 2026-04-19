"""Persistent memory — saves user preferences across sessions."""
import json
from pathlib import Path
from datetime import datetime
from mcp.server.fastmcp import FastMCP

MEMORY_FILE = Path(__file__).resolve().parents[2] / "runtime" / "memory.json"
MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_memories() -> list[dict]:
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_memories(memories: list[dict]):
    MEMORY_FILE.write_text(json.dumps(memories, indent=2), encoding="utf-8")


def get_memories_prompt() -> str:
    """Return a formatted string of all memories for injection into the system prompt."""
    memories = _load_memories()
    if not memories:
        return ""
    lines = [f"- {m['content']}" for m in memories]
    return "USER PREFERENCES (follow these at all times):\n" + "\n".join(lines)


def register(mcp: FastMCP):

    @mcp.tool(name="remember")
    def remember(content: str) -> str:
        """Save a user preference or instruction to persistent memory.
        Use this when the user says 'remember this', 'from now on', 'always do X',
        'next time do X', or any instruction meant to persist across sessions."""
        memories = _load_memories()
        memories.append({
            "content": content,
            "saved_at": datetime.now().isoformat(),
        })
        _save_memories(memories)
        return f"Noted. I'll remember that."

    @mcp.tool(name="forget")
    def forget(keyword: str) -> str:
        """Remove a saved preference that contains the given keyword.
        Use when the user says 'forget that', 'stop doing X', 'nevermind about X'."""
        memories = _load_memories()
        before = len(memories)
        memories = [m for m in memories if keyword.lower() not in m["content"].lower()]
        after = len(memories)
        if before == after:
            return f"I don't have any memories matching '{keyword}'."
        _save_memories(memories)
        return f"Done. Removed {before - after} preference(s)."

    @mcp.tool(name="list_memories")
    def list_memories() -> str:
        """List all saved user preferences. Use when the user asks
        'what do you remember' or 'what are my preferences'."""
        memories = _load_memories()
        if not memories:
            return "I don't have any saved preferences yet."
        lines = [f"- {m['content']}" for m in memories]
        return "Your saved preferences:\n" + "\n".join(lines)
