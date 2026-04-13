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
- 1–3 short sentences max. No lists, no markdown, no formatting.
- Don't call Shiv "sir" or "boss". Just talk normally. Use his name sparingly — mostly just respond directly.
- Use casual language: "yeah", "sure thing", "got it", "hmm let me check", etc.

KNOWLEDGE
- Your training data may be outdated. For ANY question about current events, conflicts, politics, wars, people in the news, or "what's happening with X" — ALWAYS use search_web first. Never guess or say "nothing is happening" based on your own knowledge.

TOOLS
- get_world_news: when he asks for general news, headlines, or a world briefing.
- search_web: when he asks about a specific topic, event, conflict, person, country, etc. Always prefer searching over guessing.
- open_world_monitor: only when he says "open" or "show" the monitor.
- Don't use tools for casual chat, jokes, or general knowledge questions that don't need current info.
- When sharing info, summarize it naturally in your own words. Don't read out source names, URLs, or raw formatting.

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
