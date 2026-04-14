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
# MCP server no longer needed — tools are registered directly on the agent

# Speaker verification
VOICE_EMBEDDING_PATH = Path(__file__).parent / "voice_embedding.npy"
SPEAKER_SIM_THRESHOLD = 0.70   # cosine similarity; tune between 0.65–0.80
SPEAKER_BUFFER_SECONDS = 2.5   # last N seconds of mic audio to verify against


class State(Enum):
    SLEEPING = "sleeping"
    ACTIVE = "active"


# ---------------------------------------------------------------------------
# Wake word listener
# ---------------------------------------------------------------------------

class WakeWordListener:
    """Continuously listens for the wake word on the mic."""

    def __init__(self, model_name: str = WAKE_MODEL, threshold: float = WAKE_THRESHOLD):
        # Use onnx instead of tflite — tflite-runtime has no Windows wheels.
        self._model = WakeWordModel(
            wakeword_models=[model_name],
            inference_framework="onnx",
        )
        self._threshold = threshold
        self._audio = pyaudio.PyAudio()
        self._stream = None
        self._enabled = True
        # Ring buffer of the last SPEAKER_BUFFER_SECONDS of int16 audio.
        self._buffer_max = int(AUDIO_RATE * SPEAKER_BUFFER_SECONDS)
        self._buffer = np.zeros(self._buffer_max, dtype=np.int16)
        self._buffer_pos = 0

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

    def reset(self):
        """Clear openwakeword's internal feature/prediction buffers and the
        rolling audio ring buffer. Call this after a voice session ends so
        stale state can't produce an instant false wake.
        """
        try:
            self._model.reset()
        except Exception as e:
            logger.debug("openwakeword reset failed (non-fatal): %s", e)
        self._buffer[:] = 0
        self._buffer_pos = 0

    def _append_to_buffer(self, audio: np.ndarray) -> None:
        n = len(audio)
        if n >= self._buffer_max:
            self._buffer = audio[-self._buffer_max:].copy()
            self._buffer_pos = 0
            return
        end = self._buffer_pos + n
        if end <= self._buffer_max:
            self._buffer[self._buffer_pos:end] = audio
        else:
            split = self._buffer_max - self._buffer_pos
            self._buffer[self._buffer_pos:] = audio[:split]
            self._buffer[: n - split] = audio[split:]
        self._buffer_pos = end % self._buffer_max

    def recent_audio_float(self) -> np.ndarray:
        """Return the rolling buffer as a contiguous float32 waveform in [-1, 1]."""
        ordered = np.concatenate(
            (self._buffer[self._buffer_pos:], self._buffer[: self._buffer_pos])
        )
        return ordered.astype(np.float32) / 32768.0

    def listen_once(self) -> bool:
        """Block until wake word is detected. Returns True if detected."""
        if not self._stream:
            self.start_stream()

        raw = self._stream.read(AUDIO_CHUNK, exception_on_overflow=False)
        audio = np.frombuffer(raw, dtype=np.int16)
        self._append_to_buffer(audio)
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
# Speaker verification (Resemblyzer)
# ---------------------------------------------------------------------------

class SpeakerVerifier:
    """Compares incoming audio against an enrolled voice embedding."""

    def __init__(self, embedding_path: Path = VOICE_EMBEDDING_PATH,
                 threshold: float = SPEAKER_SIM_THRESHOLD):
        self._threshold = threshold
        self._encoder = None
        self._reference = None
        if embedding_path.exists():
            try:
                self._reference = np.load(embedding_path)
                from resemblyzer import VoiceEncoder  # heavy import, lazy
                self._encoder = VoiceEncoder(verbose=False)
                logger.info(
                    "SpeakerVerifier loaded (threshold=%.2f, ref shape=%s)",
                    threshold, self._reference.shape,
                )
            except Exception as e:
                logger.warning("SpeakerVerifier init failed (%s); gate disabled", e)
                self._encoder = None
                self._reference = None
        else:
            logger.warning(
                "No voice embedding at %s — speaker gate disabled. "
                "Run: python enroll_voice.py",
                embedding_path,
            )

    @property
    def enabled(self) -> bool:
        return self._encoder is not None and self._reference is not None

    def verify(self, wav_float: np.ndarray) -> tuple[bool, float]:
        """Return (matched, similarity). If disabled, always (True, 1.0)."""
        if not self.enabled:
            return True, 1.0
        try:
            emb = self._encoder.embed_utterance(wav_float)
            ref = self._reference
            sim = float(np.dot(emb, ref) / ((np.linalg.norm(emb) * np.linalg.norm(ref)) + 1e-9))
            return sim >= self._threshold, sim
        except Exception as e:
            logger.warning("Speaker verify failed (%s); allowing", e)
            return True, 1.0


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

