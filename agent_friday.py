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
import re
import random
import sys
import webbrowser

import numpy as np
from livekit import rtc, agents
from livekit.agents import (
    JobContext, WorkerOptions, cli,
    llm as lk_llm, stt, TurnHandlingOptions,
)
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
from friday.tools.web import SEED_FEEDS, fetch_and_parse_feed


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
    """F.R.I.D.A.Y. voice agent. Tools registered directly — no MCP needed."""

    def __init__(self, stt, llm, tts, vad=None) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT,
            stt=stt, llm=llm, tts=tts,
            vad=vad or silero.VAD.load(
                activation_threshold=0.92,
                min_speech_duration=0.5,
                min_silence_duration=0.8,
            ),
        )

    # -- Direct tools (no MCP, no SSE, no timeouts) -------------------------

    @agents.function_tool
    async def get_current_time(self, timezone: str = "") -> str:
        """Get the current date and time. If no timezone is given, automatically
        detects the user's location via IP geolocation. You can also pass a
        specific IANA timezone like 'America/New_York', 'Europe/London', etc.
        For US states: Georgia/Florida/New York = America/New_York,
        Texas/Illinois = America/Chicago, California = America/Los_Angeles.
        Use this whenever the user asks what time it is."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import httpx

        location_info = ""

        if not timezone:
            # Auto-detect from IP geolocation
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get("http://ip-api.com/json/?fields=city,regionName,country,timezone")
                    data = resp.json()
                    timezone = data.get("timezone", "UTC")
                    city = data.get("city", "")
                    region = data.get("regionName", "")
                    country = data.get("country", "")
                    location_info = f" (detected location: {city}, {region}, {country})"
            except Exception:
                timezone = "UTC"
                location_info = " (location detection failed, using UTC)"

        try:
            tz = ZoneInfo(timezone)
            now = datetime.now(tz)
            return now.strftime("%A, %B %d, %Y at %I:%M %p %Z") + location_info
        except Exception as e:
            now = datetime.now()
            return f"(Could not resolve timezone '{timezone}': {e}) Local time is {now.strftime('%I:%M %p')}."

    @agents.function_tool
    async def search_web(self, query: str) -> str:
        """Search the web for current information on any topic.
        Use this when the user asks about a specific event, person, conflict,
        or anything that needs up-to-date information beyond general news headlines."""
        from ddgs import DDGS

        def _search():
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))
                if not results:
                    return "No results found for that query."
                lines = []
                for r in results:
                    title = r.get("title", "")
                    body = r.get("body", "")
                    if body:
                        lines.append(f"{title}: {body[:150]}")
                    else:
                        lines.append(title)
                return " | ".join(lines)
            except Exception as e:
                return f"Search failed: {str(e)}"

        return await asyncio.get_event_loop().run_in_executor(None, _search)

    @agents.function_tool
    async def get_world_news(self) -> str:
        """Fetches the latest global headlines from major news outlets simultaneously.
        Use this when the user asks 'What's going on in the world?' or for recent events."""
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            tasks = [fetch_and_parse_feed(client, url) for url in SEED_FEEDS]
            results_of_lists = await asyncio.gather(*tasks)
            all_articles = [item for sublist in results_of_lists for item in sublist]

        if not all_articles:
            return "The global news grid is unresponsive. Unable to pull headlines."

        lines = []
        for entry in all_articles[:5]:
            lines.append(f"{entry['title']}.")
        return "Here are today's top stories. " + " ".join(lines)

    @agents.function_tool
    async def open_world_monitor(self) -> str:
        """Opens the World Monitor dashboard (worldmonitor.app) in the system's web browser.
        Use this when the user wants a visual overview of global events or a real-time map."""
        try:
            webbrowser.open("https://worldmonitor.app/")
            return "Opening the World Monitor for you now."
        except Exception as e:
            return f"Unable to open the monitor: {str(e)}"

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
        logger.info("on_enter — generating greeting")
        try:
            await self.session.generate_reply(
                instructions=(
                    "Say a quick, casual greeting — one short sentence, "
                    "like 'Hey, what's up?' or 'Hey Shiv, what do you need?'. "
                    "Keep it natural. Do NOT call any tools."
                ),
                tool_choice="none",
            )
            logger.info("on_enter greeting completed")
        except Exception as e:
            logger.exception("on_enter failed: %s", e)


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


