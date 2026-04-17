"""Messaging smart-gateway tool."""
import os
import urllib.parse
from mcp.server.fastmcp import FastMCP

def register(mcp: FastMCP):
    
    @mcp.tool(name="draft_message")
    def draft_message(platform: str, recipient: str, text: str) -> str:
        """Draft a message to a person on a specific platform (WhatsApp, Discord).
        Use this when the user asks to text or message someone.
        For WhatsApp, it opens the app with the text prefilled.
        For Discord, it copies the text to the clipboard and opens Discord for easy pasting.
        """
        platform = platform.lower().strip()
        
        # We try to ensure user intent handles correctly
        if "whatsapp" in platform:
            escaped_text = urllib.parse.quote(text)
            uri = f"whatsapp://send?text={escaped_text}"
            try:
                os.startfile(uri)
                return f"Opened WhatsApp with your drafted message to {recipient}. Just hit send."
            except Exception as e:
                return f"Failed to open WhatsApp locally: {e}"
                
        elif "discord" in platform:
            # Discord has no send-URI. We copy to clipboard using powershell and focus Discord.
            escaped_text = text.replace("'", "''")
            import subprocess
            try:
                subprocess.run(["powershell", "-command", f"Set-Clipboard -Value '{escaped_text}'"], capture_output=True)
                
                # Try to launch/focus Discord using our apps cache or raw URI path
                # Since Discord registers discord://, we can ping it to bring window up.
                os.startfile("discord://")
                return f"I copied the message to your clipboard and opened Discord. Just paste it to {recipient}!"
            except Exception as e:
                return f"Failed to draft message to Discord: {e}"
        else:
            return f"{platform} is not currently supported for messaging."
