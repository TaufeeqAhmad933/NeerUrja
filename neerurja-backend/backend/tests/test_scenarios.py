"""Clear-day / cloudy-day scenarios and the export-policy cases."""
import json
from pathlib import Path

import pytest

from app.scenario_generator import generate_demo_file, generate_scenario
from app.schemas import ScenarioRequest
from app.strategies import run_comparison
from tests.conftest import make_request

DEMO_FILE = Path(__file__).resolve().parents[2] / "data" / "demo_scenario.json"
KEYS = ("habit", "timer", "optimizer")


def test_generated_profiles_are_valid_96_entry_simulated_scenarios(weather):
    d = generate_scenario(weather)
    req = ScenarioRequest.model_validate(d)
    assert req.data_mode == "simulated"
    assert all(len(getattr(req.profiles, f)) == 96 for f in type(req.profiles).model_fields)


def test_forecast_and_actual_profiles_are_genuinely_different(weather):
    p = make_request(weather).profiles
    assert p.solar_forecast_kw != p.solar_actual_kw
    assert p.water_demand_forecast_litres != p.water_demand_actual_litres


def test_cloudy_day_has_less_actual_solar_than_clear_day():
    clear = sum(make_request("clear").profiles.solar_actual_kw)
    cloudy = sum(make_request("cloudy").profiles.solar_actual_kw)
    assert cloudy < 0.75 * clear


def test_generator_is_deterministic():
    assert generate_scenario("cloudy") == generate_scenario("cloudy")


@pytest.mark.parametrize("policy,tariff", [("zero_export", 0.0), ("compensated_export", 4.0)])
def test_energy_balances_hold_for_every_strategy(weather, policy, tariff):
    req = make_request(weather, **{"site.export_policy": policy, "site.export_tariff_per_kwh": tariff})
    out = run_comparison(req)
    other_kwh = sum(req.profiles.other_building_load_kw) * 0.25
    for k in KEYS:
        m = getattr(out.strategies, k).metrics
        # solar generated = used on site + curtailed + exported
        assert m.solar_self_consumption_kwh + m.curtailed_solar_kwh + m.exported_solar_kwh == pytest.approx(
            m.solar_generation_kwh, abs=0.02)
        # building + pump demand = solar used + grid import
        assert m.solar_self_consumption_kwh + m.grid_import_kwh == pytest.approx(other_kwh + m.pump_energy_kwh, abs=0.02)
        # pump energy follows runtime x pump power
        assert m.pump_energy_kwh == pytest.approx(m.pump_runtime_minutes / 60 * req.pump.power_kw, abs=0.01)
        assert m.cost_inr == pytest.approx(m.import_cost_inr - m.export_revenue_inr, abs=0.02)
        if policy == "zero_export":
            assert m.exported_solar_kwh == 0 and m.export_revenue_inr == 0
        else:
            assert m.curtailed_solar_kwh == 0


def test_clear_day_optimizer_beats_habit_and_uses_more_solar():
    out = run_comparison(make_request("clear"))
    h, o = out.strategies.habit.metrics, out.strategies.optimizer.metrics
    assert o.cost_inr < h.cost_inr
    assert o.solar_self_consumption_kwh > h.solar_self_consumption_kwh
    assert o.curtailed_solar_kwh < h.curtailed_solar_kwh
    assert o.unmet_water_demand_litres == 0
    assert out.comparison.solar_self_consumption_change_percentage_points == pytest.approx(
        o.solar_self_consumption_pct - h.solar_self_consumption_pct, abs=0.01)


def test_cloudy_day_benefit_is_much_smaller_than_clear_day_and_reported_honestly():
    clear = run_comparison(make_request("clear")).comparison.cost_difference_inr
    cloudy = run_comparison(make_request("cloudy"))
    assert cloudy.comparison.cost_difference_inr < 0.25 * clear
    # the forecast was optimistic: planned cost differs from evaluated cost, and the response says so
    assert any("Optimizer cost under the forecast" in a for a in cloudy.assumptions)


def test_net_metering_case_shifting_gives_no_meaningful_saving():
    """Compensated export at the import tariff: solar not used by the pump is sold at the
    same price the grid charges, so moving the pump into the sun saves (almost) nothing."""
    req = make_request("clear", **{"site.export_policy": "compensated_export",
                                   "site.export_tariff_per_kwh": 8.0})
    out = run_comparison(req)
    h, o = out.strategies.habit.metrics, out.strategies.optimizer.metrics
    assert h.pump_runtime_minutes == o.pump_runtime_minutes  # same pumping volume, only the timing differs
    assert abs(h.cost_inr - o.cost_inr) <= max(1.0, 0.01 * abs(h.cost_inr))
    assert any("negligible" in w for w in out.warnings)
    # ...whereas with zero export, shifting is worth something
    zero = run_comparison(make_request("clear"))
    assert zero.comparison.cost_difference_inr > 10 * abs(h.cost_inr - o.cost_inr) + 1.0


def test_compensated_export_with_lower_feed_in_tariff_still_rewards_shifting():
    req = make_request("clear", **{"site.export_policy": "compensated_export",
                                   "site.export_tariff_per_kwh": 3.0})
    assert run_comparison(req).comparison.cost_difference_inr > 5.0


def test_response_warns_when_export_tariff_is_ignored():
    req = make_request("clear", **{"site.export_tariff_per_kwh": 5.0})
    assert any("ignored" in w for w in run_comparison(req).warnings)


# ------------------------------------------------------------------ the shipped demo file
def _close(a, b):
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= 0.002
    return a == b


def test_demo_file_is_in_sync_with_the_generator():
    on_disk = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    assert _close(on_disk, json.loads(json.dumps(generate_demo_file())))
    assert set(on_disk["scenarios"]) == {"clear", "cloudy"}
    for s in on_disk["scenarios"].values():
        ScenarioRequest.model_validate(s)
