"""Metrics and strategy comparison, computed from simulation results only.

Nothing here is hardcoded: every number comes from a `SimResult`, and the
"best" strategy is selected by comparing the computed metrics.
"""

from .schemas import Comparison, ConstraintViolations, Metrics, Timeseries
from .simulator import EPS, SimInputs, SimResult, count_min_run_violations, count_starts

TIE_TOLERANCE_INR = 0.005


def _r(x: float, nd: int = 3) -> float:
    return round(x + 0.0, nd)  # "+ 0.0" normalises -0.0


def compute_metrics(sim: SimResult, inp: SimInputs) -> Metrics:
    dt = inp.dt_hours
    n = inp.n_slots
    solar_kwh = sum(inp.solar_kw) * dt
    used_kwh = sum(sim.solar_used_kw) * dt
    load_kwh = sum(sim.load_kw) * dt
    grid_kwh = sum(sim.grid_import_kw) * dt
    starts = count_starts(sim.pump_on)

    violations = ConstraintViolations(
        tank_below_minimum_slots=sum(1 for lv in sim.level if lv < inp.tank_min - EPS),
        tank_overflow_slots=sum(1 for s in sim.spilled_litres if s > EPS),
        power_limit_slots=sum(1 for g in sim.grid_import_kw if g > inp.sanctioned_load_kw + EPS),
        minimum_runtime_violations=count_min_run_violations(sim.pump_on, inp.min_run_slots),
        excess_starts=max(0, starts - inp.max_starts),
        total=0,
    )
    violations.total = (
        violations.tank_below_minimum_slots + violations.tank_overflow_slots
        + violations.power_limit_slots + violations.minimum_runtime_violations
        + violations.excess_starts
    )

    return Metrics(
        solar_generation_kwh=_r(solar_kwh),
        solar_self_consumption_kwh=_r(used_kwh),
        solar_self_consumption_pct=_r(100.0 * used_kwh / solar_kwh if solar_kwh > 0 else 0.0, 2),
        self_sufficiency_pct=_r(100.0 * used_kwh / load_kwh if load_kwh > 0 else 0.0, 2),
        curtailed_solar_kwh=_r(sum(sim.curtailed_kw) * dt),
        exported_solar_kwh=_r(sum(sim.exported_kw) * dt),
        grid_import_kwh=_r(grid_kwh),
        pump_energy_kwh=_r(sum(sim.pump_kw) * dt),
        import_cost_inr=_r(sim.import_cost_inr, 2),
        export_revenue_inr=_r(sim.export_revenue_inr, 2),
        cost_inr=_r(sim.import_cost_inr - sim.export_revenue_inr, 2),
        peak_grid_import_kw=_r(max(sim.grid_import_kw) if n else 0.0),
        min_tank_level_litres=_r(min(sim.level) if n else inp.tank_initial, 1),
        end_tank_level_litres=_r(sim.level[-1] if n else inp.tank_initial, 1),
        unmet_water_demand_litres=_r(sum(sim.unmet_litres), 1),
        spilled_water_litres=_r(sum(sim.spilled_litres), 1),
        pump_starts=starts,
        pump_runtime_minutes=_r(sum(sim.pump_on) * inp.interval_minutes, 1),
        constraint_violations=violations,
    )


def build_timeseries(sim: SimResult) -> Timeseries:
    return Timeseries(
        tank_level_litres=[_r(x, 1) for x in sim.level],
        grid_import_kw=[_r(x) for x in sim.grid_import_kw],
        solar_used_kw=[_r(x) for x in sim.solar_used_kw],
        curtailed_solar_kw=[_r(x) for x in sim.curtailed_kw],
        exported_solar_kw=[_r(x) for x in sim.exported_kw],
    )


SUSTAINABILITY_TOLERANCE_LITRES = 1.0


def is_sustainable(m: Metrics, tank_initial_litres: float) -> bool:
    """The day ends with at least as much water in the tank as it started with.

    A schedule that pumps less than the day's demand looks cheaper only because it drains
    the tank; repeated day after day it would run dry.
    """
    return m.end_tank_level_litres + SUSTAINABILITY_TOLERANCE_LITRES >= tank_initial_litres


def is_eligible(m: Metrics, tank_initial_litres: float) -> bool:
    """Meets every operating constraint and is sustainable over repeated days.
    Spilled water is reported but does not disqualify."""
    v = m.constraint_violations
    return (
        is_sustainable(m, tank_initial_litres)
        and m.unmet_water_demand_litres <= 0
        and v.tank_below_minimum_slots == 0
        and v.power_limit_slots == 0
        and v.minimum_runtime_violations == 0
        and v.excess_starts == 0
    )


def compare(metrics: dict[str, Metrics], tank_initial_litres: float) -> Comparison:
    """Pick the lowest-cost strategy among those that meet all constraints and are sustainable
    (end the day with at least the initial tank level).

    If none meets them all, the lowest-cost strategy overall is returned and the
    note says so. Ties (within 0.005 INR) go to higher solar self-consumption,
    then shorter runtime, then name order (deterministic).
    """
    eligible = [k for k, m in metrics.items() if is_eligible(m, tank_initial_litres)]
    pool = eligible or list(metrics)

    def rank(k):
        m = metrics[k]
        return (round(m.cost_inr / TIE_TOLERANCE_INR), -m.solar_self_consumption_kwh,
                m.pump_runtime_minutes, k)

    best = min(pool, key=rank)
    if eligible:
        note = (
            "Lowest modelled cost among strategies that meet all constraints against actual conditions "
            "and end the day with at least the initial tank level "
            f"({', '.join(sorted(eligible))} qualified)."
        )
    else:
        note = (
            "NO strategy met all constraints against actual conditions; the lowest-cost strategy is "
            "shown but should not be treated as safe."
        )
    tied = [k for k in pool if k != best and abs(metrics[k].cost_inr - metrics[best].cost_inr) <= TIE_TOLERANCE_INR]
    if tied:
        note += (f" Cost is tied with {', '.join(sorted(tied))} (within {TIE_TOLERANCE_INR} INR); the tie was "
                 "broken by higher solar self-consumption, then shorter runtime.")
    habit = metrics["habit"]
    return Comparison(
        best_cost_strategy=best,
        cost_difference_inr=_r(habit.cost_inr - metrics[best].cost_inr, 2),
        solar_self_consumption_change_percentage_points=_r(
            metrics["optimizer"].solar_self_consumption_pct - habit.solar_self_consumption_pct, 2
        ),
        selection_note=note,
    )
