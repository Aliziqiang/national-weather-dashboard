#!/usr/bin/env python3
"""Refresh the public dashboard snapshot without exposing QWeather credentials."""

from __future__ import annotations

import json
import gzip
import os
import sys
import time
from datetime import datetime, timedelta
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
EVENING_RAINY_FORECAST_REFRESHES = 20
REQUEST_INTERVAL_SECONDS = 0.66  # Free plan is limited to 100 QPM.
OPEN_METEO_BATCH_SIZE = 70
OPEN_METEO_HOURLY_FIELDS = "temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,weather_code"


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


def parse_local_forecast_time(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def is_wet_hour(row: dict[str, Any]) -> bool:
    condition = value(row, "condition", {})
    text = str(value(condition, "text") or "")
    precipitation = value(row, "precipitation", {})
    precip_type = str(value(precipitation, "type") or "").lower()
    amount = nested_number(precipitation, "amount") or 0
    rain_condition = any(word in text for word in ("雨", "雷", "冰雹", "冻雨"))
    if "雪" in text and not rain_condition and precip_type == "snow":
        return False
    return (
        rain_condition
        or precip_type in {"rain", "ice", "mixed"}
        or (amount > 0 and precip_type != "snow")
    )


def normalize_hourly_days(raw: dict[str, Any], today: str) -> list[dict[str, Any]]:
    """Aggregate hourly forecasts into dashboard days and daylight drying inputs."""
    grouped: dict[str, list[tuple[datetime, dict[str, Any]]]] = {}
    last_date = (datetime.fromisoformat(today).date() + timedelta(days=6)).isoformat()
    for row in value(raw, "hours", []) or []:
        if not isinstance(row, dict):
            continue
        forecast_time = parse_local_forecast_time(value(row, "forecastTime"))
        if forecast_time is None:
            continue
        date = forecast_time.date().isoformat()
        if today <= date <= last_date:
            grouped.setdefault(date, []).append((forecast_time, row))

    result: list[dict[str, Any]] = []
    for date in sorted(grouped):
        hours = sorted(grouped[date], key=lambda item: item[0])
        daylight = [(moment, row) for moment, row in hours if 7 <= moment.hour < 19]
        daytime_wet = [(moment, row) for moment, row in daylight if is_wet_hour(row)]

        def values(rows: list[tuple[datetime, dict[str, Any]]], key: str) -> list[float]:
            return [number for _, row in rows if (number := nested_number(row, key)) is not None]

        temperatures = values(hours, "temperature")
        humidity_all = [number for _, row in hours if (number := humidity_percent(value(row, "humidity"))) is not None]
        humidity_day = [number for _, row in daylight if (number := humidity_percent(value(row, "humidity"))) is not None]
        dew_day = values(daylight, "dewPoint")
        daytime_temps = values(daylight, "temperature")
        probability_values: list[float] = []
        precipitation_amount = 0.0
        for _, row in hours:
            precipitation = value(row, "precipitation", {})
            probability = nested_number(precipitation, "probability")
            if probability is not None:
                probability_values.append(probability * 100 if probability <= 1 else probability)
            precipitation_amount += nested_number(precipitation, "amount") or 0

        texts = [str(value(value(row, "condition", {}), "text") or "") for _, row in hours]
        text = max(set(texts), key=texts.count) if texts else ""
        codes = [str(value(value(row, "condition", {}), "code") or "") for _, row in hours]
        code = max(set(codes), key=codes.count) if codes else ""
        rain_texts = [str(value(value(row, "condition", {}), "text") or "") for _, row in hours if is_wet_hour(row)]
        day_rain_texts = [str(value(value(row, "condition", {}), "text") or "") for _, row in daytime_wet]

        result.append({
            "date": date,
            "text": text,
            "rainText": " ".join(dict.fromkeys(rain_texts)),
            "dayRainText": " ".join(dict.fromkeys(day_rain_texts)),
            "code": code,
            "tempMax": max(temperatures) if temperatures else None,
            "tempMin": min(temperatures) if temperatures else None,
            "tempAvg": sum(temperatures) / len(temperatures) if temperatures else None,
            "tempDayAvg": sum(daytime_temps) / len(daytime_temps) if daytime_temps else None,
            "humidity": sum(humidity_all) / len(humidity_all) if humidity_all else None,
            "humidityDay": sum(humidity_day) / len(humidity_day) if humidity_day else None,
            "dewDay": sum(dew_day) / len(dew_day) if dew_day else None,
            "probability": round(max(0, min(100, max(probability_values, default=0)))),
            "amount": precipitation_amount,
            "rainHours": len(daytime_wet),
            "availableDayHours": len(daylight),
        })
    return result


def is_unfavorable_drying_day(day: dict[str, Any]) -> bool | None:
    humidity = nested_number(day, "humidityDay")
    if humidity is None:
        humidity = humidity_percent(value(day, "humidity"))
    rain_hours = nested_number(day, "rainHours")
    if rain_hours is None:
        # Older snapshots do not have hourly totals; retain a best-effort history
        # from their daily condition and precipitation fields until new data lands.
        wet = bool(
            float(day.get("amount") or 0) > 0
            or any(word in f"{day.get('rainText', '')} {day.get('text', '')}" for word in ("雨", "雷", "冰雹", "冻雨"))
        )
    else:
        wet = rain_hours > 0
    if humidity is None and rain_hours is None and not day.get("rainText") and not day.get("text"):
        return None
    return wet or (humidity is not None and humidity >= 85)


def preserve_drying_history(record: dict[str, Any], today: str) -> None:
    """Carry past unfavorable-day flags across daily forecast refreshes."""
    history: dict[str, dict[str, Any]] = {}
    for item in record.get("dryingHistory", []) or []:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "")[:10]
        if date and date < today and item.get("unfavorable") is not None:
            history[date] = item
    for day in record.get("daily", []) or []:
        if not isinstance(day, dict):
            continue
        date = str(day.get("date") or "")[:10]
        unfavorable = is_unfavorable_drying_day(day)
        if date and date < today and unfavorable is not None:
            history[date] = {
                "date": date,
                "unfavorable": unfavorable,
                "tempAvg": day.get("tempDayAvg", day.get("tempAvg")),
            }
    cutoff = (datetime.now(TZ).date() - timedelta(days=10)).isoformat()
    record["dryingHistory"] = [history[date] for date in sorted(history) if date >= cutoff]


