"""Optimizer: constraints, forecast isolation, infeasibility, and exactness vs brute force."""
import itertools
import random

import pytest

from app.optimizer import InfeasibleScheduleError, OptimizerConfig, optimize_schedule
from app.simulator import SimInputs, count_starts, runs, simulate
from app.strategies import inputs_from_request
from tests.conftest import make_request


def tiny(seed, T=10):
    rng = random.Random(seed)
    policy = rng.choice(["zero_export", "compensated_export"])
    return SimInputs(
        interval_minutes=15,
        solar_kw=tuple(float(rng.choice([0, 0, 3, 8, 12, 14])) for _ in range(T)),
        water_demand_litres=tuple(float(rng.choice([0, 100, 300, 500, 700])) for _ in range(T)),
        other_load_kw=tuple(float(rng.randint(2, 8)) for _ in range(T)),
        import_tariff=tuple(float(rng.randint(5, 12)) for _ in range(T)),
        pump_power_kw=5.0, pump_flow_lph=4000.0,  # 1000 L per interval
        min_run_slots=rng.choice([1, 2, 3]), max_starts=rng.choice([1, 2, 3]),
        tank_min=1000.0, tank_max=6000.0, tank_initial=3000.0,
        sanctioned_load_kw=float(rng.choice([8, 10, 40])),
        export_policy=policy,
        export_tariff=float(rng.randint(0, 9)) if policy == "compensated_export" else 0.0,
    )


def brute_force(inp):
    """Independent exhaustive search; returns the minimum forecast cost or None."""
    T, R = inp.n_slots, max(1, inp.min_run_slots)
    flow, dt = inp.flow_per_slot, inp.dt_hours
    best = None
    for mask in itertools.product((0, 1), repeat=T):
        rs = runs(mask)
        if len(rs) > inp.max_starts or any(length < R for _, length in rs):
            continue
        level, cost, ok = inp.tank_initial, 0.0, True
        for t in range(T):
            on = mask[t]
            load = inp.other_load_kw[t] + (inp.pump_power_kw if on else 0.0)
            solar = inp.solar_kw[t]
            grid, surplus = max(0.0, load - solar), max(0.0, solar - load)
            if on and grid > inp.sanctioned_load_kw + 1e-9:
                ok = False
                break
            level += (flow if on else 0.0) - inp.water_demand_litres[t]
            if level < inp.tank_min - 1e-9 or level > inp.tank_max + 1e-9:
                ok = False
                break
            cost += grid * dt * inp.import_tariff[t]
            if inp.export_policy == "compensated_export":
                cost -= surplus * dt * inp.export_tariff
        if ok and level >= inp.tank_initial - 1e-9:
            best = cost if best is None else min(best, cost)
    return best


EXACT = OptimizerConfig(level_step_litres=1.0, reserve_fraction=0.0, terminal_at_least_initial=True)


@pytest.mark.parametrize("seed", range(40))
def test_dp_matches_brute_force_on_tiny_cases(seed):
    inp = tiny(seed)
    expected = brute_force(inp)
    if expected is None:
        # No schedule can end the day at the initial level. The optimizer must either refuse
        # or relax the end-of-day target AND say so; it may never return silently.
        try:
            res = optimize_schedule(inp, EXACT)
        except InfeasibleScheduleError:
            return
        assert any("end-of-day" in note for note in res.notes)
        return
    result = optimize_schedule(inp, EXACT)
    assert result.planned_cost_inr == pytest.approx(expected, abs=1e-6)
    # and the returned schedule really achieves that cost under the shared physics
    sim = simulate(result.schedule, inp)
    assert sim.import_cost_inr - sim.export_revenue_inr == pytest.approx(expected, abs=1e-6)
    assert sum(sim.spilled_litres) == 0 and sum(sim.unmet_litres) == 0


def test_enough_tiny_cases_are_feasible_to_be_meaningful():
    feasible = sum(1 for s in range(40) if brute_force(tiny(s)) is not None)
    assert feasible >= 20


