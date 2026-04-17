# FRIDAY Capability Plan

Goal: turn FRIDAY from a voice-only Q&A demo into a practical Jarvis-style desktop assistant that stays fast in conversation, delegates long work cleanly, and grows through a reusable tool surface.

This document is intentionally biased toward low latency and believable UX. A slow assistant with many features still feels worse than a fast assistant with fewer skills.

---

## Product rules

1. Voice is the trigger, tools do the work.
2. Fast requests should feel instant and conversational.
3. Slow work should become a task, not a long awkward pause.
4. Read-only ships before destructive actions.
5. Every capability should have a clear safety boundary and audit trail.
6. MCP is the long-term tool backbone, but the live path must stay usable during migration.

---

## Master implementation checklist

This is the single top-level to-do list for the project. The sections below expand each item in detail.

1. ~~Finish Phase 0 MCP migration.~~ **Done (2026-04-15).**
- ~~Connect `agent_friday.py` to the local MCP server.~~ Via `MCPServerStdio` + `MCPToolset` on `AgentSession(tools=[...])`.
- ~~Move the seed tools to `friday/tools/` as the single source of truth.~~ Ten tools live in `friday/tools/{web,system,apps,utils}.py`. No `@agents.function_tool` on `FridayAgent` anymore.
- ~~Keep current voice behavior and latency intact during the migration.~~ Stdio keeps MCP in-process-tree; no network hop.

2. Build Phase 0.5 planner mode and task orchestration.
- Add task models, temporary task storage, router, planner, executor, and service layers.
- Keep normal chat on the fast path.
- Enable Gemini thinking only for complex tasks.
- Execute long work step by step instead of blocking one reply.

3. Ship Phase 1 app launcher.
- Add app whitelist config.
- Add `launch_app` and `close_app`.
- Demo opening and closing your main desktop apps by voice.

4. Ship Phase 2 file read tools.
- Add bounded file listing, reading, and search.
- Enforce `FRIDAY_FILE_ROOTS`.
- Keep responses short and spoken naturally.

5. Ship Phase 3 home bridge.
- Start with Home Assistant, not direct Google Home APIs.
- Add room and device lookup, announcements, and basic media or volume control.
- Keep Google Home and Nest as controllable endpoints, not microphones.

6. Ship Phase 4 Spotify.
- Add playback, search, pause, next, and previous.
- Keep it fast enough to feel like a direct voice control feature.

7. Ship Phase 5 Calendar and Gmail.
- Add read-focused tools first.
- Use quick acknowledgments before slower network calls.
- Require confirmation before any destructive or sending action later.

8. Ship Phase 6 Claude delegation.
- Two flavors, share the same task plumbing from Phase 0.5:
  - 6a: visible terminal — open a Windows Terminal tab running `claude`, hand control back immediately (interactive work, pairing, long coding sessions).
  - 6b: headless sub-agent — `ask_claude(prompt)` shells out `claude -p "<prompt>"`, runs as a background task, speaks the answer when done (delegated reasoning, "Friday, have Claude figure out X").
- Return control to the user immediately after starting work.
- Track the task instead of blocking the voice turn.

9. Ship Phase 7 file write, move, and delete.
- Reuse the confirmation system.
- Keep all operations inside approved roots.
- Log every action and result.

10. Ship Phase 8 WhatsApp Web.
- Use a browser automation path, not desktop pixel automation.
- Keep the first version read-only.
- Treat it as a later, more brittle integration.

11. Ship Phase 9 shell with confirmation.
- Add strict command allowlists.
- Run commands visibly.
- Treat shell as task-mode work, not fast-path chat.

12. Ship Phase 10 remote bridge.
- Expose FRIDAY through Telegram, Discord, or LAN.
- Reuse the same tool and task surface.
- Keep permissions and confirmation behavior consistent.

13. Ship Phase 11 memory.
- Add lightweight memory only after responsiveness is stable.
- Store compact facts and preferences, not giant transcripts.
- Keep memory out of the hot path unless it clearly improves the turn.

14. Improve hardware only after the software path feels solid.
- Use better mics for real-world reliability.
- Do not treat Google Home devices as the hearing layer.

15. Add observability and polish.
- Keep audit logs useful.
- Add task status visibility.
- Preserve the "Jarvis" feel: quick acknowledgments, short spoken updates, minimal dead air.

