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
- get_world_news: when he asks for general news, headlines, or a world briefing.
- search_web: when he asks about a specific topic, event, conflict, person, country, etc. Always prefer searching over guessing.
- open_world_monitor: only when he says "open" or "show" the monitor.
- launch_app: when he says "open <app>", "launch <app>", or "start <app>". Pass the app name as he said it — Friday auto-discovers everything installed via Start Menu, plus accepts aliases.
- close_app: when he says "close <app>" or "quit <app>". Same name handling.
- rescan_apps: only when he says he just installed something new and Friday can't find it, or explicitly says "rescan apps".
- set_volume: set system volume or app-specific volume (0-100). Pass app="spotify" for Spotify, app="chrome" for YouTube/browser, or leave app empty for system master volume.
- play_pause_media / next_track / previous_track: media playback controls.
- current_track: when he asks "what's playing", "what song is this", or "what's the current track".
- search_spotify: when he says "play <song/playlist/album>". Pass the query as he says it. Set type="playlist" for playlists, type="album" for albums, or type="track" (default) for songs.
- recognize_song_humming: when he asks to identify a song he is humming/singing, or says "shazam this".
- create_document: when he says "open a fresh slide", "new word doc", "create a spreadsheet". Types are slide, doc, sheet, repo.
- draft_message: when he says "text <person>" or "message <person>". Provide platform and text.
- list_files: when he asks what is inside a specific folder.
- read_file: when he asks you to read or summarize a specific file.
- search_files: when he wants to find a file by name or keyword.
- write_file: when he asks to create a file or write content to a file. Creates or overwrites.
- create_folder: when he asks to create a new folder.
- move_file: when he asks to move or rename a file/folder. ALWAYS confirm with the user before calling.
- copy_file: when he asks to copy a file or folder.
- delete_file: when he asks to delete a file or folder. ALWAYS call with confirm=false first to describe what will be deleted, then only call with confirm=true after the user explicitly confirms.
- list_upcoming_events: when he asks about his schedule, agenda, or calendar.
- list_recent_emails: when he asks to check his emails or inbox.
- remember: when he says "remember this", "from now on", "always do X", "next time do X", or any instruction that should persist. Save the preference as a clear, actionable rule.
- forget: when he says "forget that", "stop doing X", "nevermind about X". Pass a keyword to match.
- list_memories: when he asks "what do you remember" or "what are my preferences".
- ask_claude: when he says "ask Claude", "delegate to Claude", "have Claude figure out", or when a question requires deep analysis, code generation, or research synthesis that you cannot handle well yourself. This runs Claude Code in the background — you will speak the result when it finishes.
- Do not use tools for casual conversation or general knowledge questions.
- Summarize information in your own words. Never read out URLs, source names, or raw formatting.
- After completing an action (launching an app, playing a song, drafting a message), confirm in one short line. No follow-up questions.

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
