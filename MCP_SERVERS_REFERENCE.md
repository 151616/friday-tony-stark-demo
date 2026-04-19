# MCP Servers Reference — Building a Real JARVIS

Last updated: 2026-04-19

The goal: make FRIDAY as close to MCU JARVIS as today's technology allows. This is the catalog of MCP servers worth integrating, organized by JARVIS capability.

---

## Registries to monitor

| Registry | URL |
|----------|-----|
| Official MCP Registry | registry.modelcontextprotocol.io |
| Glama.ai | glama.ai/mcp/servers |
| Smithery | smithery.ai |
| MCP.so | mcp.so |
| Awesome MCP Servers | github.com/punkpeye/awesome-mcp-servers |
| mcp-get | mcp-get.com |
| OpenTools | opentools.com |

---

## Priority tier (integrate first)

### 1. Smart Home Control

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **Home Assistant MCP** (community/custom) | Single bridge to Hue, Nest, Ring, Ecobee, locks, thermostats, cameras — hundreds of brands | "Dim the living room to 30%" / "Lock the front door" |
| **wemo-mcp-server** | WeMo smart devices — dimmer, switches, HomeKit | Direct device control |
| **Sonos MCP** (sonos-ts-mcp) | 50+ tools — multi-room playback, queue, EQ, alarms | "Play jazz in the kitchen" |
| **smartest-tv** | LG, Samsung, Android TV, Roku — Netflix/YouTube deep linking, scene presets | "Play Netflix on the living room TV" |

> **Home Assistant is the single most impactful integration.** It covers hundreds of device brands through one API. Build `friday/tools/home_assistant.py` to talk to it.

### 2. Browser Automation

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **microsoft/playwright-mcp** | Official Playwright MCP — interact with pages via accessibility snapshots | "Book that restaurant on OpenTable" |
| **browsermcp/mcp** | Control local Chrome | Web automation with existing sessions |
| **real-browser-mcp** | Chrome with existing logins/cookies — no re-auth needed | Use authenticated sites |

### 3. Communication

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **email-mcp** | IMAP/SMTP — 42 tools: read, search, send, schedule, AI triage, notifications | "Read my unread emails" |
| **ms-365-mcp-server** | Full Microsoft 365 via Graph API — Outlook, files, Excel, calendar | Office 365 power user |
| **whatsapp-mcp** | Search personal WhatsApp messages, contacts, send messages | "Text Mom on WhatsApp" |
| **telegram-mcp** | Full Telegram API — user data, dialogs, messages | Telegram messaging |
| **discord-mcp** | 60+ tools — messages, channels, roles, forums, webhooks | Discord management |
| **Slack MCP** | DMs, channels, threads, search — 11 tools | "Check Slack for messages from the dev team" |
| **Spix** | Real phone number + voice — make/receive calls, ~500ms latency, 26 tools | "Call the restaurant and make a reservation" |
| **telephony-mcp-server** | Voice calls with STT, SMS, voicemail detection via Vonage | Full telephony |
| **ntfy-me-mcp** | Push notifications to phones/devices via ntfy | "Notify me when the build finishes" |

### 4. Desktop / OS Control

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **DesktopCommanderMCP** | Swiss-army-knife — manage programs, files, search, edit | Full desktop control |
| **Terminator** | GUI automation via accessibility APIs — Windows, macOS, Linux | Control any desktop app without screenshots |
| **Touchpoint** | "Playwright for the entire OS" — find and interact with UI elements in any app | Automate anything on screen |

---

## Second tier (integrate after core is solid)

### 5. Research & Knowledge

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **Brave Search** | Web and local search | "Search the web for..." |
| **deep-research-mcp** | Multi-step deep research with web search + code interpreter | "Do a deep dive on quantum computing" |
| **google-news-mcp-server** | Google News with topic categorization, multi-language | "What's in the news?" |
| **mcp-simple-arxiv** | Search and read arXiv papers | Scientific research |
| **Wikipedia/MediaWiki** | 33+ tools for any MediaWiki wiki | Encyclopedic knowledge |

### 6. Calendar & Scheduling

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **Google Calendar MCP** | Already in your setup — create, update, delete events, suggest times | "What's on my calendar today?" |
| **temporal-cortex** | AI-native calendar middleware — conflict-free booking across Google/Outlook/CalDAV | "Find a time that works for everyone" |
| **caldav-mcp** | Universal CalDAV — Google, Apple iCloud, Nextcloud | Cross-platform calendar |

