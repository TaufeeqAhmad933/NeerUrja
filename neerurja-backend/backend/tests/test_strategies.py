"""Timer / habit strategies, fair evaluation and winner selection."""
import pytest

from app import strategies
from app.metrics import compare
from app.schemas import ConstraintViolations, Metrics
from app.simulator import count_starts, runs, simulate
from app.strategies import inputs_from_request, run_comparison, timer_schedule
from tests.conftest import make_request


def metrics(cost, *, unmet=0.0, selfc=50.0, end=6000.0, runtime=120.0, **viol):
    v = dict(tank_below_minimum_slots=0, tank_overflow_slots=0, power_limit_slots=0,
             minimum_runtime_violations=0, excess_starts=0)
    v.update(viol)
    v["total"] = sum(v.values())
    return Metrics(
        solar_generation_kwh=100, solar_self_consumption_kwh=selfc, solar_self_consumption_pct=selfc,
        self_sufficiency_pct=10, curtailed_solar_kwh=0, exported_solar_kwh=0, grid_import_kwh=1,
        pump_energy_kwh=1, import_cost_inr=cost, export_revenue_inr=0, cost_inr=cost,
        peak_grid_import_kw=1, min_tank_level_litres=3000, end_tank_level_litres=end,
        unmet_water_demand_litres=unmet, spilled_water_litres=0, pump_starts=1,
        pump_runtime_minutes=runtime, constraint_violations=ConstraintViolations(**v),
    )


# ----------------------------------------------------------- winner is computed, never fixed
def test_winner_is_whichever_eligible_strategy_is_cheapest():
    for cheapest in ("habit", "timer", "optimizer"):
        m = {k: metrics(200.0) for k in ("habit", "timer", "optimizer")}
        m[cheapest] = metrics(150.0)
        assert compare(m, 6000.0).best_cost_strategy == cheapest


def test_cheap_but_unsafe_strategy_does_not_win():
    m = {"habit": metrics(200.0), "timer": metrics(100.0, unmet=300.0), "optimizer": metrics(150.0)}
    c = compare(m, 6000.0)
    assert c.best_cost_strategy == "optimizer"
    assert c.cost_difference_inr == 50.0  # habit cost minus winner cost


def test_strategy_that_drains_the_tank_is_not_eligible():
    m = {"habit": metrics(200.0), "timer": metrics(100.0, end=4000.0), "optimizer": metrics(150.0)}
    assert compare(m, 6000.0).best_cost_strategy == "optimizer"


def test_if_nothing_qualifies_the_note_says_so():
    m = {k: metrics(c, unmet=10.0) for k, c in (("habit", 3.0), ("timer", 2.0), ("optimizer", 1.0))}
    c = compare(m, 6000.0)
    assert c.best_cost_strategy == "optimizer" and "NO strategy" in c.selection_note


def test_cost_ties_break_on_solar_self_consumption_and_are_disclosed():
    m = {"habit": metrics(100.0, selfc=40.0), "timer": metrics(100.0, selfc=55.0),
         "optimizer": metrics(100.0, selfc=50.0)}
    c = compare(m, 6000.0)
    assert c.best_cost_strategy == "timer" and "tied" in c.selection_note
    assert c.cost_difference_inr == 0.0


def test_savings_come_from_the_model_not_a_constant():
    base = run_comparison(make_request("clear"))
    doubled = make_request("clear")
    doubled.site.import_tariff_per_kwh = 16.0
    doubled.profiles.import_tariff_per_slot = [16.0] * 96
    twice = run_comparison(doubled)
    assert base.comparison.cost_difference_inr > 0
    assert twice.comparison.cost_difference_inr == pytest.approx(2 * base.comparison.cost_difference_inr, abs=0.02)
    assert twice.strategies.habit.metrics.cost_inr == pytest.approx(2 * base.strategies.habit.metrics.cost_inr, abs=0.02)


def test_when_habit_already_equals_the_plan_there_is_no_saving():
    req = make_request("clear")
    req.profiles.solar_forecast_kw = list(req.profiles.solar_actual_kw)
    req.profiles.water_demand_forecast_litres = list(req.profiles.water_demand_actual_litres)
    plan = run_comparison(req).strategies.optimizer.schedule_pump_on
    req.profiles.baseline_pump_on = plan
    out = run_comparison(req)
    assert out.strategies.habit.metrics.cost_inr == out.strategies.optimizer.metrics.cost_inr
    assert out.comparison.cost_difference_inr == 0.0
    assert any("negligible" in w for w in out.warnings)


