"""
System tools — time, environment info, etc.
"""

import platform
from datetime import datetime


def register(mcp):

    @mcp.tool()
    async def get_current_time(timezone: str = "") -> str:
        """Get the current date and time. If no timezone is given, automatically
        detects the user's location via IP geolocation. You can also pass a
        specific IANA timezone like 'America/New_York', 'Europe/London', etc.
        For US states: Georgia/Florida/New York = America/New_York,
        Texas/Illinois = America/Chicago, California = America/Los_Angeles.
        Use this whenever the user asks what time it is."""
        from zoneinfo import ZoneInfo
        import httpx

        location_info = ""

        if not timezone:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(
                        "http://ip-api.com/json/?fields=city,regionName,country,timezone"
                    )
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
            return (
                f"(Could not resolve timezone '{timezone}': {e}) "
                f"Local time is {now.strftime('%I:%M %p')}."
            )

    @mcp.tool()
    def get_system_info() -> dict:
        """Return basic information about the host system."""
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
        }
