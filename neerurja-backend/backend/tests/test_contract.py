import re
from pathlib import Path

from app.schemas import Metrics
from tests.conftest import make_dict

REQUIRED_METRICS = {
    "solar_generation_kwh", "solar_self_consumption_kwh", "solar_self_consumption_pct",
    "self_sufficiency_pct", "curtailed_solar_kwh", "grid_import_kwh", "cost_inr",
    "peak_grid_import_kw", "min_tank_level_litres", "unmet_water_demand_litres",
    "spilled_water_litres", "pump_starts", "pump_runtime_minutes", "constraint_violations",
}
DOC = Path(__file__).resolve().parents[2] / "docs" / "API_CONTRACT.md"


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_demo_endpoint_returns_a_postable_request(client, weather):
    r = client.get("/api/v1/scenarios/demo", params={"weather": weather})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"scenario_id", "data_mode", "interval_minutes", "site", "pump", "tank", "profiles"}
    assert body["data_mode"] == "simulated"
    assert all(len(v) == 96 for v in body["profiles"].values())
    assert client.post("/api/v1/scenarios/run", json=body).status_code == 200  # round trip


def test_demo_default_is_clear_and_bad_weather_is_422(client):
    assert client.get("/api/v1/scenarios/demo").json()["scenario_id"].endswith("clear")
    assert client.get("/api/v1/scenarios/demo", params={"weather": "foggy"}).status_code == 422


def test_run_response_shape(client, weather):
    r = client.post("/api/v1/scenarios/run", json=make_dict(weather))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"scenario_id", "data_mode", "strategies", "comparison", "assumptions", "warnings"}
    assert body["data_mode"] == "simulated"
    assert set(body["strategies"]) == {"habit", "timer", "optimizer"}
    for strat in body["strategies"].values():
        assert set(strat) == {"schedule_pump_on", "metrics", "timeseries"}
        assert len(strat["schedule_pump_on"]) == 96 and set(strat["schedule_pump_on"]) <= {0, 1}
        assert REQUIRED_METRICS <= set(strat["metrics"])
        assert set(strat["metrics"]) == set(Metrics.model_fields)
        assert all(len(series) == 96 for series in strat["timeseries"].values())
    cmp = body["comparison"]
    assert set(cmp) == {"best_cost_strategy", "cost_difference_inr",
                        "solar_self_consumption_change_percentage_points", "selection_note"}
    assert cmp["best_cost_strategy"] in {"habit", "timer", "optimizer"}
    assert isinstance(body["assumptions"], list) and body["assumptions"]
    assert isinstance(body["warnings"], list)
    assert any("SIMULATED" in a for a in body["assumptions"])


def test_contract_document_matches_the_schema():
    text = DOC.read_text(encoding="utf-8")
    for field in Metrics.model_fields:
        assert f"`{field}`" in text, f"metrics field {field} is not documented"
    for path in ("/health", "/api/v1/scenarios/demo", "/api/v1/scenarios/run"):
        assert path in text
    for name in ("schedule_pump_on", "timeseries", "compensated_export", "zero_export",
                 "weather", "best_cost_strategy", "optimizer_infeasible"):
        assert name in text
    assert len(re.findall(r"96", text)) >= 3