---

## Latency-first behavior

FRIDAY should not wait for one giant final answer unless the user clearly asked for a task to complete end-to-end.

### Default interaction model

- If the answer is already known or can be fetched quickly, answer immediately.
- If a tool call will likely take more than about 1 second, acknowledge first, then do the work.
- If a workflow will likely take more than about 3 to 5 seconds, turn it into a task with progress updates.
- If a workflow launches an external system or another agent, return control to the user immediately and keep the task running.

### Response classes

| Class | Target feel | Examples | Voice behavior |
|---|---|---|---|
| Instant | under 300 ms | greeting, sleep, simple state changes | answer directly |
| Fast | under 1.5 s | time, app launch, volume change, list files | answer after tool call |
| Slow | 1.5 to 5 s | web search, Gmail lookup, Calendar freebusy, room device lookup | quick acknowledgment, then result |
| Task | over 5 s or multi-step | research, shell installs, Claude delegation, long summaries, batch file ops | acknowledge immediately, run in background, narrate progress only when useful |

### Voice rules

- Stream speech as soon as the first useful chunk is available.
- Do not hold TTS waiting for every tool result if a partial spoken response is enough.
- Use short acknowledgments for slow work: "Checking that now." / "Starting it." / "Working on it in the background."
- For background tasks, avoid chatty progress spam. Speak only on milestone changes or completion.

### Adaptive thinking for hard tasks

This is feasible and is the right shape for complex work, as long as it does not become the default path for normal conversation.

- Keep normal voice turns on the fast path with thinking disabled or minimized.
- Enable a stronger planning mode only for long, multi-step, or failure-prone tasks.
- The planner should produce a short explicit step list, then execute one step at a time.
- FRIDAY should store task state outside the model in a temporary record that it can read and update between steps.
- The temporary record should be discarded when the task is done, while the audit log keeps only the high-level result.

### Temporary task record

Do not use a messy freeform scratchpad as the source of truth. Use a small structured record instead.

Suggested fields:
- `task_id`
- `goal`
- `steps`
- `current_step`
- `status`
- `last_tool_result`
- `created_at`
- `updated_at`

Why this works:
- FRIDAY can resume after interruptions.
- The model does not have to re-plan from scratch every step.
- It lowers drift compared to a plain text note.
- It keeps long tasks organized without slowing normal chat.

### What not to do

- Do not make every request go through planner mode.
- Do not expose raw chain-of-thought to the user or treat it as durable state.
- Do not let a temporary task log grow into a second conversation history.
- Do not block the main voice turn waiting for the full plan to complete.

### Planner mode design spec

This is the concrete shape the feature should take.

### Switching rules

FRIDAY should stay on the fast path unless one of these is true:

- the request clearly requires more than one tool step
- the request launches an external process or agent
- the request is expected to take more than about 5 seconds
- the request is destructive and needs planning plus confirmation
- the first tool result changes what the next step should be
- the user explicitly asks FRIDAY to "handle it", "work on it", "research it", or "do this in the background"

FRIDAY should stay off planner mode when:

- the request is a simple factual answer
- the request is one fast tool call
- the user is casually chatting
- the benefit of planning is lower than the latency cost

### Model routing

Use two logical modes, even if they later share part of the implementation:

- `fast` mode for chat, quick tools, and immediate spoken results
- `planner` mode for long or branching tasks

Recommended behavior:

- `fast` mode keeps Gemini thinking disabled or minimized
- `planner` mode enables Gemini thinking only while creating or revising the step plan
- execution steps should go back to the cheaper and faster path whenever the next step is obvious

This avoids paying planning latency on every turn.

### Task record schema

The task record should be external state, not model memory.

Example shape:

```json
{
  "task_id": "task_20260414_001",
  "goal": "Research two external mics and tell me which is better for desk use",
  "status": "running",
  "mode": "planner",
  "source": "voice",
  "created_at": "2026-04-14T15:30:00-04:00",
  "updated_at": "2026-04-14T15:30:08-04:00",
  "current_step": 1,
  "steps": [
    {
      "id": 1,
      "title": "Find two candidate products",
      "status": "completed",
      "tool": "search_web",
      "result_summary": "Found Rode Wireless Go II and DJI Mic 2"
    },
    {
      "id": 2,
      "title": "Compare desk-use tradeoffs",
      "status": "running",
      "tool": null,
      "result_summary": null
    },
    {
      "id": 3,
      "title": "Report recommendation",
      "status": "pending",
      "tool": null,
      "result_summary": null
    }
  ],
  "last_tool_result": "Search returned two viable mic systems",
  "final_summary": null
}
```

