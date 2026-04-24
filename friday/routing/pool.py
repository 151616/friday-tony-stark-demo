from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from livekit.agents.llm.mcp import MCPServerStdio, MCPToolset

from friday.routing.domains import DOMAINS


class LocalDomainToolPool:
    """Lazily manages local MCP toolsets per domain, with auto-shutdown for idle memory."""

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = Path(repo_root)
        self._toolsets: dict[str, MCPToolset] = {}
        self._last_accessed: dict[str, float] = {}
        self._bg_task = None

    def _start_reaper_if_needed(self):
        if self._bg_task is None or self._bg_task.done():
            self._bg_task = asyncio.create_task(self._reaper_loop())

    async def _reaper_loop(self):
        while True:
            await asyncio.sleep(10)
            now = asyncio.get_running_loop().time()
            to_close = []
            for domain, toolset in list(self._toolsets.items()):
                # Keep 'core' alive permanently to reduce latency on basic commands
                if domain == "core":
                    continue
                # If unused for 120 seconds (2 minutes), shut it down to free RAM
                if now - self._last_accessed.get(domain, now) > 120.0:
                    to_close.append(domain)
            
            for domain in to_close:
                toolset = self._toolsets.pop(domain, None)
                if toolset:
                    self._last_accessed.pop(domain, None)
                    print(f"[\033[93mMemory Manager\033[0m] Shutting down idle domain to free RAM: {domain}", flush=True)
                    asyncio.create_task(toolset.aclose())

    def _create_toolset(self, domain: str) -> MCPToolset:
        if domain not in DOMAINS:
            raise ValueError(f"Unknown routing domain: {domain!r}")

        return MCPToolset(
            id=f"friday-{domain}",
            mcp_server=MCPServerStdio(
                command=sys.executable,
                args=[str(self._repo_root / "server.py"), "--domain", domain],
                cwd=str(self._repo_root),
                client_session_timeout_seconds=15,
            ),
        )

    def get_toolset(self, domain: str) -> MCPToolset:
        self._start_reaper_if_needed()
        self._last_accessed[domain] = asyncio.get_running_loop().time()
        
        toolset = self._toolsets.get(domain)
        if toolset is None:
            toolset = self._create_toolset(domain)
            self._toolsets[domain] = toolset
        return toolset

    async def get_toolsets(self, domains: list[str]) -> list[MCPToolset]:
        now = asyncio.get_running_loop().time()
        for d in domains:
            self._last_accessed[d] = now

        ordered_domains = list(dict.fromkeys(domains))
        toolsets = [self.get_toolset(domain) for domain in ordered_domains]
        for toolset in toolsets:
            # Shield to prevent agent cancellation (e.g. from user interruption) from cancelling
            # the underlying MCP initialization, which would crash the MCP subprocess due to an SDK bug.
            await asyncio.shield(toolset.setup())
        return toolsets

    async def aclose(self) -> None:
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
        for toolset in list(self._toolsets.values()):
            await toolset.aclose()
        self._toolsets.clear()
        self._last_accessed.clear()
