# Tool Routing Architecture

## Problem

FRIDAY currently loads ~20 tools into a flat list passed to the LLM. As we integrate external MCP servers (Home Assistant, Playwright, WhatsApp, Slack, Sonos, etc.), the tool count will grow to 200-300+. This creates two problems:

1. **LLM accuracy degrades** — past ~50 tools, the model starts picking wrong tools, hallucinating parameters, or getting confused by similar names.
2. **Resource overhead** — each external MCP server is a separate process. Loading all of them at boot wastes RAM and slows startup.

## Solution: Domain-Based Tool Routing

A two-stage system where FRIDAY's LLM never sees more than ~30-40 tools at once.

### Architecture

```
User speaks
    │
    ▼
┌──────────────────┐
│  Stage 1: Router │   ← lightweight keyword + LLM classifier
│  (always active) │
└────────┬─────────┘
         │ returns: domain + is_fast
         ▼
┌──────────────────────────────────────────┐
│  Stage 2: Domain Tool Loader             │
│                                          │
│  ┌─────────┐ ┌──────┐ ┌──────────────┐  │
│  │ core    │ │ home │ │ comms        │  │
│  │ (always)│ │      │ │              │  │
│  │ 20 tools│ │ 15   │ │ 20 tools     │  │
│  └─────────┘ └──────┘ └──────────────┘  │
│  ┌─────────┐ ┌──────┐ ┌──────────────┐  │
│  │ browser │ │media │ │ research     │  │
│  │         │ │      │ │              │  │
│  │ 10 tools│ │ 10   │ │ 8 tools      │  │
│  └─────────┘ └──────┘ └──────────────┘  │
└──────────────────────────────────────────┘
         │
         ▼
   LLM sees: core (always) + one domain's tools
   Max ~40 tools at a time
```

### Domains

| Domain | Tools | MCP Source | Load strategy |
|--------|-------|-----------|---------------|
| `core` | apps, files, system, memory, claude_delegate, volume | `server.py` (local) | Always loaded |
| `media` | spotify, sonos, playback, media keys, current_track | `server.py` + Sonos MCP | Always loaded (small) |
| `home` | lights, locks, thermostat, cameras, rooms, devices | Home Assistant MCP | On-demand |
| `comms` | email, whatsapp, telegram, slack, discord, calls | Multiple external MCPs | On-demand |
| `browser` | navigate, click, fill, screenshot, extract | Playwright MCP | On-demand |
| `calendar` | events, scheduling, availability | Google Calendar MCP | Always loaded (small) |
| `research` | web search, news, arxiv, deep research | Brave + news MCPs | On-demand |
| `finance` | stocks, portfolio, accounting | Finance MCPs | On-demand |
| `maps` | navigation, places, rideshare | Google Maps MCP | On-demand |

### Implementation

#### 1. Domain registry (`friday/routing/domains.py`)

```python
from dataclasses import dataclass

@dataclass
class ToolDomain:
    name: str
    keywords: list[str]           # fast keyword matching
    description: str              # for LLM fallback classification
    mcp_server: str | None        # external MCP server config, None = local
    always_loaded: bool = False   # if True, tools are in every request

DOMAINS = {
    "core": ToolDomain(
        name="core",
        keywords=[],  # no keywords needed — always loaded
        description="App launching, file management, system info, memory, volume",
        mcp_server=None,
        always_loaded=True,
    ),
    "media": ToolDomain(
        name="media",
        keywords=["play", "pause", "skip", "song", "track", "spotify",
                  "music", "album", "playlist", "volume", "sonos", "speaker"],
        description="Music playback, Spotify, Sonos, media controls",
        mcp_server=None,
        always_loaded=True,
    ),
    "home": ToolDomain(
        name="home",
        keywords=["light", "lamp", "dim", "bright", "lock", "door",
                  "thermostat", "temperature", "camera", "room", "house",
                  "home", "nest", "hue"],
        description="Smart home: lights, locks, thermostats, cameras, rooms",
        mcp_server="home_assistant",  # config key for MCP connection
        always_loaded=False,
    ),
    "comms": ToolDomain(
        name="comms",
        keywords=["email", "mail", "text", "message", "whatsapp", "slack",
                  "discord", "telegram", "call", "phone", "send"],
        description="Email, messaging, phone calls, chat platforms",
        mcp_server="comms",
        always_loaded=False,
    ),
    "browser": ToolDomain(
        name="browser",
        keywords=["browse", "website", "click", "fill", "form", "book",
                  "order", "sign up", "log in", "automate"],
        description="Browser automation, web interaction, form filling",
        mcp_server="playwright",
        always_loaded=False,
    ),
    # ... etc
}
```