async def entrypoint(ctx: JobContext) -> None:
    """Boot once, create a single persistent session, loop activations.

    Console mode's virtual room doesn't recover after session.aclose(),
    so we keep ONE session alive for the entire process lifetime.
    On dismissal we just signal the launcher (SESSION_DONE) without
    tearing down the session. On re-activation we generate a fresh
    greeting on the same live session.
    """
    logger.info("FRIDAY online — room: %s | STT=%s | LLM=%s | TTS=%s",
                ctx.room.name, STT_PROVIDER, LLM_PROVIDER, TTS_PROVIDER)

    # Warm-up: verify config, trigger heavy imports, pre-load models
    build_stt(); build_llm(); build_tts()
    get_speaker_gate()
    logger.info("All providers validated — entering session loop")
    print("FRIDAY_READY", flush=True)

    # ---- Wait for first START ----
    logger.info("Waiting for START command on stdin…")
    cmd = await _wait_for_stdin_command()
    if cmd != "START":
        logger.info("Received %r — shutting down", cmd or "EOF")
        ctx.shutdown("stdin closed")
        return

    # ---- Create ONE persistent session ----
    stt_inst = build_stt()
    llm_inst = build_llm()
    tts_inst = build_tts()

    logger.info("START received — creating persistent session")

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
        max_tool_steps=3,
    )

    # Dismissal event — set when the user says goodbye, cleared on re-activation
    dismissed = asyncio.Event()

    @session.on("user_input_transcribed")
    def _on_user_transcript(ev):
        text = (ev.transcript or "").lower().strip()
        if dismissed.is_set():
            return
        if any(phrase in text for phrase in DISMISSAL_PHRASES):
            logger.info("Dismissal detected: %r", text)

            async def _sign_off():
                try:
                    session.interrupt()
                except Exception:
                    pass
                await asyncio.sleep(0.15)
                handle = await session.generate_reply(
                    instructions=f"Say exactly: '{random.choice(SLEEP_RESPONSES)}' and nothing else.",
                )
                try:
                    await handle.wait_for_playout()
                except Exception:
                    await asyncio.sleep(2.5)
                logger.info("Sign-off complete")
                dismissed.set()

            asyncio.create_task(_sign_off())

    # Start the session ONCE — it stays alive for the whole process
    await session.start(
        agent=FridayAgent(stt=stt_inst, llm=llm_inst, tts=tts_inst),
        room=ctx.room,
    )
    print("SESSION_STARTED", flush=True)
    logger.info("Session active — listening for user speech")

    # ---- Activation loop ----
    while True:
        # Wait for dismissal
        await dismissed.wait()
        print("SESSION_DONE", flush=True)
        logger.info("Dismissed — waiting for next activation")

        # Wait for next START from launcher
        cmd = await _wait_for_stdin_command()
        if cmd != "START":
            logger.info("Received %r — shutting down", cmd or "EOF")
            break

        # Re-activate: clear dismissal, generate a fresh greeting
        dismissed.clear()
        logger.info("Re-activated — generating greeting")
        print("SESSION_STARTED", flush=True)

        try:
            await session.generate_reply(
                instructions=(
                    "Say a quick, casual greeting — one short sentence, "
                    "like 'Hey, what's up?' or 'Hey Shiv, what do you need?'. "
                    "Keep it natural. Do NOT call any tools."
                ),
                tool_choice="none",
            )
            logger.info("Re-activation greeting completed")
        except Exception as e:
            logger.warning("Re-activation greeting failed: %s", e)

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
