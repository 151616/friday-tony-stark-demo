"""
FRIDAY configuration — all settings, prompts, and constants in one place.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Providers & Models
# ---------------------------------------------------------------------------

STT_PROVIDER       = "sarvam"
LLM_PROVIDER       = "gemini"
TTS_PROVIDER       = "google"

GEMINI_LLM_MODEL   = "gemini-2.5-flash"
OPENAI_LLM_MODEL   = "gpt-4o"
GROQ_LLM_MODEL     = "llama-3.1-8b-instant"
OLLAMA_LLM_MODEL   = "llama3.2:3b"

OPENAI_TTS_MODEL   = "tts-1"
OPENAI_TTS_VOICE   = "nova"
TTS_SPEED          = 1.15

SARVAM_TTS_LANGUAGE = "en-IN"
SARVAM_TTS_SPEAKER  = "rahul"

# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

# Max conversation items (user + assistant messages) to keep in history.
# Smaller = fewer tokens resent per turn = less TPM pressure.
# The system prompt is always preserved.
MAX_HISTORY_ITEMS  = 8

# ---------------------------------------------------------------------------
# Task Orchestration (Phase 0.5)
# ---------------------------------------------------------------------------

TASK_STATE_DIR = Path(__file__).parents[1] / "runtime" / "tasks" / "active"
TASK_STATE_DIR.mkdir(parents=True, exist_ok=True)

TASK_MODE_ENABLED = True
FAST_THINKING_BUDGET = 0
PLANNER_THINKING_BUDGET = 1024
MAX_PLAN_STEPS = 6
TASK_SLOW_THRESHOLD_SECONDS = 1.5
TASK_LONG_THRESHOLD_SECONDS = 5.0

# ---------------------------------------------------------------------------
# App Launcher (Phase 1)
# ---------------------------------------------------------------------------
# Whitelist of desktop apps Friday is allowed to open or close by voice.
# `launch` is the command used with `cmd /c start ""` (resolves via Windows
# App Paths registry). `process` is the executable name used by `taskkill /F /IM`.
APP_WHITELIST = {
    "chrome":     {"launch": "chrome",   "process": "chrome.exe"},
    "spotify":    {"launch": "spotify",  "process": "Spotify.exe"},
    "vscode":     {"launch": "code",     "process": "Code.exe"},
    "discord":    {"launch": "discord",  "process": "Discord.exe"},
    "notepad":    {"launch": "notepad",  "process": "notepad.exe"},
    "explorer":   {"launch": "explorer", "process": "explorer.exe"},
    "terminal":   {"launch": "wt",       "process": "WindowsTerminal.exe"},
    "calculator": {"launch": "calc",     "process": "CalculatorApp.exe"},
    "obsidian":   {"launch": "obsidian", "process": "Obsidian.exe"},
    "claude":     {"launch": "claude",   "process": "Claude.exe"},
}

# Spoken aliases → canonical keys above. Lowercased; matched after exact-key.
APP_ALIASES = {
    "claude ai":        "claude",
    "vs code":          "vscode",
    "code":             "vscode",
    "visual studio code": "vscode",
    "google chrome":    "chrome",
    "browser":          "chrome",
    "file explorer":    "explorer",
    "files":            "explorer",
    "windows terminal": "terminal",
    "cmd":              "terminal",
    "command prompt":   "terminal",
    "powershell":       "terminal",
    "calc":             "calculator",
}

# ---------------------------------------------------------------------------
# File Read Tools (Phase 2)
# ---------------------------------------------------------------------------
# Whitelist of top-level directories Friday is permitted to scan and read.
FRIDAY_FILE_ROOTS = [
    Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "Code" / "friday-tony-stark-demo",
    Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "Documents",
    Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "Downloads",
]

# ---------------------------------------------------------------------------
# Speaker Verification
# ---------------------------------------------------------------------------

VOICE_EMBEDDING_PATH = Path(__file__).parents[1] / "voice_embedding.npy"
SPEAKER_SIM_THRESHOLD = 0.65

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are Friday, a personal AI system. You serve one user. Address him only as "sir" — never by name, never "boss", never anything else.

VOICE
- 1–3 short sentences max. No lists, no markdown, no formatting unless explicitly asked.
- Concise and direct. No enthusiasm. No exclamation marks. No filler.
- Never say "great question", "absolutely", "of course", "sure thing", "happy to help", or anything eager.
- Speak as if reporting status — calm, flat, efficient. A system delivering information, not a person having a conversation.
- Dry wit only through understatement. Never try to be funny.
- Good: "Done.", "Pulling that up now, sir.", "You have three meetings this afternoon.", "I wouldn't recommend that, sir."
- Bad: "Sure thing!", "Got it, Shiv!", "Here you go!", "Absolutely!"

KNOWLEDGE
- Your training data may be outdated. For ANY question about current events, conflicts, politics, wars, people in the news, or "what's happening with X" — ALWAYS use search_web first. Never guess or say "nothing is happening" based on your own knowledge.

TOOLS
- Only use tools that are actually available in the current turn. The active tool surface changes by request. Never invent a tool name that is not present.
- Use search for current events, politics, wars, conflicts, or other current factual questions whenever a search tool is available. Never guess.
- Use the available app, system, messaging, memory, research, file, media, calendar, email, or delegation tools when they clearly fit the request.
- Follow confirmation requirements exposed by the tool descriptions for destructive actions.
- Do not use tools for casual conversation or stable general knowledge questions unless current information or a real action is required.
- Summarize information in your own words. Never read out URLs, source names, or raw formatting.
- Never claim an action succeeded unless the tool result clearly says it succeeded.
- After completing an action, confirm in one short line. No follow-up questions unless information is missing.

DISMISSAL: If he says "that'll be all", "stand down", "go to sleep", or "goodbye", respond with a brief, composed sign-off.
""".strip()

# ---------------------------------------------------------------------------
# Dismissal
# ---------------------------------------------------------------------------

DISMISSAL_PHRASES = [
    "that'll be all",
    "that will be all",
    "stand down",
    "go to sleep",
    "goodbye friday",
    "goodbye jarvis",
]

SLEEP_RESPONSES = [
    "I'll be here if you need me.",
    "Alright, catch you later.",
    "Going quiet. Just say the word if you need anything.",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("friday-agent")
logger.setLevel(logging.INFO)

# Silence noisy loggers from Resemblyzer → librosa → numba JIT compilation
for _noisy in ("numba", "numba.core", "numba.cuda", "numba.np", "numba.typed"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
