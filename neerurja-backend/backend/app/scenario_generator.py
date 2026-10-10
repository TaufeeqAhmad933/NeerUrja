"""Synthetic (SIMULATED) scenario generator for the demo.

Every profile produced here is synthetic. None of it is a measurement or a
validated forecast. Forecast and actual profiles are generated separately, and
the forecast deliberately differs from actual (more on the cloudy day), so the
optimizer is never handed perfect knowledge of the future.

Deterministic: fixed seeds, values rounded to 3 decimals.
"""

import math
import random

from .schemas import INTERVAL_MINUTES, INTERVALS_PER_DAY

N = INTERVALS_PER_DAY
DT_H = INTERVAL_MINUTES / 60.0

PERFORMANCE_RATIO = 0.82  # synthetic: DC nameplate -> AC output at clear-sky noon
SUNRISE_H, SUNSET_H = 6.25, 18.5
DAILY_WATER_DEMAND_LITRES = 7_500.0  # synthetic hostel-scale demand
FLAT_IMPORT_TARIFF = 8.0  # INR/kWh, synthetic flat tariff

SEEDS = {"clear": 2611, "cloudy": 2623}

SITE_DEFAULTS = dict(solar_capacity_kwp=50, sanctioned_load_kw=60)
PUMP_DEFAULTS = dict(power_kw=5, flow_litres_per_hour=4000, minimum_run_minutes=45, max_starts_per_day=3)
TANK_DEFAULTS = dict(capacity_litres=10000, initial_level_litres=6000,
                     minimum_level_litres=2000, maximum_level_litres=10000)

# Synthetic "existing habit": the pump runs in two fixed blocks, early morning and evening,
# when there is little or no sun.  Slots are 15 minutes: 05:00-06:00 and 18:00-19:00.
HABIT_RUNS = ((20, 24), (72, 76))


def _hour(i: int) -> float:
    return (i + 0.5) * DT_H


def _bump(h: float, centre: float, sigma: float) -> float:
    return math.exp(-0.5 * ((h - centre) / sigma) ** 2)


def clear_sky_fraction(h: float) -> float:
    if h <= SUNRISE_H or h >= SUNSET_H:
        return 0.0
    return math.sin(math.pi * (h - SUNRISE_H) / (SUNSET_H - SUNRISE_H)) ** 1.25


def water_demand_pattern() -> list[float]:
    """Morning + small midday + evening peaks, scaled to DAILY_WATER_DEMAND_LITRES."""
    raw = []
    for i in range(N):
        h = _hour(i)
        raw.append(12 + 210 * _bump(h, 7.0, 1.0) + 70 * _bump(h, 13.0, 1.5) + 260 * _bump(h, 19.5, 1.25))
    scale = DAILY_WATER_DEMAND_LITRES / sum(raw)
    return [x * scale for x in raw]


def other_load_profile() -> list[float]:
    out = []
    for i in range(N):
        h = _hour(i)
        out.append(8.0 + 10.0 * _bump(h, 13.0, 3.5) + 5.0 * _bump(h, 20.0, 1.5))
    return out


def habit_schedule() -> list[int]:
    sched = [0] * N
    for a, b in HABIT_RUNS:
        for i in range(a, b):
            sched[i] = 1
    return sched


def _solar(weather: str, capacity_kwp: float, rng: random.Random):
    """Return (forecast_kw, actual_kw) lists."""
    peak = capacity_kwp * PERFORMANCE_RATIO
    clear = [peak * clear_sky_fraction(_hour(i)) for i in range(N)]
    if weather == "clear":
        forecast = [c * 1.0 for c in clear]
        actual = [c * min(1.03, max(0.93, 0.98 + rng.gauss(0, 0.02))) for c in clear]
    elif weather == "cloudy":
        # The forecast expects mostly-cloudy skies (about 65 % of clear sky) ...
        forecast = [c * 0.65 for c in clear]
        # ... but the actual day has a deep cloud bank around midday and short breaks.
        actual = []
        for i, c in enumerate(clear):
            h = _hour(i)
            f = 0.80 - 0.50 * _bump(h, 12.6, 1.3) - 0.20 * _bump(h, 9.5, 0.6) + rng.gauss(0, 0.04)
            actual.append(c * min(1.0, max(0.08, f)))
    else:
        raise ValueError(f"unknown weather {weather!r}")
    return forecast, actual


def _round(xs, nd=3):
    return [round(x, nd) + 0.0 for x in xs]


def generate_scenario(weather: str, *, export_policy: str = "zero_export",
                      export_tariff: float = 0.0, scenario_id: str | None = None) -> dict:
    """Build one request-shaped dict (validates against schemas.ScenarioRequest)."""
    if weather not in SEEDS:
        raise ValueError(f"weather must be one of {sorted(SEEDS)}")
    rng = random.Random(SEEDS[weather])
    forecast_solar, actual_solar = _solar(weather, SITE_DEFAULTS["solar_capacity_kwp"], rng)

    demand_forecast = water_demand_pattern()
    # Actual demand: slightly higher than forecast overall, with interval-level noise.
    demand_actual = [d * 1.03 * min(1.15, max(0.85, 1 + rng.gauss(0, 0.06))) for d in demand_forecast]

    return {
        "scenario_id": scenario_id or f"campus-demo-01-{weather}",
        "data_mode": "simulated",
        "interval_minutes": INTERVAL_MINUTES,
        "site": {
            **SITE_DEFAULTS,
            "export_policy": export_policy,
            "import_tariff_per_kwh": FLAT_IMPORT_TARIFF,
            "export_tariff_per_kwh": export_tariff,
        },
        "pump": dict(PUMP_DEFAULTS),
        "tank": dict(TANK_DEFAULTS),
        "profiles": {
            "solar_forecast_kw": _round(forecast_solar),
            "solar_actual_kw": _round(actual_solar),
            "water_demand_forecast_litres": _round(demand_forecast),
            "water_demand_actual_litres": _round(demand_actual),
            "other_building_load_kw": _round(other_load_profile()),
            "baseline_pump_on": habit_schedule(),
            "import_tariff_per_slot": [FLAT_IMPORT_TARIFF] * N,
        },
    }


def generate_demo_file() -> dict:
    return {
        "schema_version": 1,
        "description": (
            "SIMULATED demo scenarios for NeerUrja. Every profile is synthetic: not a measurement and "
            "not a validated forecast. Generated by scripts/generate_demo_data.py."
        ),
        "scenarios": {w: generate_scenario(w) for w in ("clear", "cloudy")},
    }