# --------------------------------------------------------------- fair evaluation
def test_all_strategies_are_evaluated_on_identical_actual_profiles(monkeypatch):
    calls = []
    real = strategies.simulate
    monkeypatch.setattr(strategies, "simulate", lambda sched, inp: (calls.append((tuple(sched), inp)), real(sched, inp))[1])
    req = make_request("cloudy")
    out = run_comparison(req)
    assert len(calls) == 3
    first = calls[0][1]
    assert all(inp == first for _, inp in calls)
    assert first.solar_kw == tuple(req.profiles.solar_actual_kw)
    assert first.water_demand_litres == tuple(req.profiles.water_demand_actual_litres)
    assert first.other_load_kw == tuple(req.profiles.other_building_load_kw)
    assert first.import_tariff == tuple(req.profiles.import_tariff_per_slot)
    # the schedules evaluated are the ones returned
    assert [c[0] for c in calls] == [tuple(out.strategies.habit.schedule_pump_on),
                                     tuple(out.strategies.timer.schedule_pump_on),
                                     tuple(out.strategies.optimizer.schedule_pump_on)]
    # every strategy reports the same solar generation (same actual profile)
    gens = {getattr(out.strategies, k).metrics.solar_generation_kwh for k in ("habit", "timer", "optimizer")}
    assert len(gens) == 1


def test_optimizer_is_given_forecast_inputs_only(monkeypatch):
    seen = []
    real = strategies.optimize_schedule
    monkeypatch.setattr(strategies, "optimize_schedule", lambda inp, cfg=None: (seen.append(inp), real(inp, cfg))[1])
    req = make_request("cloudy")
    run_comparison(req)
    (inp,) = seen
    assert inp.solar_kw == tuple(req.profiles.solar_forecast_kw)
    assert inp.water_demand_litres == tuple(req.profiles.water_demand_forecast_litres)
    assert inp.solar_kw != tuple(req.profiles.solar_actual_kw)
    assert inp.water_demand_litres != tuple(req.profiles.water_demand_actual_litres)


def _with_actual_demand_scaled(factor):
    req = make_request("clear")
    req.profiles.water_demand_actual_litres = [d * factor for d in req.profiles.water_demand_actual_litres]
    return run_comparison(req)


def test_forecast_error_below_minimum_level_is_reported_not_hidden():
    # Actual demand 60 % above forecast: feasible under the forecast, but the tank dips below
    # its configured minimum against actual conditions. That must be visible.
    out = _with_actual_demand_scaled(1.6)
    m = out.strategies.optimizer.metrics
    assert m.min_tank_level_litres < 2000 and m.constraint_violations.tank_below_minimum_slots > 0
    assert any(w.startswith("Optimizer:") and "below the minimum level" in w for w in out.warnings)
    assert any("do not treat it as safe" in w for w in out.warnings)


def test_forecast_error_causing_unmet_demand_is_reported_not_hidden():
    out = _with_actual_demand_scaled(3.0)
    m = out.strategies.optimizer.metrics
    assert m.unmet_water_demand_litres > 0 and m.min_tank_level_litres == 0
    assert any(w.startswith("Optimizer:") and "UNMET" in w for w in out.warnings)
    assert out.strategies.optimizer.timeseries.tank_level_litres[-1] <= m.end_tank_level_litres + 0.1


def test_power_limit_violations_are_reported_for_habit_but_not_planned_by_optimizer():
    req = make_request("clear", **{"profiles.other_building_load_kw": [58.0] * 96})
    out = run_comparison(req)
    assert out.strategies.habit.metrics.constraint_violations.power_limit_slots > 0
    assert out.strategies.optimizer.metrics.constraint_violations.power_limit_slots == 0
    assert any(w.startswith("Habit:") and "sanctioned load" in w for w in out.warnings)


def test_habit_minimum_runtime_and_start_violations_are_reported():
    req = make_request("clear")
    req.profiles.baseline_pump_on = [1 if i % 8 == 0 else 0 for i in range(96)]  # twelve 15-minute runs
    out = run_comparison(req)
    v = out.strategies.habit.metrics.constraint_violations
    assert out.strategies.habit.metrics.pump_starts == 12
    assert v.minimum_runtime_violations == 12 and v.excess_starts == 9
    ov = out.strategies.optimizer.metrics
    assert ov.pump_starts <= 3 and ov.constraint_violations.minimum_runtime_violations == 0


# -------------------------------------------------------------------------- timer
def test_timer_respects_runtime_starts_and_never_uses_solar_data():
    req = make_request("clear")
    fc = inputs_from_request(req, "forecast")
    sched = timer_schedule(fc)
    assert count_starts(sched) <= req.pump.max_starts_per_day
    assert all(length >= fc.min_run_slots for _, length in runs(sched))
    assert sum(simulate(sched, fc).spilled_litres) == 0
    # in the 10:00-14:00 window
    assert all(40 <= i < 56 for i, on in enumerate(sched) if on)
    other = make_request("clear", **{"profiles.solar_forecast_kw": [0.0] * 96})
    assert timer_schedule(inputs_from_request(other, "forecast")) == sched


def test_timer_low_level_safeguard_starts_pump_outside_the_window():
    req = make_request("clear", **{"tank.initial_level_litres": 2100.0})
    sched = timer_schedule(inputs_from_request(req, "forecast"))
    assert any(sched[:40])


def test_timer_does_not_overflow_a_nearly_full_tank():
    req = make_request("clear", **{"tank.initial_level_litres": 10000.0})
    fc = inputs_from_request(req, "forecast")
    assert sum(simulate(timer_schedule(fc), fc).spilled_litres) == 0
