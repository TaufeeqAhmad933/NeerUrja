"""Pydantic models for the NeerUrja API (request, response, metrics).

Units used everywhere:
  * power profiles ........ kW (average power during the interval)
  * water demand .......... litres PER INTERVAL (not litres per hour)
  * tank levels ........... litres
  * money ................. INR
Every profile has exactly 96 entries (24 h at 15-minute intervals).
"""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

INTERVALS_PER_DAY = 96
INTERVAL_MINUTES = 15
# PV output cannot sensibly exceed the DC nameplate by much; used as a sanity bound.
MAX_SOLAR_TO_KWP_RATIO = 1.25

ExportPolicy = Literal["zero_export", "compensated_export"]
StrategyName = Literal["habit", "timer", "optimizer"]


class _Strict(BaseModel):
    """Unknown fields are rejected so a misspelled field never gets silently ignored."""

    model_config = ConfigDict(extra="forbid")


def _finite(**kw):
    return Field(allow_inf_nan=False, **kw)


# --------------------------------------------------------------------------- request
class Site(_Strict):
    solar_capacity_kwp: float = _finite(gt=0, le=10_000)
    sanctioned_load_kw: float = _finite(gt=0, le=100_000)
    export_policy: ExportPolicy
    import_tariff_per_kwh: float = _finite(ge=0, le=1_000)
    export_tariff_per_kwh: float = _finite(ge=0, le=1_000)


class Pump(_Strict):
    power_kw: float = _finite(gt=0, le=1_000)
    flow_litres_per_hour: float = _finite(gt=0, le=1_000_000)
    minimum_run_minutes: int = Field(ge=0, le=1_440)
    max_starts_per_day: int = Field(ge=1, le=INTERVALS_PER_DAY)


class Tank(_Strict):
    capacity_litres: float = _finite(gt=0, le=10_000_000)
    initial_level_litres: float = _finite(ge=0)
    minimum_level_litres: float = _finite(ge=0)
    maximum_level_litres: float = _finite(gt=0)

    @model_validator(mode="after")
    def _check_levels(self):
        if not self.minimum_level_litres <= self.maximum_level_litres:
            raise ValueError("minimum_level_litres must be <= maximum_level_litres")
        if self.maximum_level_litres > self.capacity_litres:
            raise ValueError("maximum_level_litres must be <= capacity_litres")
        if not self.minimum_level_litres <= self.initial_level_litres <= self.maximum_level_litres:
            raise ValueError(
                "initial_level_litres must lie between minimum_level_litres and maximum_level_litres"
            )
        return self


_FLOAT_PROFILES = (
    "solar_forecast_kw",
    "solar_actual_kw",
    "water_demand_forecast_litres",
    "water_demand_actual_litres",
    "other_building_load_kw",
    "import_tariff_per_slot",
)


class Profiles(_Strict):
    solar_forecast_kw: list[float]
    solar_actual_kw: list[float]
    water_demand_forecast_litres: list[float]
    water_demand_actual_litres: list[float]
    other_building_load_kw: list[float]
    baseline_pump_on: list[int]
    import_tariff_per_slot: list[float]

    @field_validator("baseline_pump_on", mode="before")
    @classmethod
    def _bools_to_ints(cls, v):
        if isinstance(v, list):
            return [int(x) if isinstance(x, bool) else x for x in v]
        return v

    @field_validator(*_FLOAT_PROFILES, "baseline_pump_on", mode="after")
    @classmethod
    def _check_profile(cls, v, info):
        name = info.field_name
        if len(v) != INTERVALS_PER_DAY:
            raise ValueError(f"{name} must contain exactly {INTERVALS_PER_DAY} entries, got {len(v)}")
        for i, x in enumerate(v):
            if isinstance(x, float) and not math.isfinite(x):
                raise ValueError(f"{name}[{i}] is not a finite number")
            if x < 0:
                raise ValueError(f"{name}[{i}] must be >= 0, got {x}")
            if name == "baseline_pump_on" and x not in (0, 1):
                raise ValueError(f"baseline_pump_on[{i}] must be 0 or 1, got {x}")
            if name == "import_tariff_per_slot" and x > 1_000:
                raise ValueError(f"import_tariff_per_slot[{i}] is implausibly large ({x})")
        return v


class ScenarioRequest(_Strict):
    scenario_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    data_mode: Literal["simulated", "measured"]
    interval_minutes: Literal[15]
    site: Site
    pump: Pump
    tank: Tank
    profiles: Profiles

    @model_validator(mode="after")
    def _cross_checks(self):
        limit = self.site.solar_capacity_kwp * MAX_SOLAR_TO_KWP_RATIO
        for name in ("solar_forecast_kw", "solar_actual_kw"):
            for i, x in enumerate(getattr(self.profiles, name)):
                if x > limit:
                    raise ValueError(
                        f"{name}[{i}]={x} kW exceeds {MAX_SOLAR_TO_KWP_RATIO}x solar_capacity_kwp "
                        f"({limit:.1f} kW); check units (profiles are kW, not W or kWh)"
                    )
        return self


# -------------------------------------------------------------------------- response
class ConstraintViolations(BaseModel):
    """Counts of intervals/events (evaluated against ACTUAL conditions)."""

    tank_below_minimum_slots: int
    tank_overflow_slots: int
    power_limit_slots: int
    minimum_runtime_violations: int
    excess_starts: int
    total: int


class Metrics(BaseModel):
    solar_generation_kwh: float
    solar_self_consumption_kwh: float
    solar_self_consumption_pct: float
    self_sufficiency_pct: float
    curtailed_solar_kwh: float
    exported_solar_kwh: float
    grid_import_kwh: float
    pump_energy_kwh: float
    import_cost_inr: float
    export_revenue_inr: float
    cost_inr: float
    peak_grid_import_kw: float
    min_tank_level_litres: float
    end_tank_level_litres: float
    unmet_water_demand_litres: float
    spilled_water_litres: float
    pump_starts: int
    pump_runtime_minutes: float
    constraint_violations: ConstraintViolations


class Timeseries(BaseModel):
    """Per-interval results (96 entries each) from the evaluation against actual conditions."""

    tank_level_litres: list[float]  # end-of-interval level
    grid_import_kw: list[float]
    solar_used_kw: list[float]
    curtailed_solar_kw: list[float]
    exported_solar_kw: list[float]


class StrategyResult(BaseModel):
    schedule_pump_on: list[int]
    metrics: Metrics
    timeseries: Timeseries


class Strategies(BaseModel):
    habit: StrategyResult
    timer: StrategyResult
    optimizer: StrategyResult


class Comparison(BaseModel):
    best_cost_strategy: StrategyName
    cost_difference_inr: float
    solar_self_consumption_change_percentage_points: float
    selection_note: str


class ScenarioResponse(BaseModel):
    scenario_id: str
    data_mode: Literal["simulated", "measured"]
    strategies: Strategies
    comparison: Comparison
    assumptions: list[str]
    warnings: list[str]