def preserve_low_temp_history(record: dict[str, Any], today: str) -> None:
    """Keep recent past forecast lows so cold streaks can cross refreshes."""
    history: dict[str, dict[str, Any]] = {}
    for item in record.get("lowTempHistory", []) or []:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "")[:10]
        if date and date < today and item.get("tempMin") is not None:
            history[date] = {"date": date, "tempMin": item["tempMin"]}
    for item in record.get("daily", []) or []:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "")[:10]
        if date and date < today and item.get("tempMin") is not None:
            history[date] = {"date": date, "tempMin": item["tempMin"]}

    cutoff = (datetime.now(TZ).date() - timedelta(days=10)).isoformat()
    record["lowTempHistory"] = [history[date] for date in sorted(history) if date >= cutoff]


def get_daily(api: QWeather, city: dict[str, Any]) -> list[dict[str, Any]]:
    lat, lon = f"{city['lat']:.2f}", f"{city['lon']:.2f}"
    raw = api.get(f"/weather/v1/daily/{lat}/{lon}", {"days": "7", "localTime": "true", "lang": "zh"})
    return normalize_days(raw)


def get_hourly_days(api: QWeather, city: dict[str, Any], today: str) -> list[dict[str, Any]]:
    lat, lon = f"{city['lat']:.2f}", f"{city['lon']:.2f}"
    raw = api.get(f"/weather/v1/hourly/{lat}/{lon}", {"hours": "168", "localTime": "true", "lang": "zh"})
    return normalize_hourly_days(raw, today)