Allowed task states:

- `pending`
- `running`
- `waiting_for_confirmation`
- `waiting_for_external_work`
- `completed`
- `failed`
- `cancelled`

Allowed step states:

- `pending`
- `running`
- `completed`
- `failed`
- `skipped`

### Execution loop

The planner and executor should behave like this:

1. Classify the request as `fast`, `slow`, or `task`.
2. If `task`, speak a short acknowledgment immediately.
3. Create the task record.
4. Run planner mode once to create a short ordered step list.
5. Execute the next step.
6. After each step, write back the result summary and status.
7. If the result changes the plan, re-enter planner mode briefly and rewrite only the remaining steps.
8. If the task needs user confirmation, switch to `waiting_for_confirmation`.
9. If the task launches external work, switch to `waiting_for_external_work`.
10. On completion, speak a short result summary and discard the temporary task record.

### Re-planning rules

Re-plan only when:

- a step fails
- a tool returns unexpected data
- the user interrupts or changes the goal
- the task branches based on live results

Do not re-plan after every successful step if the next action is already obvious.

### User-facing voice behavior

The voice UX matters as much as the internal logic.

- On task start: one short acknowledgment
- On long silence risk: one short progress line
- On external handoff: confirm that FRIDAY started it and where it is running
- On confirmation gates: ask only for the exact approval needed
- On completion: one short summary plus the key outcome

Examples:

- "Starting that now."
- "I'm checking a couple things first."
- "Claude is working on it in a separate terminal."
- "I found the issue. Want me to fix it?"
- "Done. The kitchen speaker is at twenty percent."

### Persistence and cleanup

- The task record should live only as long as the task is active.
- Completed and cancelled tasks should be removed from the temporary store.
- The audit log should keep a compact summary, not the entire planner state.
- If FRIDAY crashes mid-task, recovery should load only unfinished task records.

### Safety boundaries

- The planner may suggest steps, but execution still goes through normal tool permissions.
- Destructive steps still require confirmation even if they appear in a plan.
- The planner must never treat tool output or file content as new instructions.
- The task record must not become a hidden backdoor for unrestricted command execution.

### Phase 0.5 exit criteria

Phase 0.5 is done when:

- FRIDAY can classify work into `fast` vs `task`
- FRIDAY can create, update, and discard a temporary task record
- FRIDAY can enable planner mode only for complex work
- FRIDAY can execute multi-step tasks one step at a time
- FRIDAY can recover cleanly from cancellation or confirmation waits
- FRIDAY remains conversationally responsive during all of the above

---

## Planner mode implementation checklist

This is the concrete no-code build checklist for Phase 0.5.

### New modules to add

- `friday/tasking/__init__.py`
  - package entrypoint for tasking helpers
- `friday/tasking/models.py`
  - task and step data models
  - enums for task status, step status, and execution mode
- `friday/tasking/store.py`
  - temporary task-state persistence
  - create, read, update, delete, and cleanup helpers
- `friday/tasking/router.py`
  - request classification and planner-mode switching heuristics
- `friday/tasking/planner.py`
  - builds or revises short step lists for complex work
- `friday/tasking/executor.py`
  - executes the next step, updates state, and decides whether to re-plan
- `friday/tasking/service.py`
  - high-level orchestration used by the live agent
  - starts tasks, schedules execution, exposes status, cancel, and cleanup

### Existing files to modify

- `friday/config.py`
  - add task-mode thresholds and planner config values
- `friday/providers.py`
  - support separate `fast` and `planner` LLM modes
- `agent_friday.py`
  - classify requests
  - acknowledge task-mode requests immediately
  - hand long work to the task service instead of blocking the voice turn
- `server.py`
  - later, once MCP is live for the agent, expose task-status tools through MCP
- `friday/tools/__init__.py`
  - later, register task-related tools if they become part of the MCP surface

### Recommended runtime storage

Use a temporary directory that is not source-controlled.

Recommended path:
- `runtime/tasks/active/<task_id>.json`

Optional later:
- `runtime/tasks/recovery/`

