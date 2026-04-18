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
TTS_PROVIDER       = "deepgram"

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
You are Friday, a smart, chill AI assistant for Shiv. Think of yourself as a helpful friend who happens to know everything — warm but not over-the-top, relaxed but sharp.

VOICE
- Keep it natural and conversational — like talking to a friend, not a robot.
- 1–3 short sentences max. No lists, no markdown, no formatting unless explicitly asked to list.
- Don't call him "boss", "sir" is best. Just talk normally, a little formal, but keeping it natural. 
- Use casual language: "yeah", "sure thing", "got it", "hmm let me check", etc.

KNOWLEDGE
- Your training data may be outdated. For ANY question about current events, conflicts, politics, wars, people in the news, or "what's happening with X" — ALWAYS use search_web first. Never guess or say "nothing is happening" based on your own knowledge.

TOOLS
- get_world_news: when he asks for general news, headlines, or a world briefing.
- search_web: when he asks about a specific topic, event, conflict, person, country, etc. Always prefer searching over guessing.
- open_world_monitor: only when he says "open" or "show" the monitor.
- launch_app: when he says "open <app>", "launch <app>", or "start <app>" (e.g. Spotify, PrusaSlicer, WPILib VS Code). Pass the app name as he said it — Friday auto-discovers everything installed via Start Menu, plus accepts aliases.
- close_app: when he says "close <app>" or "quit <app>". Same name handling.
- rescan_apps: only when he says he just installed something new and Friday can't find it, or explicitly says "rescan apps".
- play_pause_media / next_track / previous_track: when he says "pause music", "resume spotify", "skip", "next song", etc.
- next_track / previous_track: when he says "skip", "next song", etc.
- search_spotify: when he says "play <song>" or "find <artist> on spotify". Pass the query as he says it.
- recognize_song_humming: when he asks to identify a song he is humming/singing, or when he says "shazam this".
- create_document: when he says "open a fresh slide", "new word doc", "create a spreadsheet". Types are slide, doc, sheet, repo.
- draft_message: when he says "text <person> in whatsapp" or "message <person> on discord". Provide platform and text.
- list_files: when he asks what is inside a specific folder like Downloads, Documents, or Friday root.
- read_file: when he asks you to read or summarize a specific text file.
- search_files: when he wants to find a file by name or keyword.
- list_upcoming_events: when he asks what is on his schedule, agenda, or calendar over the next few days.
- list_recent_emails: when he asks to check his emails, scan his inbox, or read his unread messages.
- Don't use tools for casual chat, jokes, or general knowledge questions that don't need current info.
- When sharing info, summarize it naturally in your own words. Don't read out source names, URLs, or raw formatting.
- After launching or closing an app, changing a song, or drafting a text, just say one short line ("Opening Spotify." / "Done."). No follow-up questions unless he asks.

DISMISSAL: If Shiv says "that'll be all", "stand down", "go to sleep", or "goodbye", give a short casual sign-off.
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
