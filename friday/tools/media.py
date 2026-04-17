"""Media control tool."""
import os
import keyboard
import urllib.parse
from mcp.server.fastmcp import FastMCP

def register(mcp: FastMCP):
    
    @mcp.tool(name="play_pause_media")
    def play_pause_media() -> str:
        """Toggle play/pause for currently active media (like Spotify, YouTube)."""
        keyboard.send("play/pause media")
        return "Toggled playback."
        
    @mcp.tool(name="next_track")
    def next_track() -> str:
        """Skip to the next media track."""
        keyboard.send("next track")
        return "Skipped to next track."

    @mcp.tool(name="previous_track")
    def previous_track() -> str:
        """Go back to the previous media track."""
        keyboard.send("previous track")
        return "Went to previous track."
        
    @mcp.tool(name="search_spotify")
    async def search_spotify(query: str) -> str:
        """Search Spotify for a track and instantly auto-play it. 
        Use this when the user says 'play <song> on spotify'.
        """
        import asyncio
        from ddgs import DDGS
        import re
        
        def _get_track_uri():
            try:
                with DDGS() as ddgs:
                    # Append site restriction to force exact track links
                    search_query = f"{query} site:open.spotify.com/track"
                    results = list(ddgs.text(search_query, max_results=3))
                    
                    for r in results:
                        link = r.get("href", "")
                        match = re.search(r"open\.spotify\.com/track/([a-zA-Z0-9]+)", link)
                        if match:
                            return match.group(1)
                return None
            except Exception as e:
                print(f"DDGS Error: {e}")
                return None

        # Run synchronous web request offline
        track_id = await asyncio.get_event_loop().run_in_executor(None, _get_track_uri)
        
        if track_id:
            try:
                os.startfile(f"spotify:track:{track_id}")
                return f"I found the track and started playing it immediately."
            except Exception as e:
                return f"Failed to auto-play Spotify track: {e}"
        else:
            # Fallback to normal search
            escaped_query = urllib.parse.quote(query)
            try:
                os.startfile(f"spotify:search:{escaped_query}")
                return f"I couldn't find an auto-play link, but I opened the Spotify search page for '{query}'."
            except Exception as e:
                return f"Failed to open Spotify: {e}"
