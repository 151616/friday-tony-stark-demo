"""
FRIDAY – Voice Agent
====================
Iron Man-style voice assistant powered by LiveKit Agents SDK.
All config lives in friday/config.py, providers in friday/providers.py.

Run:
  friday_start             – full launcher with wake word
  python agent_friday.py console  – text-only console mode
"""

import asyncio
import os
import re
import random
import sys

import numpy as np

# ---------------------------------------------------------------------------
# Mic selection — apply BEFORE livekit imports, so sounddevice picks it up.
# Set SESSION_MIC=<name substring> in your .env (e.g. "USB Microphone") to
# route the agent's mic capture to a specific device. Empty = system default.
# ---------------------------------------------------------------------------
def _apply_session_mic() -> None:
    name = os.getenv("SESSION_MIC", "").strip()
    if not name:
        return
    try:
        import sounddevice as sd
        needle = name.lower()
        for idx, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels", 0)) <= 0:
                continue
            if needle in info["name"].lower():
                # Tuple is (input, output); leave output as default.
                sd.default.device = (idx, sd.default.device[1])
                print(f"SESSION_MIC resolved: {info['name']!r} (idx={idx})",
                      flush=True)
                return
        print(f"SESSION_MIC {name!r} not found — using system default", flush=True)
    except Exception as e:
        print(f"SESSION_MIC setup failed: {e}", flush=True)

_apply_session_mic()

from pathlib import Path

from livekit import rtc
from livekit.agents import (
    JobContext, WorkerOptions, cli,
    llm as lk_llm, stt, TurnHandlingOptions,
)
from livekit.agents.llm.mcp import MCPServerStdio, MCPToolset
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.voice.turn import InterruptionOptions, EndpointingOptions
from livekit.plugins import silero

from friday.config import (
    SYSTEM_PROMPT, DISMISSAL_PHRASES, SLEEP_RESPONSES,
    STT_PROVIDER, LLM_PROVIDER, TTS_PROVIDER,
    MAX_HISTORY_ITEMS, logger,
)
from friday.providers import build_stt, build_llm, build_tts
from friday.speaker_gate import get_speaker_gate

# Repo root — used to locate server.py when spawning the MCP subprocess.
_REPO_ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Tool-call leakage scrubber (only needed for llama models via Groq/Ollama)
# ---------------------------------------------------------------------------

