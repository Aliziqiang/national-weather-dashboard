#!/usr/bin/env python3
"""Refresh the public dashboard snapshot without exposing QWeather credentials."""

from __future__ import annotations

import json
import gzip
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CITY_FILE = ROOT / "cities.json"
DATA_FILE = ROOT / "weather-data.json"
TZ = ZoneInfo("Asia/Shanghai")
MAX_DAILY_CALLS = 1000
CURRENT_PER_RUN = 310
MINUTELY_PER_RUN = 11
REQUEST_INTERVAL_SECONDS = 0.66  # Free plan is limited to 100 QPM.


class BudgetExhausted(RuntimeError):
    pass


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required GitHub variable/secret: {name}")
    return value


class QWeather:
    def __init__(self, host: str, api_key: str, request_budget: int) -> None:
        self.host = host.removeprefix("https://").removeprefix("http://").strip("/")
        self.api_key = api_key
        self.request_budget = max(0, request_budget)
        self.last_call = 0.0
        self.calls = 0

    def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        if self.calls >= self.request_budget:
            raise BudgetExhausted("Today's free-plan request budget has been reached; retaining cached data")
        wait = REQUEST_INTERVAL_SECONDS - (time.monotonic() - self.last_call)
        if self.last_call and wait > 0:
            time.sleep(wait)
        url = f"https://{self.host}{path}"
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={"X-QW-Api-Key": self.api_key, "Accept": "application/json"})
        self.last_call = time.monotonic()
        self.calls += 1
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    body = gzip.decompress(body)
                payload = json.loads(body.decode("utf-8"))
        except HTTPError as exc:
            if exc.code in (401, 403):
                # Stop immediately on authentication, quota, or access failures.
                # Do not burn the daily request budget or publish an empty snapshot.
                raise SystemExit(
                    f"QWeather rejected the request (HTTP {exc.code}); stopping before publishing data"
                ) from exc
            raise RuntimeError(f"QWeather request failed: {exc.code} {exc}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"QWeather request failed: {getattr(exc, 'code', '')} {exc}") from exc
        return payload


def value(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else default


def nested_number(obj: Any, key: str) -> float | None:
    raw = value(obj, key)
    raw = value(raw, "value", raw)
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def humidity_percent(raw: Any) -> float | None:
    number = raw
    try:
        number = float(value(raw, "value", raw))
    except (TypeError, ValueError):
        return None
    if 0 <= number <= 1:
        number *= 100
    return max(0, min(100, number))


def get_current(api: QWeather, city: dict[str, Any]) -> dict[str, Any]:
    lat, lon = f"{city['lat']:.2f}", f"{city['lon']:.2f}"
    raw = api.get(f"/weather/v1/current/{lat}/{lon}", {"localTime": "true", "lang": "zh"})
    # Accept both current v1 and the older v7 object shape while accounts migrate.
    current = value(raw, "now", raw)
    condition = value(raw, "condition", {})
    temp = nested_number(raw, "temperature")
    if temp is None:
        temp = nested_number(current, "temp")
    humidity = humidity_percent(value(raw, "humidity"))
    if humidity is None:
        humidity = humidity_percent(value(raw, "relativeHumidity"))
    if humidity is None:
        humidity = humidity_percent(value(current, "humidity"))
    if humidity is None:
        humidity = humidity_percent(value(current, "relativeHumidity"))
    dew = nested_number(raw, "dewPoint")
    if dew is None:
        dew = nested_number(raw, "dew")
    if dew is None:
        dew = nested_number(current, "dewPoint")
    if dew is None:
        dew = nested_number(current, "dew")
    return {
        "temp": temp,
        "text": value(condition, "text") or value(current, "text") or "",
        "code": str(value(condition, "code") or value(current, "icon") or ""),
        "precip": nested_number(raw, "precipitation") if nested_number(raw, "precipitation") is not None else nested_number(current, "precip"),
        "humidity": humidity,
        "dew": dew,
        "obsTime": value(raw, "updateTime") or value(current, "obsTime") or "",
        "updatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
    }


def normalize_days(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows = value(raw, "days") or value(raw, "daily") or []
    result = []
    for row in rows:
        daypart = value(row, "daytime", {})
        nightpart = value(row, "nighttime", {})
        condition = value(row, "condition", {}) or value(daypart, "condition", {}) or value(nightpart, "condition", {})
        if isinstance(condition, dict) and not condition:
            condition = value(daypart, "condition", {}) or value(nightpart, "condition", {})
        precip_day = value(daypart, "precipitation", {})
        precip_night = value(nightpart, "precipitation", {})
        precip = value(row, "precipitation", {})

        # v1 probabilities use 0-1; v7 uses 0-100 in the "pop" field.
        probabilities = [value(precip, "probability"), value(precip_day, "probability"), value(precip_night, "probability")]
        probabilities = [x for x in probabilities if x is not None]
        if not probabilities:
            probabilities = [value(row, "pop", 0)]
        normalized = []
        for probability in probabilities:
            try:
                probability = float(probability or 0)
                normalized.append(probability * 100 if probability <= 1 else probability)
            except (TypeError, ValueError):
                pass
        probability = max(normalized, default=0)

        amount = nested_number(precip, "amount")
        if amount is None:
            amount = (nested_number(precip_day, "amount") or 0) + (nested_number(precip_night, "amount") or 0)
        humidity_values = [
            humidity_percent(value(daypart, "humidity", value(daypart, "relativeHumidity"))),
            humidity_percent(value(nightpart, "humidity", value(nightpart, "relativeHumidity"))),
        ]
        humidity_values = [number for number in humidity_values if number is not None]
        humidity = sum(humidity_values) / len(humidity_values) if humidity_values else humidity_percent(value(row, "humidity"))
        temp_max = nested_number(row, "temperatureMax") if nested_number(row, "temperatureMax") is not None else nested_number(row, "tempMax")
        temp_min = nested_number(row, "temperatureMin") if nested_number(row, "temperatureMin") is not None else nested_number(row, "tempMin")
        temp_avg = nested_number(row, "temperatureAvg")
        if temp_avg is None and temp_max is not None and temp_min is not None:
            temp_avg = (temp_max + temp_min) / 2
        date = str(value(row, "forecastStartTime") or value(row, "fxDate") or "")[:10]
        if not date:
            continue
        rain_text = " ".join(
            str(value(value(part, "condition", {}), "text") or "")
            for part in (daypart, nightpart)
        ).strip()
        result.append({
            "date": date,
            "text": value(condition, "text") or value(row, "text") or "",
            "rainText": rain_text or value(condition, "text") or value(row, "text") or "",
            "code": str(value(condition, "code") or value(row, "icon") or ""),
            "tempMax": temp_max,
            "tempMin": temp_min,
            "tempAvg": temp_avg,
            "humidity": humidity,
            "probability": round(max(0, min(100, probability))),
            "amount": amount or 0,
        })
    return result[:7]


def get_daily(api: QWeather, city: dict[str, Any]) -> list[dict[str, Any]]:
    lat, lon = f"{city['lat']:.2f}", f"{city['lon']:.2f}"
    raw = api.get(f"/weather/v1/daily/{lat}/{lon}", {"days": "7", "localTime": "true", "lang": "zh"})
    return normalize_days(raw)


def get_minutely(api: QWeather, city: dict[str, Any]) -> dict[str, Any]:
    location = f"{city['lon']:.2f},{city['lat']:.2f}"
    raw = api.get("/v7/minutely/5m", {"location": location, "lang": "zh"})
    return {"summary": value(raw, "summary") or "暂无临近降水", "updateTime": value(raw, "updateTime"), "items": value(raw, "minutely", [])}


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def rain_rank(city_name: str, record: dict[str, Any]) -> tuple[float, float, int]:
    days = record.get("daily") or []
    first = days[0] if days else {}
    current = record.get("current") or {}
    text = f"{first.get('text', '')} {current.get('text', '')}"
    risk = float(first.get("probability") or 0)
    amount = float(first.get("amount") or 0)
    raining = any(word in text for word in ("雨", "雷", "冰雹")) or float(current.get("precip") or 0) > 0
    return (1 if raining else 0, risk, amount)


def main() -> int:
    cities = json.loads(CITY_FILE.read_text(encoding="utf-8"))
    now = datetime.now(TZ)
    # Scheduled runs use their intended slot even if GitHub starts them late.
    # Manual runs retain the local-time behavior.
    run_mode = os.environ.get("QWEATHER_RUN_MODE", "").strip().lower()
    morning = run_mode == "morning" if run_mode in {"morning", "evening"} else now.hour < 12
    old = load_json(DATA_FILE, {"updatedAt": None, "cities": {}})
    records: dict[str, Any] = old.get("cities", {})
    # Cooling comparisons use today's forecast as the baseline in the dashboard;
    # older forecast snapshots are no longer needed.
    for record in records.values():
        if isinstance(record, dict):
            record.pop("previousForecast", None)
    today_index = now.timetuple().tm_yday

    # Rotate two disjoint groups of 28 cities. Each city still gets current weather
    # at least once each day; the other 310 get the scheduled morning and evening refresh.
    skip_start = ((today_index - 1) * 56) % len(cities)
    offset = 0 if morning else 28
    skipped = {(skip_start + offset + i) % len(cities) for i in range(28)}
    current_targets = [city for i, city in enumerate(cities) if i not in skipped]

    prior_calls = old.get("requestsToday", 0) if old.get("requestDate") == now.date().isoformat() else 0
    api = QWeather(required("QWEATHER_API_HOST"), required("QWEATHER_API_KEY"), MAX_DAILY_CALLS - int(prior_calls or 0))
    errors = 0

    daily_targets = cities if morning else [city for city in cities if not (records.get(city["name"]) or {}).get("daily")]
    for city in daily_targets:
        record = records.setdefault(city["name"], {})
        try:
            record["daily"] = get_daily(api, city)
            record["forecastUpdatedAt"] = datetime.now(TZ).isoformat(timespec="seconds")
        except BudgetExhausted:
            break
        except Exception as exc:  # keep last good value for a transient city-level error
            errors += 1
            print(f"Daily forecast unavailable for {city['name']}: {exc}", file=sys.stderr)

    for city in current_targets:
        record = records.setdefault(city["name"], {})
        try:
            record["current"] = get_current(api, city)
        except BudgetExhausted:
            break
        except Exception as exc:
            errors += 1
            print(f"Current weather unavailable for {city['name']}: {exc}", file=sys.stderr)

    # Minute precipitation is short-lived and useful mainly for cities with the
    # strongest rain signal. Limit it to 11 cities per refresh to stay under quota.
    candidates = sorted(cities, key=lambda city: rain_rank(city["name"], records.get(city["name"], {})), reverse=True)
    minute_success = 0
    for city in candidates[:MINUTELY_PER_RUN]:
        record = records.setdefault(city["name"], {})
        try:
            record["minutely"] = get_minutely(api, city)
            record["minutelyUpdatedAt"] = datetime.now(TZ).isoformat(timespec="seconds")
            minute_success += 1
        except BudgetExhausted:
            break
        except Exception as exc:
            errors += 1
            print(f"Minute precipitation unavailable for {city['name']}: {exc}", file=sys.stderr)

    snapshot = {
        "source": "QWeather",
        "updatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "mode": "morning" if morning else "evening",
        "requestCountThisRun": api.calls,
        "requestDate": now.date().isoformat(),
        "requestsToday": int(prior_calls or 0) + api.calls,
        "cityCount": len(cities),
        "minutelyCityCountThisRun": minute_success,
        "errorsThisRun": errors,
        "attribution": "https://developer.qweather.com/attribution.html",
        "cities": records,
    }
    DATA_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} city records; mode={snapshot['mode']}; requests={api.calls}; minute={minute_success}; errors={errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