@pytest.mark.parametrize("seed", range(40, 70))
def test_returned_schedule_always_satisfies_constraints_under_forecast(seed):
    inp = tiny(seed)
    cfg = OptimizerConfig(level_step_litres=50.0, reserve_fraction=0.0, terminal_at_least_initial=False)
    try:
        res = optimize_schedule(inp, cfg)
    except InfeasibleScheduleError:
        return
    s = res.schedule
    assert count_starts(s) <= inp.max_starts
    assert all(length >= inp.min_run_slots for _, length in runs(s))
    sim = simulate(s, inp)
    assert min(sim.level) >= inp.tank_min - 1e-6
    assert sum(sim.spilled_litres) == 0 and sum(sim.unmet_litres) == 0
    for t, on in enumerate(s):
        if on:
            assert sim.grid_import_kw[t] <= inp.sanctioned_load_kw + 1e-9


def test_demo_scenarios_are_planned_within_all_limits(weather):
    req = make_request(weather)
    fc = inputs_from_request(req, "forecast")
    res = optimize_schedule(fc)
    sim = simulate(res.schedule, fc)
    assert count_starts(res.schedule) <= req.pump.max_starts_per_day
    assert all(length >= fc.min_run_slots for _, length in runs(res.schedule))
    assert sum(sim.spilled_litres) == 0 and sum(sim.unmet_litres) == 0
    assert min(sim.level) >= fc.tank_min + res.reserve_litres - 1e-6
    assert sim.level[-1] >= fc.tank_initial - 1e-6
    assert not res.notes


def test_optimizer_output_depends_only_on_forecast_inputs():
    base = make_request("cloudy")
    sched = optimize_schedule(inputs_from_request(base, "forecast")).schedule

    # wildly different ACTUAL profiles must not change the plan
    wild = make_request("cloudy")
    wild.profiles.solar_actual_kw = [0.0] * 96
    wild.profiles.water_demand_actual_litres = [d * 1.4 for d in wild.profiles.water_demand_actual_litres]
    assert optimize_schedule(inputs_from_request(wild, "forecast")).schedule == sched

    # changing the FORECAST does change the plan
    other = make_request("cloudy")
    other.profiles.solar_forecast_kw = [0.0] * 96
    assert optimize_schedule(inputs_from_request(other, "forecast")).schedule != sched


def test_pump_is_not_scheduled_when_sanctioned_load_would_be_exceeded():
    # 58 kW base load + 5 kW pump: only allowed when forecast solar covers the excess
    req = make_request("clear", **{"profiles.other_building_load_kw": [58.0] * 96})
    fc = inputs_from_request(req, "forecast")
    res = optimize_schedule(fc)
    for t, on in enumerate(res.schedule):
        if on:
            assert fc.solar_kw[t] + 60.0 >= 58.0 + 5.0 - 1e-9
    assert sum(res.schedule) > 0


def test_infeasible_scenario_raises_with_details():
    # pump delivers 25 L per interval while the day's demand is ~7,500 L
    req = make_request("clear", **{"pump.flow_litres_per_hour": 100.0})
    with pytest.raises(InfeasibleScheduleError) as exc:
        optimize_schedule(inputs_from_request(req, "forecast"))
    assert exc.value.details


def test_infeasible_scenario_returns_clear_422_from_the_api(client):
    from tests.conftest import make_dict
    r = client.post("/api/v1/scenarios/run", json=make_dict(**{"pump.flow_litres_per_hour": 100.0}))
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "optimizer_infeasible" and detail["message"] and detail["details"]


def test_pump_blocked_by_sanctioned_load_is_infeasible_when_tank_must_be_refilled():
    req = make_request("clear", **{
        "profiles.other_building_load_kw": [58.0] * 96,
        "profiles.solar_forecast_kw": [0.0] * 96,
        "profiles.solar_actual_kw": [0.0] * 96,
    })
    with pytest.raises(InfeasibleScheduleError):
        optimize_schedule(inputs_from_request(req, "forecast"))


def test_relaxations_are_reported_not_hidden():
    n = 4
    inp = SimInputs(
        interval_minutes=15, solar_kw=(0.0,) * n, water_demand_litres=(20.0,) * n,
        other_load_kw=(58.0,) * n, import_tariff=(8.0,) * n, pump_power_kw=5.0, pump_flow_lph=4000.0,
        min_run_slots=1, max_starts=3, tank_min=2000.0, tank_max=5000.0, tank_initial=2100.0,
        sanctioned_load_kw=60.0, export_policy="zero_export", export_tariff=0.0,
    )  # pump can never run (63 kW > 60 kW) and the tank sits just above its minimum
    res = optimize_schedule(inp)
    assert sum(res.schedule) == 0
    joined = " ".join(res.notes)
    assert "reserve" in joined and "end-of-day" in joined