_TOOL_LEAK_RE = re.compile(
    r"""
    (?:
        <\|python_tag\|>
      | <\|?function[^>|]*\|?>
      | </function>
      | <tool_call>.*?(?:</tool_call>|$)
      | function\s*=\s*["'<]?\w+["'>]?
      | \{\s*["']name["']\s*:\s*["'][^"']+["'].*?\}
    )
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


class _ToolLeakScrubber:
    """Strips tool-call syntax leaked into assistant text by llama models."""

    SAFE_TAIL = 64

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._pending += text
        self._pending = _TOOL_LEAK_RE.sub("", self._pending)
        if len(self._pending) > self.SAFE_TAIL:
            out = self._pending[: -self.SAFE_TAIL]
            self._pending = self._pending[-self.SAFE_TAIL :]
            return out
        return ""

    def flush(self) -> str:
        out = _TOOL_LEAK_RE.sub("", self._pending)
        self._pending = ""
        return out


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class FridayAgent(Agent):
    """F.R.I.D.A.Y. voice agent. Tools come from the local MCP server
    (see server.py + friday/tools/). This class keeps voice-specific
    concerns: speaker gating, history trimming, streaming signals, greeting."""

    def __init__(self, stt, llm, tts, vad=None) -> None:
        from friday.tools.memory import get_memories_prompt
        memories = get_memories_prompt()
        full_prompt = SYSTEM_PROMPT + ("\n\n" + memories if memories else "")
        super().__init__(
            instructions=full_prompt,
            stt=stt, llm=llm, tts=tts,
            vad=vad or silero.VAD.load(
                # Bumped from 0.92 / 0.5 to filter out background chatter,
                # typing, distant voices, brief noises during a session.
                activation_threshold=0.95,
                min_speech_duration=0.7,
                min_silence_duration=0.8,
            ),
        )

    # -- Speaker-gated STT ------------------------------------------------

    async def stt_node(self, audio, model_settings):
        """Only yield transcripts from the enrolled voice."""
        gate = get_speaker_gate()
        if not gate.enabled:
            async for ev in Agent.default.stt_node(self, audio, model_settings):
                yield ev
            return

        audio_buf: list[rtc.AudioFrame] = []
        sample_rate = 16000

        async def _buffered_audio():
            nonlocal sample_rate
            async for frame in audio:
                audio_buf.append(frame)
                sample_rate = frame.sample_rate
                yield frame

        async for ev in Agent.default.stt_node(self, _buffered_audio(), model_settings):
            if not isinstance(ev, stt.SpeechEvent):
                yield ev
                continue
            if ev.type not in (
                stt.SpeechEventType.FINAL_TRANSCRIPT,
                stt.SpeechEventType.INTERIM_TRANSCRIPT,
            ):
                yield ev
                continue

            if audio_buf:
                pcm = np.concatenate(
                    [np.frombuffer(f.data, dtype=np.int16) for f in audio_buf]
                )
                is_user = gate.verify(pcm, sample_rate)
            else:
                is_user = True

            if is_user:
                yield ev
            else:
                text = ev.alternatives[0].text if ev.alternatives else ""
                logger.info("Suppressed non-user transcript: %r (type=%s)",
                            text[:60], ev.type.name)
            audio_buf.clear()

    # -- LLM with history trimming + optional scrubber --------------------

    async def llm_node(self, chat_ctx, tools, model_settings):
        """Trim history and optionally scrub tool-call leaks (llama only)."""
        if MAX_HISTORY_ITEMS and len(chat_ctx.items) > MAX_HISTORY_ITEMS:
            chat_ctx = chat_ctx.truncate(max_items=MAX_HISTORY_ITEMS)

        # Signal the launcher that we're thinking
        print("PROCESSING", flush=True)

        use_scrubber = LLM_PROVIDER in ("groq", "ollama")
        scrubber = _ToolLeakScrubber() if use_scrubber else None
        first_content = True

        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            # Signal when first real content arrives (TTS will start speaking)
            if (
                first_content
                and isinstance(chunk, lk_llm.ChatChunk)
                and chunk.delta is not None
                and chunk.delta.content
            ):
                print("SPEAKING", flush=True)
                first_content = False

            if (
                scrubber
                and isinstance(chunk, lk_llm.ChatChunk)
                and chunk.delta is not None
                and chunk.delta.content
            ):
                cleaned = scrubber.feed(chunk.delta.content)
                if cleaned or chunk.delta.tool_calls:
                    new_delta = chunk.delta.model_copy(
                        update={"content": cleaned if cleaned else None}
                    )
                    yield chunk.model_copy(update={"delta": new_delta})
            else:
                yield chunk

        if scrubber:
            tail = scrubber.flush()
            if tail:
                yield lk_llm.ChatChunk(
                    id="scrub-tail",
                    delta=lk_llm.ChoiceDelta(role="assistant", content=tail),
                )

    # -- Greeting ---------------------------------------------------------

    async def on_enter(self) -> None:
        # Intentionally silent. Greetings are fired from the activation loop
        # in entrypoint() on each START — this lets us pre-start the session
        # during boot (paying VAD load + connection setup up-front) without
        # the agent speaking into an empty room. Result: first "hey jarvis"
        # feels as snappy as re-activation.
        logger.info("on_enter — session attached (greeting deferred to activation)")


# ---------------------------------------------------------------------------
# Session entrypoint (stdin/stdout protocol with friday_launcher.py)
# ---------------------------------------------------------------------------

def _endpointing_delay() -> float:
    return {"sarvam": 0.07, "whisper": 0.3}.get(STT_PROVIDER, 0.1)


async def _wait_for_stdin_command() -> str:
    """Block until START or QUIT arrives on stdin."""
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return ""
        cmd = line.strip().upper()
        if cmd in ("START", "QUIT"):
            return cmd


_GREETING_INSTRUCTIONS = (
    "Greet with one short, professional sentence. "
    "Examples: 'At your service, sir.', 'Online and ready, sir.', 'What can I help you with, sir.', 'Hello, sir.'. "
    "Never use his name. Do NOT call any tools. "
    "Do NOT mention the day or time unless it's relevant."
)


async def _fire_greeting(session) -> None:
    """Generate the activation greeting on the already-running session."""
    from datetime import datetime
    now = datetime.now().strftime("%A, %I:%M %p")
    try:
        await session.generate_reply(
            instructions=f"It is currently {now}. {_GREETING_INSTRUCTIONS}",
            tool_choice="none",
        )
        logger.info("Greeting completed")
    except Exception as e:
        logger.warning("Greeting failed: %s", e)


async def entrypoint(ctx: JobContext) -> None:
    """Boot once, pre-start the session, then loop activations.

    Key timing choice: the LiveKit session is started BEFORE we announce
    FRIDAY_READY to the launcher. That front-loads the VAD load +
    room connection cost (~2s) into boot, so the first "hey jarvis"
    after launch is as fast as a re-activation. We keep the mic
    disabled on the session until the user actually wakes the agent,
    so no transcripts reach the LLM during the idle wait.

    Console mode's virtual room doesn't recover after session.aclose(),
    so we keep ONE session alive for the entire process lifetime.
    On dismissal we just signal the launcher (SESSION_DONE) without
    tearing down the session. On re-activation we re-enable audio
    and generate a fresh greeting on the same live session.
    """
    logger.info("FRIDAY online — room: %s | STT=%s | LLM=%s | TTS=%s",
                ctx.room.name, STT_PROVIDER, LLM_PROVIDER, TTS_PROVIDER)

    # Warm-up: build providers + speaker gate in parallel. Each factory
    # is a plain synchronous constructor call with no shared state, so
    # running them through the default thread pool is safe and shaves a
    # second or two off boot time.
    loop = asyncio.get_event_loop()
    stt_inst, llm_inst, tts_inst, _ = await asyncio.gather(
        loop.run_in_executor(None, build_stt),
        loop.run_in_executor(None, build_llm),
        loop.run_in_executor(None, build_tts),
        loop.run_in_executor(None, get_speaker_gate),
    )
    logger.info("Providers + speaker gate warm — preparing session")

    # Spawn the local MCP server as a stdio subprocess and wrap it in a
    # toolset. This is the single source of truth for tools (see server.py
    # + friday/tools/). Stdio keeps everything in-process-tree — no port,
    # no URL, no network hop. The session closes the toolset on aclose(),
    # which closes the underlying MCP subprocess.
    mcp_toolset = MCPToolset(
        id="friday-local",
        mcp_server=MCPServerStdio(
            command=sys.executable,
            args=[str(_REPO_ROOT / "server.py")],
            cwd=str(_REPO_ROOT),
            client_session_timeout_seconds=15,
        ),
    )
    logger.info("MCP stdio toolset prepared (%s)", _REPO_ROOT / "server.py")

    session = AgentSession(
        turn_handling=TurnHandlingOptions(
            turn_detection="vad",
            endpointing=EndpointingOptions(
                min_delay=_endpointing_delay(),
                max_delay=0.8,
            ),
            interruption=InterruptionOptions(
                enabled=True,
                mode="adaptive",
                min_duration=0.5,
                min_words=1,
                resume_false_interruption=True,
                false_interruption_timeout=3.0,
            ),
        ),
        tools=[mcp_toolset],
        max_tool_steps=3,
    )

    # -----------------------------------------------------------------------
    # Phase 0.5: Task Orchestration Setup
    # -----------------------------------------------------------------------
    from friday.tasking import register_toolset, start_worker, set_completion_callback
    register_toolset(mcp_toolset)
    start_worker()
    
    async def _on_task_finished(task):
        try:
            logger.info(f"Task {task.task_id} completed. Narrating summary.")
            await session.generate_reply(
                instructions=f"The background task finished. Speak the following summary exactly in a natural tone, do not list steps or add extra flair: '{task.final_summary}'",
                tool_choice="none",
            )
        except Exception as e:
            logger.error(f"Task completion callback failed: {e}")
            
    set_completion_callback(_on_task_finished)

    # Dismissal event — set when the user says goodbye, cleared on re-activation.
    # Start in "dismissed" state so the activation loop's first iteration
    # waits for a START command instead of immediately looping.
    dismissed = asyncio.Event()
    dismissed.set()

    _signing_off = False   # guard against interim+final double-fire

    @session.on("user_input_transcribed")
    def _on_user_transcript(ev):
        nonlocal _signing_off
        text = (ev.transcript or "").lower().strip()
        if dismissed.is_set() or _signing_off:
            return
        if any(phrase in text for phrase in DISMISSAL_PHRASES):
            _signing_off = True
            logger.info("Dismissal detected: %r", text)

            async def _sign_off():
                nonlocal _signing_off
                # The LLM already knows to say a casual sign-off for dismissal
                # phrases (via the system prompt). Don't generate a second one —
                # just wait for the natural response to play out, then end session.
                await asyncio.sleep(6.0)
                logger.info("Sign-off complete")
                _signing_off = False
                dismissed.set()

            asyncio.create_task(_sign_off())

    # Pre-start the session so VAD + room connection is warm before the
    # first "hey jarvis". Silence the mic immediately — we don't want
    # transcripts landing in the LLM before the user actually wakes it.
    await session.start(
        agent=FridayAgent(stt=stt_inst, llm=llm_inst, tts=tts_inst),
        room=ctx.room,
    )
    try:
        session.input.set_audio_enabled(False)
    except Exception as e:
        logger.warning("Failed to pre-disable audio input: %s", e)
    logger.info("Session pre-warmed, audio gated off — awaiting first START")
    print("FRIDAY_READY", flush=True)

    # ---- Activation loop (first START + every subsequent one use the same path) ----
    while True:
        logger.info("Waiting for START command on stdin…")
        cmd = await _wait_for_stdin_command()
        if cmd != "START":
            logger.info("Received %r — shutting down", cmd or "EOF")
            break

        # Re-activate: clear dismissal, generate a fresh greeting
        _signing_off = False
        dismissed.clear()
        print("SESSION_STARTED", flush=True)

        try:
            from datetime import datetime
            now = datetime.now().strftime("%A, %I:%M %p")
            await session.generate_reply(
                instructions=(
                    f"It is currently {now}. "
                    "Greet with one short, professional sentence. "
                    "Examples: 'At your service, sir.', 'Online and ready, sir.', 'What can I help you with, sir.', 'Hello, sir.'. "
                    "Never use his name. Do NOT call any tools. "
                    "Do NOT mention the day or time unless it's relevant."
                ),
                tool_choice="none",
            )
            logger.info("Re-activation greeting completed")
        except Exception as e:
            logger.warning("Re-activation greeting failed: %s", e)

        # Enable mic AFTER greeting to avoid the race condition
        try:
            session.input.set_audio_enabled(True)
            logger.info("Audio input enabled — listening for user speech")
        except Exception as e:
            logger.warning("Failed to enable audio input: %s", e)

        # Stay active until user dismisses ("that'll be all", etc.)
        await dismissed.wait()
        logger.info("Session dismissed — gating mic")
        try:
            session.input.set_audio_enabled(False)
        except Exception:
            pass
        print("SESSION_DONE", flush=True)

    # Clean up
    try:
        await session.aclose()
    except Exception:
        pass
    ctx.shutdown("stdin closed")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

def dev():
    if len(sys.argv) == 1:
        sys.argv.append("dev")
    main()

if __name__ == "__main__":
    main()
