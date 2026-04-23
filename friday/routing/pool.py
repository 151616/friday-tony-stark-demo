from __future__ import annotations

import sys
from pathlib import Path

from livekit.agents.llm.mcp import MCPServerStdio, MCPToolset

from friday.routing.domains import DOMAINS


class LocalDomainToolPool:
    """Lazily manages local MCP toolsets per domain."""

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = Path(repo_root)
        self._toolsets: dict[str, MCPToolset] = {}

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
        toolset = self._toolsets.get(domain)
        if toolset is None:
            toolset = self._create_toolset(domain)
            self._toolsets[domain] = toolset
        return toolset

    async def get_toolsets(self, domains: list[str]) -> list[MCPToolset]:
        ordered_domains = list(dict.fromkeys(domains))
        toolsets = [self.get_toolset(domain) for domain in ordered_domains]
        for toolset in toolsets:
            await toolset.setup()
        return toolsets

    async def aclose(self) -> None:
        for toolset in list(self._toolsets.values()):
            await toolset.aclose()
        self._toolsets.clear()