def get_open_meteo_drying_metrics(cities: list[dict[str, Any]]) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    """Fetch daytime hourly inputs used by the dryer score, in coordinate batches."""
    metrics_by_city: dict[str, dict[str, dict[str, Any]]] = {}
    errors: list[str] = []
    for start in range(0, len(cities), OPEN_METEO_BATCH_SIZE):
        batch = cities[start:start + OPEN_METEO_BATCH_SIZE]
        params = urlencode({
            "latitude": ",".join(str(city["lat"]) for city in batch),
            "longitude": ",".join(str(city["lon"]) for city in batch),
            "hourly": OPEN_METEO_HOURLY_FIELDS,
            "timezone": "Asia/Shanghai",
            "forecast_days": "7",
            "forecast_hours": "168",
            # Include today's earlier daylight hours when a refresh runs in the evening.
            "past_hours": "24",
        })
        request = Request(
            f"https://api.open-meteo.com/v1/forecast?{params}",
            headers={"Accept": "application/json", "User-Agent": "national-weather-dashboard/1.0"},
        )
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError(str(payload.get("reason") or "Open-Meteo returned an error"))
            locations = payload if isinstance(payload, list) else [payload]
            if len(locations) != len(batch):
                raise RuntimeError(f"Open-Meteo returned {len(locations)} locations for a batch of {len(batch)}")
        except Exception as exc:
            errors.append(f"batch {start // OPEN_METEO_BATCH_SIZE + 1}: {exc}")
            continue

        for city, location in zip(batch, locations):
            hourly = value(location, "hourly", {})
            times = value(hourly, "time", []) or []
            groups: dict[str, list[dict[str, Any]]] = {}
            for index, timestamp in enumerate(times):
                text = str(timestamp)
                if len(text) < 13:
                    continue
                date, hour = text[:10], int(text[11:13])
                if not 7 <= hour < 19:
                    continue

                def item(field: str) -> Any:
                    values = value(hourly, field, []) or []
                    return values[index] if index < len(values) else None

                groups.setdefault(date, []).append({
                    "humidity": item("relative_humidity_2m"),
                    "dew": item("dew_point_2m"),
                    "temperature": item("temperature_2m"),
                    "precipitation": item("precipitation"),
                    "weather_code": item("weather_code"),
                })

            city_metrics: dict[str, dict[str, Any]] = {}
            for date, daylight in groups.items():
                def mean(field: str) -> float | None:
                    values: list[float] = []
                    for row in daylight:
                        try:
                            raw = row[field]
                            if raw is not None:
                                values.append(float(raw))
                        except (TypeError, ValueError):
                            continue
                    return sum(values) / len(values) if values else None

                def is_rain_hour(row: dict[str, Any]) -> bool:
                    try:
                        code = int(float(row["weather_code"])) if row["weather_code"] is not None else None
                    except (TypeError, ValueError):
                        code = None
                    snow_codes = {71, 73, 75, 77, 85, 86}
                    rain_codes = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
                    if code in snow_codes:
                        return False
                    if code in rain_codes:
                        return True
                    try:
                        return float(row["precipitation"] or 0) > 0
                    except (TypeError, ValueError):
                        return False

                city_metrics[date] = {
                    "humidityDay": mean("humidity"),
                    "dewDay": mean("dew"),
                    "tempDayAvg": mean("temperature"),
                    "rainHours": sum(1 for row in daylight if is_rain_hour(row)),
                    "availableDayHours": len(daylight),
                }
            metrics_by_city[city["name"]] = city_metrics
    return metrics_by_city, errors


