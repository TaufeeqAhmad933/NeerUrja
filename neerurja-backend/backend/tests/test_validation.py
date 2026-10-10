import math

import pytest
from pydantic import ValidationError

from app.schemas import ScenarioRequest
from tests.conftest import make_dict

PROFILES = [
    "solar_forecast_kw", "solar_actual_kw", "water_demand_forecast_litres",
    "water_demand_actual_litres", "other_building_load_kw", "baseline_pump_on",
    "import_tariff_per_slot",
]


def post(client, body):
    return client.post("/api/v1/scenarios/run", json=body)


@pytest.mark.parametrize("name", PROFILES)
@pytest.mark.parametrize("length", [0, 95, 97])
def test_wrong_profile_length_is_rejected(client, name, length):
    d = make_dict()
    d["profiles"][name] = d["profiles"][name][:length] if length < 96 else d["profiles"][name] + [0] * 1
    r = post(client, d)
    assert r.status_code == 422
    assert name in r.text and "96" in r.text


def test_negative_null_and_nan_values_are_rejected(client):
    d = make_dict()
    d["profiles"]["solar_actual_kw"][10] = -1
    assert post(client, d).status_code == 422
    d = make_dict()
    d["profiles"]["water_demand_actual_litres"][3] = None  # missing value
    assert post(client, d).status_code == 422
    d = make_dict()
    d["profiles"]["other_building_load_kw"][3] = float("nan")
    with pytest.raises(ValidationError):
        ScenarioRequest.model_validate(d)
    d["profiles"]["other_building_load_kw"][3] = math.inf
    with pytest.raises(ValidationError):
        ScenarioRequest.model_validate(d)


def test_baseline_must_be_zero_or_one_and_accepts_booleans(client):
    d = make_dict()
    d["profiles"]["baseline_pump_on"][5] = 2
    assert post(client, d).status_code == 422
    d = make_dict()
    d["profiles"]["baseline_pump_on"] = [bool(x) for x in d["profiles"]["baseline_pump_on"]]
    assert post(client, d).status_code == 200


def test_solar_in_wrong_units_is_rejected(client):
    d = make_dict()
    d["profiles"]["solar_actual_kw"] = [x * 1000 for x in d["profiles"]["solar_actual_kw"]]  # W, not kW
    r = post(client, d)
    assert r.status_code == 422 and "kW" in r.text


@pytest.mark.parametrize("path,value", [
    ("site.export_policy", "net_metering"),
    ("site.solar_capacity_kwp", 0),
    ("site.sanctioned_load_kw", -5),
    ("site.import_tariff_per_kwh", -1),
    ("site.export_tariff_per_kwh", -0.5),
    ("pump.power_kw", 0),
    ("pump.flow_litres_per_hour", 0),
    ("pump.minimum_run_minutes", -1),
    ("pump.max_starts_per_day", 0),
    ("tank.initial_level_litres", 11_000),      # above maximum
    ("tank.initial_level_litres", 1_000),       # below minimum
    ("tank.maximum_level_litres", 12_000),      # above capacity
    ("tank.minimum_level_litres", 11_000),      # above maximum
    ("interval_minutes", 30),
    ("data_mode", "real"),
    ("scenario_id", "has spaces!"),
])
def test_bad_scalar_inputs_are_rejected(client, path, value):
    assert post(client, make_dict(**{path: value})).status_code == 422


def test_unknown_fields_are_rejected_not_ignored(client):
    d = make_dict()
    d["profiles"]["solar_forcast_kw"] = [0] * 96  # typo
    assert post(client, d).status_code == 422
    d = make_dict()
    d["surprise"] = 1
    assert post(client, d).status_code == 422


def test_missing_section_is_rejected(client):
    d = make_dict()
    del d["tank"]
    assert post(client, d).status_code == 422


def test_compensated_export_request_is_accepted(client):
    d = make_dict(**{"site.export_policy": "compensated_export", "site.export_tariff_per_kwh": 4.0})
    assert post(client, d).status_code == 200
