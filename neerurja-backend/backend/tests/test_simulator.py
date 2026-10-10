import pytest

from app.metrics import compute_metrics
from app.simulator import (SimInputs, count_min_run_violations, count_starts, power_flows, runs,
                           simulate, slot_money, tank_step)


def inputs(n=4, solar=0.0, other=0.0, demand=0.0, tariff=10.0, **kw):
    base = dict(
        interval_minutes=15, solar_kw=(solar,) * n, water_demand_litres=(demand,) * n,
        other_load_kw=(other,) * n, import_tariff=(tariff,) * n, pump_power_kw=5.0,
        pump_flow_lph=4000.0, min_run_slots=1, max_starts=10, tank_min=100.0, tank_max=1000.0,
        tank_initial=500.0, sanctioned_load_kw=60.0, export_policy="zero_export", export_tariff=0.0,
    )
    base.update(kw)
    return SimInputs(**base)


def test_pump_power_is_added_to_other_load():
    pump, load, used, grid, surplus = power_flows(solar_kw=3.0, other_kw=10.0, pump_on=1, pump_power_kw=5.0)
    assert (pump, load, used, grid, surplus) == (5.0, 15.0, 3.0, 12.0, 0.0)
    pump, load, used, grid, surplus = power_flows(solar_kw=30.0, other_kw=10.0, pump_on=0, pump_power_kw=5.0)
    assert (pump, load, used, grid, surplus) == (0.0, 10.0, 10.0, 0.0, 20.0)


def test_water_delivery_uses_flow_times_interval_hours():
    assert inputs().flow_per_slot == 1000.0  # 4000 L/h x 0.25 h


def test_overflow_is_spilled_and_reported():
    inp = inputs(n=2, tank_initial=900.0, demand=0.0)
    sim = simulate([1, 1], inp)
    assert sim.level == [1000.0, 1000.0]
    assert sim.spilled_litres == [900.0, 1000.0]
    m = compute_metrics(sim, inp)
    assert m.spilled_water_litres == 1900.0
    assert m.constraint_violations.tank_overflow_slots == 2


def test_shortage_is_unmet_demand_and_level_never_negative():
    inp = inputs(n=2, tank_initial=100.0, demand=500.0)
    sim = simulate([0, 0], inp)
    assert sim.level == [0.0, 0.0]
    assert sim.unmet_litres == [400.0, 500.0]
    m = compute_metrics(sim, inp)
    assert m.unmet_water_demand_litres == 900.0
    assert m.min_tank_level_litres == 0.0
    assert m.constraint_violations.tank_below_minimum_slots == 2


def test_tank_balance_with_delivery_and_consumption():
    level, spilled, unmet = tank_step(500.0, 1000.0, 300.0, 2000.0)
    assert (level, spilled, unmet) == (1200.0, 0.0, 0.0)


def test_sanctioned_load_violation_counts_grid_import_only():
    # 58 kW building load + 5 kW pump with no sun = 63 kW import > 60 kW
    inp = inputs(n=4, other=58.0)
    m = compute_metrics(simulate([0, 1, 1, 0], inp), inp)
    assert m.constraint_violations.power_limit_slots == 2
    assert m.peak_grid_import_kw == 63.0
    # the same pump load is fine once solar covers the excess (limit applies to grid import)
    inp = inputs(n=4, other=58.0, solar=10.0)
    m = compute_metrics(simulate([0, 1, 1, 0], inp), inp)
    assert m.constraint_violations.power_limit_slots == 0
    assert m.peak_grid_import_kw == 53.0


def test_zero_export_curtails_and_compensated_export_pays():
    inp = inputs(n=1, solar=20.0, other=5.0)
    m = compute_metrics(simulate([0], inp), inp)
    assert m.curtailed_solar_kwh == 3.75 and m.exported_solar_kwh == 0 and m.cost_inr == 0
    inp = inputs(n=1, solar=20.0, other=5.0, export_policy="compensated_export", export_tariff=4.0)
    m = compute_metrics(simulate([0], inp), inp)
    assert m.curtailed_solar_kwh == 0 and m.exported_solar_kwh == 3.75
    assert m.export_revenue_inr == 15.0 and m.cost_inr == -15.0


def test_slot_money():
    assert slot_money(10.0, 0.0, 8.0, "zero_export", 0.0, 0.25) == (20.0, 0.0, 0.0, 0.0)


def test_minimum_runtime_and_start_counting():
    s = [0, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1]
    assert runs(s) == [(1, 1), (3, 2), (6, 3), (10, 1)]
    assert count_starts(s) == 4
    # the final run (still on at the end of the day) is not counted as short
    assert count_min_run_violations(s, 3) == 2
    inp = inputs(n=len(s), max_starts=3, min_run_slots=3)
    m = compute_metrics(simulate(s, inp), inp)
    assert m.pump_starts == 4
    assert m.constraint_violations.excess_starts == 1
    assert m.constraint_violations.minimum_runtime_violations == 2
    assert m.pump_runtime_minutes == 7 * 15


def test_simulate_rejects_bad_schedules():
    with pytest.raises(ValueError):
        simulate([0, 1], inputs(n=4))
    with pytest.raises(ValueError):
        simulate([0, 2, 0, 0], inputs(n=4))
