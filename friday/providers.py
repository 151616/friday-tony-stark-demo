"""
Provider factories — build STT, LLM, and TTS instances.

Each factory creates a fresh provider instance. Call once per session
since the SDK tears down internal WebSocket connections on session.aclose().
"""

import os
from .config import (
    STT_PROVIDER, LLM_PROVIDER, TTS_PROVIDER,
    GEMINI_LLM_MODEL, OPENAI_LLM_MODEL, GROQ_LLM_MODEL, OLLAMA_LLM_MODEL,
    OPENAI_TTS_MODEL, OPENAI_TTS_VOICE, TTS_SPEED,
    SARVAM_TTS_LANGUAGE, SARVAM_TTS_SPEAKER,
    FAST_THINKING_BUDGET, PLANNER_THINKING_BUDGET,
    logger,
)

from typing import Literal

from livekit.plugins import (
    deepgram as lk_deepgram,
    google as lk_google,
    openai as lk_openai,
    sarvam,
)


def build_stt(http_session=None):
    if STT_PROVIDER == "sarvam":
        logger.info("STT → Sarvam Saaras v3")
        return sarvam.STT(
            language="en-IN",
            model="saaras:v3",
            mode="transcribe",
            flush_signal=True,
            sample_rate=16000,
            http_session=http_session,
        )
    elif STT_PROVIDER == "whisper":
        logger.info("STT → OpenAI Whisper")
        return lk_openai.STT(model="whisper-1")
    else:
        raise ValueError(f"Unknown STT_PROVIDER: {STT_PROVIDER!r}")


def build_llm(mode: Literal["fast", "planner"] = "fast"):
    budget = PLANNER_THINKING_BUDGET if mode == "planner" else FAST_THINKING_BUDGET
    
    if LLM_PROVIDER == "openai":
        logger.info("LLM → OpenAI (%s) [mode=%s]", OPENAI_LLM_MODEL, mode)
        return lk_openai.LLM(model=OPENAI_LLM_MODEL)
    elif LLM_PROVIDER == "gemini":
        logger.info("LLM → Google Gemini (%s) [mode=%s, budget=%d]", GEMINI_LLM_MODEL, mode, budget)
        return lk_google.LLM(
            model=GEMINI_LLM_MODEL,
            api_key=os.getenv("GOOGLE_API_KEY"),
            # Only supply a thinking_config if budget is positive
            thinking_config={"thinking_budget": budget} if budget > 0 else None,
        )
    elif LLM_PROVIDER == "groq":
        logger.info("LLM → Groq (%s)", GROQ_LLM_MODEL)
        return lk_openai.LLM(
            model=GROQ_LLM_MODEL,
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
    elif LLM_PROVIDER == "ollama":
        logger.info("LLM → Ollama (%s)", OLLAMA_LLM_MODEL)
        import httpx
        return lk_openai.LLM(
            model=OLLAMA_LLM_MODEL,
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")


def build_tts(http_session=None):
    if TTS_PROVIDER == "sarvam":
        logger.info("TTS → Sarvam Bulbul v3")
        return sarvam.TTS(
            target_language_code=SARVAM_TTS_LANGUAGE,
            model="bulbul:v3",
            speaker=SARVAM_TTS_SPEAKER,
            pace=TTS_SPEED,
            http_session=http_session,
        )
    elif TTS_PROVIDER == "openai":
        logger.info("TTS → OpenAI TTS (%s / %s)", OPENAI_TTS_MODEL, OPENAI_TTS_VOICE)
        return lk_openai.TTS(model=OPENAI_TTS_MODEL, voice=OPENAI_TTS_VOICE, speed=TTS_SPEED)
    elif TTS_PROVIDER == "deepgram":
        logger.info("TTS → Deepgram Aura 2")
        return lk_deepgram.TTS(
            model="aura-2-andromeda-en",
            encoding="linear16",
            sample_rate=24000,
            http_session=http_session,
        )
    elif TTS_PROVIDER == "google":
        logger.info("TTS → Google Gemini TTS")
        return lk_google.TTS(
            model_name="gemini-2.5-flash-tts",
            credentials_info={"api_key": os.getenv("GOOGLE_API_KEY")},
        )
    else:
        raise ValueError(f"Unknown TTS_PROVIDER: {TTS_PROVIDER!r}")
