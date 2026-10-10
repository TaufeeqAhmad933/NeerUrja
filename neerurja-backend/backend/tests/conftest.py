import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scenario_generator import generate_scenario
from app.schemas import ScenarioRequest


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(params=["clear", "cloudy"])
def weather(request):
    return request.param


def make_request(weather="clear", **overrides) -> ScenarioRequest:
    """Fresh validated request; `overrides` is applied to the raw dict by dotted key
    e.g. make_request(**{"site.sanctioned_load_kw": 30})."""
    return ScenarioRequest.model_validate(make_dict(weather, **overrides))


def make_dict(weather="clear", **overrides) -> dict:
    d = generate_scenario(weather)
    for dotted, value in overrides.items():
        node = d
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = value
    return d
