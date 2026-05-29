"""
Weather tools — current conditions via OpenWeatherMap (free tier).
"""

import os
import httpx

# Fallback city if not set in .env
DEFAULT_CITY = os.getenv("WEATHER_CITY", "São Paulo")


def register(mcp):

    @mcp.tool()
    async def get_weather(city: str = None) -> str:
        """
        Get current weather conditions for a city.
        Defaults to the user's configured city (WEATHER_CITY env var).
        Use when asked about the weather, temperature, or conditions outside.
        """
        target = city or os.getenv("WEATHER_CITY", DEFAULT_CITY)
        api_key = os.getenv("OPENWEATHERMAP_API_KEY")

        if not api_key:
            return "Weather service not configured, boss. OPENWEATHERMAP_API_KEY is missing."

        try:
            async with httpx.AsyncClient(timeout=6) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={
                        "q": target,
                        "appid": api_key,
                        "units": "metric",
                        "lang": "en",
                    },
                )
                if resp.status_code == 404:
                    return f"Couldn't find weather data for '{target}', boss."
                if resp.status_code != 200:
                    return "Weather service is unresponsive right now."

                d = resp.json()

            desc = d["weather"][0]["description"].capitalize()
            temp = d["main"]["temp"]
            feels = d["main"]["feels_like"]
            humidity = d["main"]["humidity"]
            wind_kph = round(d["wind"]["speed"] * 3.6, 1)
            city_name = d.get("name", target)

            return (
                f"{city_name}: {desc}. "
                f"{temp:.0f}°C, feels like {feels:.0f}°C. "
                f"Humidity {humidity}%, wind {wind_kph} km/h."
            )

        except Exception as e:
            return f"Weather feed down, boss: {e}"
