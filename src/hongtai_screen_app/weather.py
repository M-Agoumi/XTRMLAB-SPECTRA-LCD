"""
weather.py -- free, no-API-key current weather lookup, so the
dashboard's middle column (see themes/dashboard_theme.py's
`middle_content` setting) has something to show for anyone who doesn't
want Spotify's now-playing display there -- or anything at all.

Uses Open-Meteo (https://open-meteo.com): free, no signup, no API key,
for both geocoding a plain place name into coordinates and for the
actual current-conditions lookup. Two lightweight HTTP calls over
stdlib `urllib`, the same "no extra dependency for a small HTTP need"
approach control_server.py already takes for its own local API.

Polled from a background thread (same reasoning as dashboard_theme.py's
Spotify polling: a real network round trip has no business happening
inline in the 10Hz render loop), but much less often -- weather doesn't
change on a per-second basis, and Open-Meteo's free tier is generous
but not meant for hammering every frame.
"""
import json
import threading
import time
import urllib.parse
import urllib.request

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

REQUEST_TIMEOUT = 8  # seconds -- a hung DNS/network shouldn't wedge the poll thread
POLL_INTERVAL = 600  # 10 minutes -- plenty fresh for a weather readout

UNIT_OPTIONS = {"celsius": "Celsius (°C)", "fahrenheit": "Fahrenheit (°F)"}

# WMO weather interpretation codes (the scheme Open-Meteo's `weather_code`
# uses) collapsed into a handful of broad categories -- good enough for
# a small on-panel icon + one-line description. See
# https://open-meteo.com/en/docs for the full table this simplifies.
_WMO_CATEGORIES = {
    0: ("clear", "Clear sky"),
    1: ("clear", "Mainly clear"),
    2: ("cloudy", "Partly cloudy"),
    3: ("cloudy", "Overcast"),
    45: ("fog", "Fog"),
    48: ("fog", "Depositing rime fog"),
    51: ("rain", "Light drizzle"),
    53: ("rain", "Drizzle"),
    55: ("rain", "Dense drizzle"),
    56: ("rain", "Freezing drizzle"),
    57: ("rain", "Freezing drizzle"),
    61: ("rain", "Slight rain"),
    63: ("rain", "Rain"),
    65: ("rain", "Heavy rain"),
    66: ("rain", "Freezing rain"),
    67: ("rain", "Freezing rain"),
    71: ("snow", "Slight snow"),
    73: ("snow", "Snow"),
    75: ("snow", "Heavy snow"),
    77: ("snow", "Snow grains"),
    80: ("rain", "Rain showers"),
    81: ("rain", "Rain showers"),
    82: ("rain", "Violent rain showers"),
    85: ("snow", "Snow showers"),
    86: ("snow", "Snow showers"),
    95: ("storm", "Thunderstorm"),
    96: ("storm", "Thunderstorm, hail"),
    99: ("storm", "Thunderstorm, hail"),
}


def categorize(weather_code):
    """(icon_category, description) for a WMO weather_code -- category
    is one of "clear"/"cloudy"/"fog"/"rain"/"snow"/"storm", falling
    back to ("cloudy", "--") for a code not in the table above
    (Open-Meteo's table is stable, but this is cheap insurance)."""
    return _WMO_CATEGORIES.get(weather_code, ("cloudy", "--"))


def _http_get_json(url, params):
    qs = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{qs}", timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode(location):
    """Resolves a free-typed place name ("Paris, FR", "90210", "Tokyo")
    into (lat, lon, display_name), or None if it can't be resolved (a
    typo, an empty string, or a network error). `display_name` is
    Open-Meteo's own resolved label (city + admin region + country) so
    what ends up on the panel reflects what was actually matched, not
    just an echo of whatever was typed."""
    location = (location or "").strip()
    if not location:
        return None
    try:
        data = _http_get_json(GEOCODE_URL, {"name": location, "count": 1, "language": "en", "format": "json"})
    except Exception:  # noqa: BLE001 -- no network, DNS failure, bad response, ...
        return None
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    parts = [r.get("name")]
    if r.get("admin1") and r.get("admin1") != r.get("name"):
        parts.append(r["admin1"])
    if r.get("country"):
        parts.append(r["country"])
    display_name = ", ".join(p for p in parts if p)
    return r["latitude"], r["longitude"], display_name