class AgentProcess:
    """Manages the single long-lived agent_friday.py subprocess.

    Protocol (line-based, over stdin/stdout):
        launcher → subprocess stdin:   START | QUIT
        subprocess stdout → launcher:  FRIDAY_READY | SESSION_STARTED | SESSION_DONE
                                       PROCESSING | SPEAKING
    """

    def __init__(self, on_processing=None, on_speaking=None):
        self._proc: subprocess.Popen | None = None
        self._ready = threading.Event()
        self._session_done = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._on_processing = on_processing  # callback when LLM starts thinking
        self._on_speaking = on_speaking       # callback when first TTS content arrives

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self):
        """Spawn the subprocess and wait for FRIDAY_READY."""
        if self.alive:
            return
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        self._ready.clear()
        self._session_done.clear()
        self._proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "agent_friday.py"), "console"],
            cwd=Path(__file__).parent,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        logger.info("Agent subprocess started (PID %d) — cold-booting models…",
                     self._proc.pid)
        self._reader_thread = threading.Thread(
            target=self._read_stdout, daemon=True
        )
        self._reader_thread.start()

    def _read_stdout(self):
        """Drain subprocess stdout, dispatch signals, echo everything else."""
        try:
            assert self._proc and self._proc.stdout
            for line in self._proc.stdout:
                stripped = line.rstrip()
                if "FRIDAY_READY" in stripped:
                    logger.info("Agent subprocess signalled FRIDAY_READY")
                    self._ready.set()
                elif "SESSION_STARTED" in stripped:
                    logger.info("Agent subprocess signalled SESSION_STARTED")
                elif "SESSION_DONE" in stripped:
                    logger.info("Agent subprocess signalled SESSION_DONE")
                    self._session_done.set()
                elif "PROCESSING" in stripped:
                    if self._on_processing:
                        self._on_processing()
                elif "SPEAKING" in stripped:
                    if self._on_speaking:
                        self._on_speaking()
                elif stripped:
                    print(stripped, flush=True)
        except Exception as e:
            logger.debug("stdout reader error: %s", e)
        finally:
            self._ready.set()
            self._session_done.set()

    async def wait_ready(self, timeout: float = 60.0) -> bool:
        """Block until FRIDAY_READY (or timeout/death)."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._ready.wait, timeout
        )

    def send_start(self):
        """Tell the subprocess to begin a new voice session."""
        if not self.alive:
            logger.warning("Cannot send START — agent subprocess is dead")
            return
        self._session_done.clear()
        assert self._proc and self._proc.stdin
        try:
            self._proc.stdin.write("START\n")
            self._proc.stdin.flush()
        except Exception as e:
            logger.error("Failed to write START: %s", e)

    async def wait_session_done(self):
        """Block until SESSION_DONE (or subprocess death)."""
        await asyncio.get_event_loop().run_in_executor(
            None, self._session_done.wait
        )

    def stop(self):
        """Gracefully shut down the subprocess."""
        if not self.alive:
            return
        try:
            assert self._proc and self._proc.stdin
            self._proc.stdin.write("QUIT\n")
            self._proc.stdin.flush()
        except Exception:
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.terminate()
            self._proc.wait(timeout=3)
        logger.info("Agent subprocess stopped")


async def launcher_loop():
    wakeword = WakeWordListener()
    overlay = FridayOverlay()
    verifier = SpeakerVerifier()
    agent = AgentProcess(
        on_processing=lambda: overlay.show_loading("Thinking..."),
        on_speaking=lambda: overlay.hide_loading(),
    )

    overlay.start()

    # ---- One-time cold boot: spawn the agent and load models ----
    overlay.show_loading("Booting up Omnicron...")
    agent.start()
    ready = await agent.wait_ready(timeout=60.0)
    if not ready or not agent.alive:
        logger.error("Agent subprocess failed to start — exiting")
        overlay.stop()
        return
    overlay.hide()           # hide the initial boot overlay
    logger.info("Agent subprocess ready — models loaded")

    wakeword.start_stream()
    state = State.SLEEPING
    logger.info("FRIDAY launcher ready — say 'Hey Jarvis' to activate")

    try:
        while True:
            if state == State.SLEEPING:
                # If the agent subprocess died between sessions, respawn it.
                if not agent.alive:
                    logger.warning("Agent subprocess died — respawning…")
                    overlay.show_loading("Rebooting FRIDAY...")
                    wakeword.stop_stream()
                    agent.start()
                    await agent.wait_ready(timeout=60.0)
                    overlay.hide()
                    wakeword.start_stream()

                detected = await asyncio.get_event_loop().run_in_executor(
                    None, wakeword.listen_once
                )
                if detected:
                    # Instant feedback — chime + loading overlay the moment
                    # the wake word is recognised, BEFORE speaker verification.
                    play_chime()
                    overlay.show_loading("Waking up...")

                    if verifier.enabled:
                        wav = wakeword.recent_audio_float()
                        matched, sim = await asyncio.get_event_loop().run_in_executor(
                            None, verifier.verify, wav
                        )
                        if not matched:
                            logger.info(
                                "Wake word ignored — speaker mismatch (sim=%.3f < %.2f)",
                                sim, SPEAKER_SIM_THRESHOLD,
                            )
                            overlay.hide()
                            continue
                        logger.info("Speaker verified (sim=%.3f)", sim)
                    state = State.ACTIVE
                    logger.info("State → ACTIVE")

            elif state == State.ACTIVE:
                wakeword.stop_stream()

                # Tell the already-running subprocess to start a session.
                # The overlay shows "Waking up..." from the wake word handler;
                # it'll switch to bars when the agent sends SPEAKING, or
                # show "Thinking..." on PROCESSING signals.
                agent.send_start()

                # Wait for the session to end (dismissal or crash).
                await agent.wait_session_done()

                overlay.hide()
                await asyncio.sleep(1.5)
                wakeword.reset()
                wakeword.start_stream()
                state = State.SLEEPING
                logger.info("State → SLEEPING")

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        overlay.stop()
        wakeword.cleanup()
        agent.stop()
        logger.info("FRIDAY launcher stopped")


def main():
    asyncio.run(launcher_loop())


if __name__ == "__main__":
    main()