Do not store planner state in:
- the main conversation history
- random markdown files
- `logs/friday-actions.log`

The audit log should keep only compact summaries.

### Data models

`TaskRecord`
- `task_id: str`
- `goal: str`
- `status: Literal["pending", "running", "waiting_for_confirmation", "waiting_for_external_work", "completed", "failed", "cancelled"]`
- `mode: Literal["fast", "planner"]`
- `source: Literal["voice", "telegram", "discord", "other"]`
- `created_at: str`
- `updated_at: str`
- `current_step: int | None`
- `steps: list[TaskStep]`
- `last_tool_result: str | None`
- `final_summary: str | None`

`TaskStep`
- `id: int`
- `title: str`
- `status: Literal["pending", "running", "completed", "failed", "skipped"]`
- `tool: str | None`
- `args_preview: str | None`
- `result_summary: str | None`

### Suggested interfaces

`friday/tasking/router.py`
- `classify_request(text: str) -> Literal["fast", "slow", "task"]`
- `should_enable_planner(text: str, request_class: str) -> bool`

`friday/tasking/store.py`
- `create_task(task: TaskRecord) -> None`
- `load_task(task_id: str) -> TaskRecord | None`
- `save_task(task: TaskRecord) -> None`
- `delete_task(task_id: str) -> None`
- `list_active_tasks() -> list[TaskRecord]`
- `cleanup_finished_tasks() -> None`

`friday/tasking/planner.py`
- `plan_steps(goal: str, context: str | None = None) -> list[TaskStep]`
- `replan_remaining_steps(task: TaskRecord) -> list[TaskStep]`

`friday/tasking/executor.py`
- `execute_next_step(task: TaskRecord) -> TaskRecord`
- `run_task(task_id: str) -> None`
- `cancel_task(task_id: str) -> None`

`friday/tasking/service.py`
- `start_task(goal: str, source: str = "voice") -> str`
- `get_task_status(task_id: str) -> TaskRecord | None`
- `summarize_task(task_id: str) -> str`

### Config knobs to add

In `friday/config.py`:

- `TASK_MODE_ENABLED`
- `TASK_SLOW_THRESHOLD_SECONDS`
- `TASK_LONG_THRESHOLD_SECONDS`
- `FAST_THINKING_BUDGET`
- `PLANNER_THINKING_BUDGET`
- `MAX_PLAN_STEPS`
- `TASK_STATE_DIR`

Recommended defaults:
- keep `FAST_THINKING_BUDGET = 0`
- keep `MAX_PLAN_STEPS` small, around 3 to 6
- start with conservative task switching rather than aggressive auto-planning

### Provider changes

In `friday/providers.py`, move from one LLM builder to a mode-aware builder.

Recommended direction:
- `build_llm(mode: Literal["fast", "planner"] = "fast")`

Expected behavior:
- `fast` mode uses Gemini with thinking disabled or minimized
- `planner` mode uses Gemini with a nonzero or dynamic thinking budget
- both modes should keep the same basic tool behavior and safety rules

### Agent integration points

In `agent_friday.py`:

- classify the incoming request before starting heavy work
- if request is `fast`, keep the current behavior
- if request is `task`, speak a short acknowledgment immediately
- create the task record
- hand execution to the task service
- speak again only when the task finishes, needs confirmation, or fails

Important:
- do not move wake-word, speaker-gate, or session-lifecycle logic into the tasking layer
- do not block `llm_node` waiting for task completion
- do not add a second giant history buffer just for planner mode

### MCP integration, later

After Phase 0 lands, tasking can also expose small control tools:

- `get_task_status(task_id: str)`
- `cancel_task(task_id: str)`
- `list_active_tasks()`

These are useful for desktop or phone bridges, but they should not block the first local voice implementation.

### Voice UX checklist

- immediate acknowledgment for task starts
- short follow-up only on milestone changes
- concise confirmation prompts
- concise completion summaries
- no narration of raw planner internals

### Overlay checklist

Do not add new overlay states first.

Start by reusing:
- `THINKING` while planning
- `SPEAKING` for acknowledgments and completion

Only add new visual states later if the current overlay cannot communicate task progress clearly enough.

### Rollout order