def fetch_current(lat, lon, units="celsius"):
    """One current-conditions snapshot for (lat, lon). Returns a dict
    (temperature, feels_like, humidity, wind_speed, weather_code, icon,
    description, units) or None on any failure (no network, bad
    coordinates, an Open-Meteo hiccup) -- callers treat that exactly
    like "no data yet", the same tolerance dashboard_theme.py's own
    get_media_info() has for "no Spotify session found"."""
    temperature_unit = "fahrenheit" if units == "fahrenheit" else "celsius"
    wind_speed_unit = "mph" if units == "fahrenheit" else "kmh"
    try:
        data = _http_get_json(FORECAST_URL, {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "temperature_unit": temperature_unit,
            "wind_speed_unit": wind_speed_unit,
            "timezone": "auto",
        })
        current = data["current"]
        code = current.get("weather_code")
        icon, description = categorize(code)
        return {
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "weather_code": code,
            "icon": icon,
            "description": description,
            "units": "fahrenheit" if units == "fahrenheit" else "celsius",
        }
    except Exception:  # noqa: BLE001
        return None


# --- background polling ------------------------------------------------

_lock = threading.Lock()
_latest = None          # last snapshot/error dict from fetch_current(), or None
_thread_started = False
_current_location = None
_current_units = "celsius"
_geocode_cache = {}      # location string -> (lat, lon, display_name), successes only
_wake = threading.Event()  # lets set_location()/set_units() skip the rest of a stale wait


def set_location(location):
    """Changes which place the poll loop fetches for -- takes effect on
    the very next poll (wakes the thread immediately rather than
    waiting out whatever's left of the current 10-minute interval), the
    same "no restart needed" live-apply deal as dashboard_theme.py's
    set_default_art_path()/set_not_playing_message()."""
    global _current_location
    new = (location or "").strip() or None
    if new != _current_location:
        _current_location = new
        with _lock:
            global _latest
            _latest = None  # stale snapshot for the old location -- don't show it
        _wake.set()


def set_units(units):
    global _current_units
    new = "fahrenheit" if units == "fahrenheit" else "celsius"
    if new != _current_units:
        _current_units = new
        _wake.set()


def _poll_worker():
    global _latest
    while True:
        location = _current_location
        units = _current_units
        if not location:
            with _lock:
                _latest = None
        else:
            geo = _geocode_cache.get(location)
            if geo is None:
                geo = geocode(location)
                if geo is not None:
                    _geocode_cache[location] = geo
            if geo is None:
                with _lock:
                    _latest = {"error": f"couldn't find a place called {location!r}"}
            else:
                lat, lon, display_name = geo
                current = fetch_current(lat, lon, units)
                if current is None:
                    with _lock:
                        _latest = {"error": "weather lookup failed (no network?)"}
                else:
                    current["location_name"] = display_name
                    with _lock:
                        _latest = current
        _wake.wait(POLL_INTERVAL)
        _wake.clear()


def start_polling():
    """Idempotent, like dashboard_theme.py's start_media_polling() --
    safe to call any time a setting changes, whether or not the
    Dashboard theme actually happens to be running right now."""
    global _thread_started
    if _thread_started:
        return
    _thread_started = True
    threading.Thread(target=_poll_worker, daemon=True).start()


def get_weather():
    """Latest snapshot, non-blocking. None if no location is set and
    nothing's ever been fetched; otherwise the dict fetch_current()
    returned (plus "location_name"), or {"error": "..."} if the last
    attempt failed -- same non-blocking-snapshot shape as
    dashboard_theme.py's get_media_info()."""
    with _lock:
        return dict(_latest) if _latest else None
