"""The three scheduling strategies and the end-to-end comparison.

habit      the existing fixed schedule supplied in profiles.baseline_pump_on
timer      a fixed midday operating window with tank safeguards (no solar knowledge)
optimizer  forecast-aware dynamic programme (see optimizer.py)

All three schedules are evaluated by `simulate` against the SAME actual profiles.
"""

from typing import Literal

from .metrics import build_timeseries, compare, compute_metrics, is_eligible, is_sustainable
from .optimizer import OptimizerConfig, OptimizerResult, optimize_schedule
from .schemas import ScenarioRequest, ScenarioResponse, Strategies, StrategyResult
from .simulator import EPS, SimInputs, simulate

TIMER_WINDOW_START_MIN = 10 * 60  # 10:00
TIMER_WINDOW_END_MIN = 14 * 60  # 14:00 (exclusive)
NEAR_ZERO_SAVING_FRACTION = 0.01
NEAR_ZERO_SAVING_INR = 1.0


def inputs_from_request(req: ScenarioRequest, view: Literal["actual", "forecast"]) -> SimInputs:
    """Build simulation inputs. `forecast` uses forecast solar and forecast water demand;
    `actual` uses actual solar and actual water demand. Other load and tariffs are the same
    in both (assumed known to the planner)."""
    p = req.profiles
    solar = p.solar_actual_kw if view == "actual" else p.solar_forecast_kw
    demand = p.water_demand_actual_litres if view == "actual" else p.water_demand_forecast_litres
    step = req.interval_minutes
    return SimInputs(
        interval_minutes=step,
        solar_kw=tuple(solar),
        water_demand_litres=tuple(demand),
        other_load_kw=tuple(p.other_building_load_kw),
        import_tariff=tuple(p.import_tariff_per_slot),
        pump_power_kw=req.pump.power_kw,
        pump_flow_lph=req.pump.flow_litres_per_hour,
        min_run_slots=-(-req.pump.minimum_run_minutes // step),  # ceil
        max_starts=req.pump.max_starts_per_day,
        tank_min=req.tank.minimum_level_litres,
        tank_max=req.tank.maximum_level_litres,
        tank_initial=req.tank.initial_level_litres,
        sanctioned_load_kw=req.site.sanctioned_load_kw,
        export_policy=req.site.export_policy,
        export_tariff=req.site.export_tariff_per_kwh,
    )


def habit_schedule(req: ScenarioRequest) -> list[int]:
    return list(req.profiles.baseline_pump_on)


def timer_schedule(inp: SimInputs, window_start_min: int = TIMER_WINDOW_START_MIN,
                   window_end_min: int = TIMER_WINDOW_END_MIN) -> list[int]:
    """Fixed daily window with tank safeguards.

    Uses only forecast water demand (to track the tank level) and NO solar information.
    Rules, per interval:
      * a run in progress continues until the minimum runtime is met;
      * after that it continues while inside the window and the next interval would not
        overflow the tank (high-level cut-off), or while the tank is about to fall below
        the minimum level (low-level safeguard);
      * a new run starts inside the window if starts remain and pumping for one minimum
        run would not overflow the tank; or at any time if the tank is about to fall below
        the minimum level (emergency start).
    """
    n, step = inp.n_slots, inp.interval_minutes
    ws, we = window_start_min // step, window_end_min // step
    flow, R = inp.flow_per_slot, max(1, inp.min_run_slots)
    level, starts, run, prev_on = inp.tank_initial, 0, 0, False
    schedule = []

    def overflows_during_min_run(t, lvl):
        for k in range(R):
            if t + k >= n:
                break
            lvl += flow - inp.water_demand_litres[t + k]
            if lvl > inp.tank_max + EPS:
                return True
        return False

    for t in range(n):
        d = inp.water_demand_litres[t]
        in_window = ws <= t < we
        low = level - d < inp.tank_min - EPS
        if prev_on and run < R:
            on = True
        elif prev_on:
            on = (in_window and level + flow - d <= inp.tank_max + EPS) or low
        else:
            can_start = starts < inp.max_starts
            on = can_start and (low or (in_window and not overflows_during_min_run(t, level)))
        if on and not prev_on:
            starts += 1
            run = 1
        elif on:
            run += 1
        else:
            run = 0
        level += (flow if on else 0.0) - d
        level = min(max(level, 0.0), inp.tank_max)
        schedule.append(1 if on else 0)
        prev_on = on
    return schedule


def _fmt(x: float) -> str:
    return f"{x:,.1f}"


def run_comparison(req: ScenarioRequest, optimizer_config: OptimizerConfig | None = None) -> ScenarioResponse:
    """Run habit, timer and optimizer and evaluate all three against the ACTUAL profiles."""
    actual = inputs_from_request(req, "actual")
    forecast = inputs_from_request(req, "forecast")

    schedules = {"habit": habit_schedule(req), "timer": timer_schedule(forecast)}
    opt: OptimizerResult = optimize_schedule(forecast, optimizer_config)  # forecast ONLY
    schedules["optimizer"] = opt.schedule

    results, metrics = {}, {}
    for name in ("habit", "timer", "optimizer"):
        sim = simulate(schedules[name], actual)  # identical actual conditions for every strategy
        metrics[name] = compute_metrics(sim, actual)
        results[name] = StrategyResult(
            schedule_pump_on=schedules[name], metrics=metrics[name], timeseries=build_timeseries(sim)
        )

    comparison = compare(metrics, req.tank.initial_level_litres)
    return ScenarioResponse(
        scenario_id=req.scenario_id,
        data_mode=req.data_mode,
        strategies=Strategies(**results),
        comparison=comparison,
        assumptions=_assumptions(req, opt, metrics),
        warnings=_warnings(req, opt, metrics, comparison),
    )


def _assumptions(req: ScenarioRequest, opt: OptimizerResult, metrics) -> list[str]:
    step = req.interval_minutes
    a = []
    if req.data_mode == "simulated":
        a.append("All input profiles are SIMULATED (synthetic). They are not measurements and the "
                 "forecasts are not validated forecasts. Results are not evidence of real-world savings.")
    else:
        a.append("data_mode is 'measured': the profiles were supplied by the caller and their "
                 "provenance has not been verified by this backend.")
    a += [
        f"{step}-minute intervals, 96 per day. Power profiles are in kW; water demand is litres per "
        "interval (not litres per hour).",
        "The pump is assumed OFF before the first interval; pump starts are counted from that state.",
        "Tank balance per interval = previous level + delivered water - consumed water. Water above "
        "maximum_level_litres is counted as spilled; a shortfall below 0 L is counted as unmet demand.",
        "Optimizer: dynamic programme planned on FORECAST solar and FORECAST water demand only. "
        "Other building load and tariffs are treated as known. It does not see the actual profiles.",
        f"Optimizer planning settings: tank level bucket {opt.level_step_litres:.0f} L (approximate "
        f"optimality, see backend README), safety reserve {opt.reserve_litres:.0f} L above the minimum "
        f"level, end-of-day tank level >= {opt.terminal_level_litres:.0f} L.",
        f"Optimizer cost under the forecast was {opt.planned_cost_inr:.2f} INR; its cost evaluated "
        f"against actual conditions was {metrics['optimizer'].cost_inr:.2f} INR.",
        "Timer: pump window 10:00-14:00 with high-level cut-off and low-level emergency start, "
        "using forecast water demand only (no solar information).",
        "Habit: the schedule in profiles.baseline_pump_on, evaluated as given.",
        "All three strategies are evaluated against the same actual solar, water demand, other "
        "building load and tariffs.",
        "Cost = sum of grid import kWh x per-interval import tariff, minus export revenue. "
        "Demand charges, fixed charges, taxes and emissions are not modelled.",
        "Sanctioned load is applied to grid import in each interval (grid import above it is a "
        "power-limit violation).",
    ]
    if req.site.export_policy == "zero_export":
        a.append("Export policy zero_export: solar surplus that the building cannot use is curtailed "
                 "and earns nothing.")
    else:
        a.append(f"Export policy compensated_export: surplus solar is exported and paid at "
                 f"{req.site.export_tariff_per_kwh} INR/kWh.")
    a.append("Costs are not adjusted for differences in end-of-day tank level between strategies "
             "(see end_tank_level_litres). A strategy that ends the day with less water than it started "
             "with is excluded from the best-cost selection because it would run the tank down.")
    return a


def _warnings(req: ScenarioRequest, opt: OptimizerResult, metrics, comparison) -> list[str]:
    w = list(opt.notes)
    names = {"habit": "Habit", "timer": "Timer", "optimizer": "Optimizer"}
    for key, m in metrics.items():
        v, n = m.constraint_violations, names[key]
        if m.unmet_water_demand_litres > 0:
            w.append(f"{n}: {_fmt(m.unmet_water_demand_litres)} L of water demand went UNMET "
                     f"(tank minimum reached {_fmt(m.min_tank_level_litres)} L) against actual conditions.")
        if v.tank_below_minimum_slots:
            w.append(f"{n}: tank was below the minimum level in {v.tank_below_minimum_slots} intervals.")
        if m.spilled_water_litres > 0:
            w.append(f"{n}: {_fmt(m.spilled_water_litres)} L of water overflowed the tank.")
        if v.power_limit_slots:
            w.append(f"{n}: grid import exceeded the sanctioned load in {v.power_limit_slots} intervals "
                     f"(peak {m.peak_grid_import_kw:.1f} kW).")
        if v.minimum_runtime_violations:
            w.append(f"{n}: {v.minimum_runtime_violations} pump run(s) were shorter than the minimum runtime.")
        if v.excess_starts:
            w.append(f"{n}: {v.excess_starts} pump start(s) above the daily limit.")
        if not is_sustainable(m, req.tank.initial_level_litres):
            w.append(f"{n}: ends the day with {_fmt(m.end_tank_level_litres)} L in the tank, below the "
                     f"initial {_fmt(req.tank.initial_level_litres)} L. Repeated daily it would run the tank "
                     "down, so it is excluded from the best-cost selection.")

    if "NO strategy" in comparison.selection_note:
        w.append(comparison.selection_note)

    hab = metrics["habit"].cost_inr
    best = metrics[comparison.best_cost_strategy].cost_inr
    if hab > 0 and (hab - best) < max(NEAR_ZERO_SAVING_INR, NEAR_ZERO_SAVING_FRACTION * hab):
        w.append("The modelled cost difference between the existing habit and the best strategy is "
                 "negligible in this scenario: under these tariffs, export policy and actual solar "
                 "conditions, shifting pump operation produced little financial benefit.")

    if req.site.export_policy == "zero_export" and req.site.export_tariff_per_kwh > 0:
        w.append("export_tariff_per_kwh is ignored because export_policy is zero_export.")
    tariffs = set(req.profiles.import_tariff_per_slot)
    if tariffs != {req.site.import_tariff_per_kwh}:
        w.append("import_tariff_per_slot differs from site.import_tariff_per_kwh; the per-interval "
                 "profile is used for all cost calculations.")
    if req.site.export_policy == "compensated_export" and req.site.export_tariff_per_kwh > min(tariffs):
        w.append("export_tariff_per_kwh exceeds the lowest import tariff, which is unusual; check the inputs.")
    # surface strategy ranking facts that are not eligibility-related
    if not is_eligible(metrics["optimizer"], req.tank.initial_level_litres):
        w.append("The optimizer plan was feasible under the FORECAST but is not constraint-free "
                 "under actual conditions; do not treat it as safe.")
    return w