### 7. Weather

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **weather-mcp-server** | Real-time weather via WeatherAPI.com | "What's the weather like?" |
| **weekly-weather-mcp** | 7-day forecasts worldwide via open-meteo (free) | "What's the weather this week?" |

### 8. Maps & Navigation

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **Google Maps MCP** | Location services, routing, place details, geocoding | "Navigate to the nearest coffee shop" |
| **rideshare-comparison-mcp** | Compare Uber/Lyft prices for any route in real-time | "Get me a ride to the airport" |

### 9. Finance

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **finbrain-mcp** | Institutional-grade alternative financial data | "How are my stocks doing?" |
| **freshcontext-mcp** | Real-time finance data with freshness timestamps | Live market data |

---

## Third tier (nice-to-have / future)

### 10. Memory & Knowledge Base

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **@modelcontextprotocol/server-memory** | Knowledge graph-based persistent memory | Long-term personality |
| **mengram** | Human-like memory: semantic, episodic, procedural — 29 tools | "Remember that I prefer dark mode" |
| **mcp-memory-service** | Semantic search, persistent storage, autonomous consolidation | Deep memory |
| **Obsidian MCP** | Read/write Obsidian vaults — 11 tools | Personal knowledge base |

> FRIDAY already has basic memory (`friday/tools/memory.py`). These are upgrades for semantic/episodic memory if needed.

### 11. Files & Documents

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **mcp-everything-search** | Fast Windows file search using Everything SDK | "Find that PDF I downloaded last week" |
| **markitdown** (Microsoft) | Convert any file format to Markdown for LLM consumption | Process any document |
| **safe-docx** | Surgical Word .docx editing with formatting preservation | Edit documents |
| **filestash** | Remote storage: SFTP, S3, FTP, SMB, WebDAV, Azure, SharePoint | Access remote storage |

### 12. Media Production

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **ffmpeg-mcp** | Video search, trimming, stitching via FFmpeg | Video editing by voice |
| **gemini-media-mcp** | Image gen, video gen, TTS, music gen via Gemini | Full AI media creation |
| **MCPSuno** | Suno AI music generation, lyrics, covers | Generate music on demand |

### 13. IoT & Vehicles

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **TeslaMate MCP** | Tesla vehicle data + remote control — climate, charging, locks, sentry — 29 tools | "Preheat the car" / "Is the car locked?" |
| **Apple Shortcuts MCP** | Trigger any iOS/macOS shortcut | Bridge to Apple ecosystem |

### 14. Productivity

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **GitHub MCP** (official) | Repos, PRs, issues — full GitHub workflow | Dev workflow |
| **Google Tasks MCP** | Google Tasks API | Task management |
| **Apple Reminders** | macOS Reminders integration | "Remind me to call John at 3pm" |

### 15. Code Execution

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **pydantic-ai/mcp-run-python** | Run Python in a secure sandbox | Execute code on demand |
| **mcp-shell-server** | Secure shell command execution | System commands |
| **ssh-mcp** | SSH to remote Linux/Windows servers | Remote management |

### 16. Security

| Server | What it does | JARVIS moment |
|--------|-------------|---------------|
| **fritzbox-mcp-server** | Network management, device monitoring, parental controls | Home network security |
| **chrome-mcp-secure** | Security-hardened Chrome with audit logging | Secure browsing |

---

## Integration priority for FRIDAY

Based on what would make the biggest difference to daily use:

1. **Home Assistant MCP** — smart home is the JARVIS killer feature
2. **Playwright MCP** — browser automation unlocks everything web-based
3. **WhatsApp + Telegram MCPs** — messaging is daily-driver
4. **Spix / telephony** — making phone calls is peak JARVIS
5. **Desktop automation (Terminator)** — control any app by voice
6. **Weather + Maps** — environmental awareness
7. **Everything Search** — instant file finding on Windows
8. **Deep research** — background research tasks
9. **Finance** — portfolio monitoring
10. **Tesla / IoT** — vehicle and device control

---

## What FRIDAY already has

- Google Calendar and Gmail (via MCP, read-only)
- Spotify playback + playlists + volume control
- App launch/close (Start Menu + UWP discovery)
- File read/search (bounded by FRIDAY_FILE_ROOTS)
- Web search (DDGS)
- Song recognition (Gemini multimodal)
- WhatsApp/Discord draft messaging
- Persistent memory (JSON-based)
- Background task orchestration with completion callback
- Google Gemini TTS (Charon voice, JARVIS-tuned)
