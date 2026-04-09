"""
FRIDAY Launcher — Wake Word Activated Voice Assistant
=====================================================
Single entry point that manages:
1. MCP Server subprocess (always running)
2. OpenWakeWord listener (always running)
3. LiveKit voice sessions (on-demand)

Usage:
    uv run friday_start
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import winsound
from enum import Enum
from pathlib import Path

import numpy as np
import pyaudio
from dotenv import load_dotenv
from openwakeword.model import Model as WakeWordModel
from friday_overlay import FridayOverlay

load_dotenv()

logger = logging.getLogger("friday-launcher")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WAKE_MODEL = "hey_jarvis_v0.1"
WAKE_THRESHOLD = 0.7
SILENCE_TIMEOUT = 30.0
AUDIO_RATE = 16000
AUDIO_CHUNK = 1280  # 80ms at 16kHz
CHIME_PATH = Path(__file__).parent / "sounds" / "activate.wav"
MCP_SERVER_SCRIPT = Path(__file__).parent / "server.py"


class State(Enum):
    SLEEPING = "sleeping"
    ACTIVE = "active"


# ---------------------------------------------------------------------------
# MCP Server management
# ---------------------------------------------------------------------------

class MCPServerManager:
    """Keeps the MCP server subprocess alive."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None

    def start(self):
        if self._proc and self._proc.poll() is None:
            return
        logger.info("Starting MCP server...")
        self._proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "server.py")],
            cwd=Path(__file__).parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info("MCP server started (PID %d)", self._proc.pid)

    def ensure_alive(self):
        if self._proc is None or self._proc.poll() is not None:
            if self._proc is not None:
                logger.warning("MCP server died, restarting...")
            self.start()

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait(timeout=5)
            logger.info("MCP server stopped")


# ---------------------------------------------------------------------------
# Wake word listener
# ---------------------------------------------------------------------------

class WakeWordListener:
    """Continuously listens for the wake word on the mic."""

    def __init__(self, model_name: str = WAKE_MODEL, threshold: float = WAKE_THRESHOLD):
        self._model = WakeWordModel(wakeword_models=[model_name])
        self._threshold = threshold
        self._audio = pyaudio.PyAudio()
        self._stream = None
        self._enabled = True

    def start_stream(self):
        self._stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=AUDIO_RATE,
            input=True,
            frames_per_buffer=AUDIO_CHUNK,
        )
        logger.info("Mic stream opened for wake word detection")

    def stop_stream(self):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None

    def listen_once(self) -> bool:
        """Block until wake word is detected. Returns True if detected."""
        if not self._stream:
            self.start_stream()

        raw = self._stream.read(AUDIO_CHUNK, exception_on_overflow=False)
        audio = np.frombuffer(raw, dtype=np.int16)
        prediction = self._model.predict(audio)

        for model_name, score in prediction.items():
            if score >= self._threshold:
                logger.info("Wake word detected! (model=%s, score=%.3f)", model_name, score)
                return True
        return False

    def cleanup(self):
        self.stop_stream()
        self._audio.terminate()


# ---------------------------------------------------------------------------
# Chime
# ---------------------------------------------------------------------------

def play_chime():
    """Play activation chime in a background thread."""
    def _play():
        try:
            winsound.PlaySound(str(CHIME_PATH), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            logger.warning("Could not play chime: %s", e)
    threading.Thread(target=_play, daemon=True).start()


# ---------------------------------------------------------------------------
# Main launcher loop
# ---------------------------------------------------------------------------

async def launcher_loop():
    mcp = MCPServerManager()
    wakeword = WakeWordListener()
    overlay = FridayOverlay()

    mcp.start()
    wakeword.start_stream()
    overlay.start()

    state = State.SLEEPING
    logger.info("FRIDAY launcher ready — say 'Hey Jarvis' to activate")

    try:
        while True:
            if state == State.SLEEPING:
                # Check MCP server health
                mcp.ensure_alive()

                # Listen for wake word (non-blocking check)
                detected = await asyncio.get_event_loop().run_in_executor(
                    None, wakeword.listen_once
                )
                if detected:
                    play_chime()
                    overlay.show()
                    state = State.ACTIVE
                    logger.info("State → ACTIVE")

            elif state == State.ACTIVE:
                # Stop wake word stream while LiveKit uses the mic
                wakeword.stop_stream()

                # Launch voice agent in console mode (local mic/speaker)
                # This uses LiveKit's built-in console with proper job context
                voice_proc = subprocess.Popen(
                    [sys.executable, str(Path(__file__).parent / "agent_friday.py"), "console"],
                    cwd=Path(__file__).parent,
                )
                logger.info("Voice agent started in console mode (PID %d)", voice_proc.pid)

                # Wait for the voice agent process to exit
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, voice_proc.wait
                    )
                except Exception as e:
                    logger.error("Voice session error: %s", e)
                finally:
                    if voice_proc.poll() is None:
                        voice_proc.terminate()
                        voice_proc.wait(timeout=5)

                # Hide overlay and resume wake word listening
                overlay.hide()
                wakeword.start_stream()
                state = State.SLEEPING
                logger.info("State → SLEEPING")

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        overlay.stop()
        wakeword.cleanup()
        mcp.stop()
        logger.info("FRIDAY launcher stopped")


def main():
    asyncio.run(launcher_loop())


if __name__ == "__main__":
    main()
