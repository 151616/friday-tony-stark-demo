"""
Weather tools — current conditions and multi-day forecasts via Open-Meteo.

No API key required. Uses:
  - ip-api.com        for default geolocation (when no city is given)
  - geocoding-api.open-meteo.com  to resolve city names to lat/lon
  - api.open-meteo.com            for weather data
"""

import json
import urllib.request
import urllib.parse
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# WMO weather interpretation codes → short spoken description
# https://open-meteo.com/en/docs#weathervariables
# ---------------------------------------------------------------------------
_WMO = {
    0: "clear skies",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "icy fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "heavy freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "heavy showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "severe thunderstorms with hail",
}

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _fetch_json(url: str) -> dict:
    """Fetch a URL and return parsed JSON. Raises on HTTP errors."""
    req = urllib.request.Request(url, headers={"User-Agent": "Friday-AI/1.0"})
    with urllib.request.urlopen(req, timeout=6) as resp:
        return json.loads(resp.read().decode())


def _ip_location() -> tuple[float, float, str]:
    """Return (lat, lon, city) from the caller's public IP via ip-api.com."""
    data = _fetch_json("http://ip-api.com/json/?fields=lat,lon,city,status")
    if data.get("status") != "success":
        raise RuntimeError("IP geolocation failed.")
    return data["lat"], data["lon"], data.get("city", "your location")


def _geocode(city: str) -> tuple[float, float, str]:
    """Resolve a city name to (lat, lon, display_name) via Open-Meteo geocoding."""
    params = urllib.parse.urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
    url = f"https://geocoding-api.open-meteo.com/v1/search?{params}"
    data = _fetch_json(url)
    results = data.get("results")
    if not results:
        raise ValueError(f"Couldn't find a location called '{city}'.")
    r = results[0]
    parts = [r.get("name", city)]
    if r.get("admin1"):
        parts.append(r["admin1"])
    if r.get("country_code") and r["country_code"] != "US":
        parts.append(r.get("country", r["country_code"]))
    display = ", ".join(parts)
    return r["latitude"], r["longitude"], display


def _resolve_location(city: str) -> tuple[float, float, str]:
    """Return (lat, lon, display_name). Falls back to IP geolocation when city is empty."""
    city = city.strip()
    if city:
        return _geocode(city)
    return _ip_location()


def _celsius_to_f(c: float) -> int:
    return round(c * 9 / 5 + 32)


def _wind_mph(kmh: float) -> int:
    return round(kmh * 0.621371)


def register(mcp: FastMCP):

    @mcp.tool(name="get_weather")
    def get_weather(city: str = "") -> str:
        """Get the current weather conditions for a location.
        Use for questions like 'What's the weather?', 'Is it cold outside?',
        'Temperature in Tokyo?', or 'Do I need a jacket?'.
        Leave city empty to use the user's current location."""
        try:
            lat, lon, place = _resolve_location(city)
        except ValueError as e:
            return str(e)
        except Exception:
            return "I couldn't determine the location — the geolocation service didn't respond."

        params = urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
        })
        url = f"https://api.open-meteo.com/v1/forecast?{params}"

        try:
            data = _fetch_json(url)
        except Exception:
            return "The weather service isn't responding right now, sir."

        cur = data.get("current", {})
        temp = round(cur.get("temperature_2m", 0))
        feels = round(cur.get("apparent_temperature", temp))
        code = cur.get("weather_code", 0)
        wind = round(cur.get("wind_speed_10m", 0))
        humidity = round(cur.get("relative_humidity_2m", 0))
        condition = _WMO.get(code, "conditions unknown")

        parts = [f"{temp}°F and {condition} in {place}"]
        if abs(feels - temp) >= 4:
            parts.append(f"feels like {feels}°F")
        if wind >= 15:
            parts.append(f"winds at {wind} mph")
        if humidity >= 80:
            parts.append(f"humidity at {humidity}%")

        return ", ".join(parts) + "."

    @mcp.tool(name="get_forecast")
    def get_forecast(city: str = "", days: int = 4) -> str:
        """Get a multi-day weather forecast for a location.
        Use for questions like 'Will it rain tomorrow?', 'What's the weather this week?',
        'Weekend forecast?', or 'Should I bring an umbrella on Friday?'.
        Leave city empty to use the user's current location. Days defaults to 4."""
        try:
            lat, lon, place = _resolve_location(city)
        except ValueError as e:
            return str(e)
        except Exception:
            return "I couldn't determine the location — the geolocation service didn't respond."

        days = max(2, min(days, 7))

        params = urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
            "forecast_days": days,
        })
        url = f"https://api.open-meteo.com/v1/forecast?{params}"

        try:
            data = _fetch_json(url)
        except Exception:
            return "The weather service isn't responding right now, sir."

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        precip = daily.get("precipitation_probability_max", [])

        if not dates:
            return "No forecast data was returned for that location."

        lines = [f"Forecast for {place}:"]
        for i, date_str in enumerate(dates):
            # Parse day name from ISO date string (YYYY-MM-DD)
            try:
                import datetime
                d = datetime.date.fromisoformat(date_str)
                if i == 0:
                    label = "Today"
                elif i == 1:
                    label = "Tomorrow"
                else:
                    label = _DAYS[d.weekday()]
            except Exception:
                label = date_str

            hi = round(highs[i]) if i < len(highs) else "?"
            lo = round(lows[i]) if i < len(lows) else "?"
            condition = _WMO.get(codes[i] if i < len(codes) else 0, "unknown")
            rain_pct = precip[i] if i < len(precip) else 0

            entry = f"{label}: {hi}°F high, {lo}°F low, {condition}"
            if rain_pct is not None and rain_pct >= 30:
                entry += f", {rain_pct}% chance of rain"
            lines.append(entry)

        return ". ".join(lines) + "."