1. Add task models and JSON store.
2. Add a simple classifier with heuristic rules only.
3. Add `build_llm(mode=...)`.
4. Add planner mode for one narrow workflow.
5. Add executor loop and cleanup.
6. Add confirmation-wait handling.
7. Add recovery for unfinished tasks.
8. Add task-status tools after MCP migration.

### Narrow first workflow

Do not make the first planner-mode workflow something huge.

Best first candidates:
- web research with a short final summary
- Claude delegation with status tracking
- a home-control mini-sequence like "find the kitchen speaker and set it to 20%"

Avoid as the first planner workflow:
- shell installs
- WhatsApp automation
- broad file cleanup

### Done means

This checklist is complete when a user can say something like:

- "Research this and tell me the answer when you're done."
- "Start Claude on that and let me know when it finishes."
- "Check the speaker in the bedroom and lower it if it's over fifty percent."

and FRIDAY stays conversationally responsive instead of hanging on one long reply.

---

## What is realistic

### Clearly viable in this repo

- App launching and closing through a whitelist.
- File listing, reading, search, and bounded write/move/delete inside approved roots.
- Spotify, Gmail, Calendar, GitHub, Notion, and Obsidian style skills.
- Home control through Home Assistant or other local bridges.
- Claude Code delegation through a visible terminal.
- Phone or chat bridges that talk to the same tool surface.

### Viable, but only with a bridge

- Google Home / Nest control.
- Smart-home aggregation across mixed vendors.
- WhatsApp reading via browser automation.
- Cross-device control from phone, watch, or another laptop.

### Not a good fit for the current repo

- Using scattered Google Home / Nest speakers as FRIDAY's raw microphones.
- Intercepting Google Assistant wake-word behavior on Nest devices.
- Letting the LLM run arbitrary shell or arbitrary file-system actions without strict allowlists and confirmation.
- Blocking the main conversation turn on long research, installs, or external agent work.

---

## Google Home / Nest: possible vs not possible

### Possible

- Query what speakers or rooms are online.
- Send announcements to one room or the whole house.
- Start or stop media on supported speakers.
- Adjust volume and basic playback state.
- Control other smart-home devices if they are exposed through a bridge.

### Not realistically available here

- Raw mic capture from Nest speakers.
- Turning Google Home devices into distributed wake-word endpoints for FRIDAY.
- A pure Python desktop-only integration that directly uses Google's official Home APIs.

### Recommended path

1. Stand up Home Assistant on the LAN.
2. Let Home Assistant discover Google Cast / Nest devices.
3. Add `friday/tools/home_assistant.py` with a very small first slice:
   - `list_home_rooms()`
   - `list_home_devices(room: str | None = None)`
   - `announce(message: str, room: str | None = None)`
   - `set_volume(device: str, level: float)`
   - `stop_media(device: str)`
4. Only build a direct Google Home mobile bridge later if Home Assistant proves too limiting.

### Why this path wins

- It is local and usually lower latency than round-tripping through more cloud layers.
- It fits this Python codebase cleanly.
- It scales to non-Google devices without redoing FRIDAY's architecture.
- It keeps FRIDAY responsive because room control is a short tool call, not a giant agent workflow.

---

## Architecture target

### Current reality (post Phase 0)

- `agent_friday.py` connects to the local MCP server via `MCPServerStdio` + `MCPToolset`.
- Every skill lives in `friday/tools/` and is registered through `server.py`.
- The agent has no `@agents.function_tool` methods — it's all MCP.

### Still to build

- Phase 0.5 task layer so long-running work doesn't block the voice turn.
- External bridges (phone, Telegram, LAN) can attach to the same tool surface via `server.py --sse` or `--streamable-http`.

---

## Recommended build order

This order is optimized for responsiveness, not maximum feature count.

### Phase 0 - MCP migration

Move the live agent toward `server.py` so new capabilities do not require hand-editing `FridayAgent`.

Exit criteria:
- The agent can consume tools from the local MCP server.
- Existing seed tools still work.
- New tools have one home: `friday/tools/`.

### Phase 0.5 - Task model for slow work

Add a minimal task layer before expanding slow integrations.

Needed behavior:
- `start_task(...)` style abstraction for long-running jobs.
- Immediate spoken acknowledgment.
- Optional progress callbacks.
- Later completion summary.
- Temporary structured task state that FRIDAY can read and update between steps.
- Planner mode that can enable Gemini thinking only for complex tasks.
- Step-by-step execution instead of one long blocking response.