#### 2. Enhanced router (`friday/routing/classifier.py`)

```python
def classify_domain(text: str) -> list[str]:
    """Return matching domain names, ordered by confidence.
    Always includes 'core'. Falls back to LLM classification
    if no keyword matches."""

    text_lower = text.lower()
    matches = []

    for name, domain in DOMAINS.items():
        if domain.always_loaded:
            continue  # already included
        score = sum(1 for kw in domain.keywords if kw in text_lower)
        if score > 0:
            matches.append((name, score))

    # Sort by match count, take top 1-2 domains
    matches.sort(key=lambda x: -x[1])
    domains = ["core"] + [m[0] for m in matches[:2]]

    # If no keyword match, optionally ask the LLM (costs one fast call)
    if len(domains) == 1:
        domains = ["core"]  # just use core tools

    return domains
```

#### 3. On-demand MCP connection pool (`friday/routing/pool.py`)

```python
class MCPPool:
    """Manages on-demand MCP server connections.
    Servers are started when first needed and kept warm for a configurable
    idle timeout before being shut down."""

    def __init__(self, idle_timeout: float = 300.0):
        self._connections: dict[str, MCPToolset] = {}
        self._last_used: dict[str, float] = {}
        self._idle_timeout = idle_timeout

    async def get_tools(self, domain_name: str) -> MCPToolset | None:
        """Get or start the MCP server for this domain."""
        if domain_name in self._connections:
            self._last_used[domain_name] = time.time()
            return self._connections[domain_name]

        config = MCP_SERVER_CONFIGS.get(domain_name)
        if not config:
            return None

        toolset = MCPToolset(mcp_server=MCPServerStdio(**config))
        await toolset.initialize()
        self._connections[domain_name] = toolset
        self._last_used[domain_name] = time.time()
        return toolset

    async def cleanup_idle(self):
        """Shut down servers that haven't been used recently."""
        now = time.time()
        for name, last in list(self._last_used.items()):
            if now - last > self._idle_timeout:
                toolset = self._connections.pop(name, None)
                if toolset:
                    await toolset.aclose()
                del self._last_used[name]
```

#### 4. Modified LLM node in `agent_friday.py`

The key change is in `llm_node` — before calling the LLM, classify the domain and swap the active toolset:

```python
async def llm_node(self, chat_ctx, tools, model_settings):
    # Get the latest user message
    last_msg = chat_ctx.items[-1] if chat_ctx.items else None
    user_text = ""
    if last_msg and last_msg.role == "user":
        user_text = last_msg.text_content or ""

    # Classify which domain(s) this request needs
    domains = classify_domain(user_text)

    # Build combined tool list: core (always) + domain-specific
    active_tools = [self._core_toolset]  # always present
    for domain in domains:
        if domain != "core":
            domain_toolset = await self._mcp_pool.get_tools(domain)
            if domain_toolset:
                active_tools.append(domain_toolset)

    # Pass the scoped tools to the LLM
    async for chunk in Agent.default.llm_node(
        self, chat_ctx, active_tools, model_settings
    ):
        yield chunk
```

### Migration path

This doesn't need to be built all at once. The steps:

1. **Now**: Keep everything as-is. ~20 tools in one flat server works fine.
2. **When adding first external MCP** (e.g., Home Assistant): Create the domain registry and pool. Route `home` domain requests to the HA MCP server. Core tools stay in `server.py`.
3. **When adding 2-3 more external MCPs**: The pattern is proven. Each new MCP server just needs a domain config entry.
4. **When tool count exceeds ~50**: Add LLM fallback classification for ambiguous requests.

### Key design decisions

- **Core tools are always loaded** — no routing penalty for everyday commands
- **On-demand servers have idle timeout** — saves RAM when not in use
- **Max 2 domains per request** — caps tool count at ~40 even with many domains
- **Keyword matching first, LLM fallback second** — fast path stays fast
- **External MCP servers are stdio subprocesses** — same pattern as today's `server.py`, no network hops
- **Pool manages lifecycle** — agent doesn't care about MCP connection details