def supplement_drying_metrics(
    cities: list[dict[str, Any]], records: dict[str, Any]
) -> tuple[int, int, list[str]]:
    """Fill missing QWeather hourly score inputs with Open-Meteo and refresh prior fallback values."""
    metrics_by_city, errors = get_open_meteo_drying_metrics(cities)
    updated_cities = 0
    updated_days = 0
    fields = ("humidityDay", "dewDay", "tempDayAvg", "rainHours", "availableDayHours")
    fetched_at = datetime.now(TZ).isoformat(timespec="seconds")
    for city in cities:
        record = records.get(city["name"])
        if not isinstance(record, dict):
            continue
        city_metrics = metrics_by_city.get(city["name"], {})
        city_updated = False
        for day in record.get("daily", []) or []:
            if not isinstance(day, dict):
                continue
            fallback = city_metrics.get(str(day.get("date") or "")[:10])
            if not fallback:
                continue
            sources = day.get("dryingMetricsSources")
            if not isinstance(sources, dict):
                sources = {}
            try:
                qweather_daylight_hours = int(float(day.get("availableDayHours")))
            except (TypeError, ValueError):
                qweather_daylight_hours = 0
            qweather_day_is_partial = qweather_daylight_hours < 12
            day_updated = False
            for field in fields:
                value_from_open_meteo = fallback.get(field)
                if value_from_open_meteo is None:
                    continue
                if day.get(field) is None or sources.get(field) == "Open-Meteo" or qweather_day_is_partial:
                    day[field] = value_from_open_meteo
                    sources[field] = "Open-Meteo"
                    day_updated = True
                else:
                    sources.setdefault(field, "QWeather")
            if sources:
                day["dryingMetricsSources"] = sources
            if day_updated:
                day["dryingMetricsUpdatedAt"] = fetched_at
                updated_days += 1
                city_updated = True
        if city_updated:
            record["dryingMetricsUpdatedAt"] = fetched_at
            updated_cities += 1
    return updated_cities, updated_days, errors


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
    # The dashboard compares today's minimum with the next six days and carries
    # recent forecast lows forward so ongoing cold streaks survive daily refreshes.
    today_date = now.date().isoformat()
    for record in records.values():
        if isinstance(record, dict):
            record.pop("previousForecast", None)
            preserve_low_temp_history(record, today_date)
            preserve_drying_history(record, today_date)
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
    forecast_updated_names: set[str] = set()
    hourly_forecast_supported: bool | None = None
    for city in daily_targets:
        record = records.setdefault(city["name"], {})
        try:
            previous_days = {day.get("date"): day for day in record.get("daily", []) if isinstance(day, dict)}
            if hourly_forecast_supported is not False:
                try:
                    refreshed_days = get_hourly_days(api, city, today_date)
                    hourly_forecast_supported = True
                except SystemExit as exc:
                    if "HTTP 403" not in str(exc):
                        raise
                    hourly_forecast_supported = False
                    print("Hourly Forecast API is not enabled for this credential; falling back to Daily Forecast.")
                    refreshed_days = get_daily(api, city)
            else:
                refreshed_days = get_daily(api, city)
            # Today's hourly forecast starts at the current hour. Preserve the
            # previous daily forecast's full-day high/low for existing charts.
            for day in refreshed_days:
                if day.get("date") == today_date and day["date"] in previous_days:
                    previous_day = previous_days[day["date"]]
                    for key in ("tempMax", "tempMin", "tempAvg"):
                        if previous_day.get(key) is not None:
                            day[key] = previous_day[key]
            record["daily"] = refreshed_days
            record["forecastUpdatedAt"] = datetime.now(TZ).isoformat(timespec="seconds")
            forecast_updated_names.add(city["name"])
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

    # Keep the regular daily forecast refresh at one call per city. In the
    # evening, spend the remaining free-plan headroom on up to 20 cities that
    # are currently raining, so the dryer-demand panel gets a fresher outlook.
    evening_rainy_forecast_success = 0
    if not morning and hourly_forecast_supported is not False:
        def currently_raining(city: dict[str, Any]) -> bool:
            current = (records.get(city["name"]) or {}).get("current") or {}
            text = str(current.get("text") or "")
            try:
                precip = float(current.get("precip") or 0)
            except (TypeError, ValueError):
                precip = 0
            return any(word in text for word in ("雨", "雷", "冰雹")) or precip > 0

        candidates = sorted(cities, key=lambda city: rain_rank(city["name"], records.get(city["name"], {})), reverse=True)
        for city in candidates:
            if evening_rainy_forecast_success >= EVENING_RAINY_FORECAST_REFRESHES:
                break
            if city["name"] in forecast_updated_names or not currently_raining(city):
                continue
            record = records.setdefault(city["name"], {})
            try:
                record["daily"] = get_hourly_days(api, city, today_date)
                record["forecastUpdatedAt"] = datetime.now(TZ).isoformat(timespec="seconds")
                hourly_forecast_supported = True
                forecast_updated_names.add(city["name"])
                evening_rainy_forecast_success += 1
            except BudgetExhausted:
                break
            except SystemExit as exc:
                if "HTTP 403" in str(exc):
                    hourly_forecast_supported = False
                    print("Hourly Forecast API is not enabled for this credential; skipping evening score refresh.")
                    break
                raise
            except Exception as exc:
                errors += 1
                print(f"Evening hourly forecast unavailable for {city['name']}: {exc}", file=sys.stderr)

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

    # QWeather's free tier does not provide the full 168-hour window needed by
    # the seven-day dryer model. Open-Meteo fills those score inputs without
    # replacing QWeather's current conditions or daily temperature forecasts.
    drying_supplement_cities, drying_supplement_days, open_meteo_errors = supplement_drying_metrics(cities, records)
    errors += len(open_meteo_errors)
    for message in open_meteo_errors:
        print(f"Open-Meteo drying supplement unavailable for {message}", file=sys.stderr)

    snapshot = {
        "source": "QWeather",
        "updatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "mode": "morning" if morning else "evening",
        "requestCountThisRun": api.calls,
        "requestDate": now.date().isoformat(),
        "requestsToday": int(prior_calls or 0) + api.calls,
        "cityCount": len(cities),
        "minutelyCityCountThisRun": minute_success,
        "eveningRainyForecastCityCountThisRun": evening_rainy_forecast_success,
        "hourlyForecastSupportedThisRun": hourly_forecast_supported,
        "dryingMetricsSource": "Open-Meteo supplement",
        "dryingSupplementCityCountThisRun": drying_supplement_cities,
        "dryingSupplementDayCountThisRun": drying_supplement_days,
        "dryingSupplementErrorsThisRun": len(open_meteo_errors),
        "errorsThisRun": errors,
        "attribution": "https://developer.qweather.com/attribution.html",
        "dryingMetricsAttribution": "https://open-meteo.com/",
        "cities": records,
    }
    DATA_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} city records; mode={snapshot['mode']}; requests={api.calls}; minute={minute_success}; evening_rainy_forecasts={evening_rainy_forecast_success}; hourly_supported={hourly_forecast_supported}; drying_supplement={drying_supplement_cities} cities/{drying_supplement_days} days; Open-Meteo_errors={len(open_meteo_errors)}; errors={errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