This is what keeps Jarvis natural instead of silent while waiting for one big answer.

Recommended shape:
- `fast` path for normal chat and quick tools
- `task` path for long workflows
- planner creates a short step list
- executor runs one step at a time
- task record is discarded on completion

This should be built as explicit orchestration, not as "let the model keep a hidden diary." The model can help plan, but the task state must live outside the model.

### Phase 1 - App launcher

Low-latency, high-demo-value, easy to trust.

### Phase 2 - File read tools

Still fast, still bounded, very useful in day-to-day use.

### Phase 3 - Home bridge

Do Home Assistant before chasing deeper Google-specific work.

Why early:
- It is a clean demo.
- It is mostly local.
- It fits the "fast action" interaction pattern.

### Phase 4 - Spotify

Natural voice demo, low-risk, good wow factor.

### Phase 5 - Calendar and Gmail

Useful, but network-bound and slightly slower. These should use quick acknowledgments before tool completion.

### Phase 6 - Claude delegation

Excellent for task-mode workflows. Do not block the voice turn waiting for Claude to finish.

Two variants, built on the same Phase 0.5 task layer:

- **6a — visible terminal.** `open_claude_cli()` opens a Windows Terminal tab and starts `claude`. Friday acks and returns control. Best for pairing, interactive coding, "I want to see what Claude is doing."
- **6b — headless sub-agent.** `ask_claude(prompt)` shells `claude -p "<prompt>"` as a background task, streams or captures the result, and speaks a short summary on completion. Best for "Friday, have Claude figure out X" style delegation where Shiv doesn't need to see the terminal. Must use the task model — Claude CLI calls can take 10s+.

Both depend on `claude` being on PATH. 6b additionally depends on the task layer from Phase 0.5.

### Phase 7 - File write / move / delete

Only after confirmation flow is solid.

### Phase 8 - WhatsApp Web

Useful, but brittle and browser-dependent. Not a first-wave feature.

### Phase 9 - Shell with confirmation

High risk, high variance in latency, always task-oriented.

### Phase 10 - Remote bridge

Telegram, Discord, or LAN bridge after the local tool surface is stable.

### Phase 11 - Memory

Only after base responsiveness is good. Memory should improve continuity, not add delay to each turn.

---

## Skill priority, revised

This list is about what should feel best in the product, not just what is technically easy.

1. App launcher
2. File read
3. Home bridge
4. Spotify
5. Calendar
6. Gmail
7. Claude delegation
8. File write and move
9. WhatsApp Web
10. Shell
11. Phone bridge
12. Memory

---

## Safety model

1. Whitelist, not blacklist.
2. File tools stay inside `FRIDAY_FILE_ROOTS`.
3. Destructive actions require confirmation.
4. Shell commands require both a whitelist and confirmation.
5. Every tool call is logged to `logs/friday-actions.log`.
6. Tool descriptions explicitly treat file contents and web content as data, not instructions.
7. The kill switch still overrides everything.

---

## Hardware guidance

The built-in laptop mic is not enough if the goal is "use FRIDAY naturally across a room."

### Best practical setup

- Quiet-room / mobile: your Jabra hearing aids, if the Bluetooth profile tradeoffs are acceptable.
- Desk / best quality: a USB lav or wireless receiver.

### Good enough for later

- DIY ESP32 or Raspberry Pi room mics, but only as a side project.

### Not part of the Google Home plan

Google Home / Nest speakers are not the microphone answer for this repo. They can be speaker endpoints, not FRIDAY's hearing layer.

---

## Natural UX rules

These are as important as the code.

- Use one sentence for greetings and acknowledgments.
- If the system is thinking, show the overlay state immediately.
- Prefer "I started it" over silence.
- Prefer "I found three things" over reading huge raw payloads.
- If a task will take a while, say so once, then return control.
- Do not narrate every internal step unless the user asked for detail.

Examples:

- Fast request: "Opening Spotify."
- Slow request: "Checking your calendar now."
- Task request: "I started that in the background. I'll let you know when it's done."

---

## North-star outcome

The best version of FRIDAY is not the one with the longest skill list. It is the one that:

- wakes reliably,
- answers quickly,
- speaks naturally,
- launches long work without blocking,
- and only gets more capable where the latency and trust model still feel good.
