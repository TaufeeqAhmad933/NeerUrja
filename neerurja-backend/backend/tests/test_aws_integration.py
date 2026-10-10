"""S3 scenario store, CORS and the Lambda handler (no AWS account or credentials needed)."""
import io
import json
import sys
import types
from pathlib import Path

import pytest

from app import main
from app.scenario_generator import generate_demo_file
from tests.conftest import make_dict

TEMPLATE = Path(__file__).resolve().parents[2] / "infra" / "template.yaml"


def fake_boto3(monkeypatch, payload=None, error=None):
    calls = []

    class S3:
        def get_object(self, Bucket, Key):
            calls.append((Bucket, Key))
            if error:
                raise error
            return {"Body": io.BytesIO(json.dumps(payload).encode())}

    mod = types.SimpleNamespace(client=lambda name: S3() if name == "s3" else None)
    monkeypatch.setitem(sys.modules, "boto3", mod)
    return calls


# ------------------------------------------------------------------------ store
def test_local_mode_uses_repo_file_or_generated_fallback(client, monkeypatch, weather, tmp_path):
    monkeypatch.delenv("DEMO_BUCKET", raising=False)
    assert client.get("/api/v1/scenarios/demo", params={"weather": weather}).status_code == 200
    monkeypatch.setenv("DEMO_SCENARIO_PATH", str(tmp_path / "does-not-exist.json"))
    r = client.get("/api/v1/scenarios/demo", params={"weather": weather})
    assert r.status_code == 200 and r.json()["scenario_id"].endswith(weather)


def test_s3_mode_reads_the_configured_object(client, monkeypatch, weather):
    monkeypatch.setenv("DEMO_BUCKET", "my-demo-bucket")
    monkeypatch.setenv("DEMO_OBJECT_KEY", "scenarios/demo_scenario.json")
    calls = fake_boto3(monkeypatch, payload=generate_demo_file())
    r = client.get("/api/v1/scenarios/demo", params={"weather": weather})
    assert r.status_code == 200 and r.json()["scenario_id"].endswith(weather)
    assert calls == [("my-demo-bucket", "scenarios/demo_scenario.json")]


def test_s3_failure_is_a_clear_503_and_never_falls_back_to_local_data(client, monkeypatch):
    monkeypatch.setenv("DEMO_BUCKET", "my-demo-bucket")
    fake_boto3(monkeypatch, error=RuntimeError("AccessDenied"))
    r = client.get("/api/v1/scenarios/demo")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "scenario_store_unavailable"
    assert "my-demo-bucket" in r.json()["detail"]["message"]


def test_s3_object_with_bad_content_is_a_503(client, monkeypatch):
    monkeypatch.setenv("DEMO_BUCKET", "b")
    fake_boto3(monkeypatch, payload={"scenarios": {"clear": {"scenario_id": "x"}}})
    assert client.get("/api/v1/scenarios/demo").status_code == 503


def test_run_endpoint_does_not_touch_s3(client, monkeypatch):
    monkeypatch.setenv("DEMO_BUCKET", "b")
    calls = fake_boto3(monkeypatch, error=RuntimeError("should not be called"))
    assert client.post("/api/v1/scenarios/run", json=make_dict()).status_code == 200
    assert calls == []


# ------------------------------------------------------------------------- CORS
def preflight(client, origin):
    return client.options("/api/v1/scenarios/run", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})


def test_cors_allows_configured_origin_only(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://main.d1abc.amplifyapp.com/, http://localhost:5173")
    import importlib
    reloaded = importlib.reload(main)
    try:
        c = TestClient(reloaded.app)
        ok = preflight(c, "https://main.d1abc.amplifyapp.com")
        assert ok.headers["access-control-allow-origin"] == "https://main.d1abc.amplifyapp.com"
        assert preflight(c, "http://localhost:5173").status_code == 200
        bad = preflight(c, "https://evil.example.com")
        assert "access-control-allow-origin" not in bad.headers
        resp = c.get("/health", headers={"Origin": "https://main.d1abc.amplifyapp.com"})
        assert resp.headers["access-control-allow-origin"] == "https://main.d1abc.amplifyapp.com"
    finally:
        monkeypatch.delenv("FRONTEND_ORIGIN")
        importlib.reload(main)


# ------------------------------------------------------------------ Lambda handler
class Ctx:
    function_name = "neerurja-api"
    memory_limit_in_mb = 1024
    invoked_function_arn = "arn:aws:lambda:ap-south-1:123456789012:function:neerurja-api"
    aws_request_id = "req-1"


def http_api_event(method, path, body=None, query=""):
    return {
        "version": "2.0", "routeKey": "ANY /{proxy+}", "rawPath": path, "rawQueryString": query,
        "headers": {"content-type": "application/json", "host": "abc.execute-api.ap-south-1.amazonaws.com",
                    "origin": "http://localhost:5173"},
        "queryStringParameters": dict(p.split("=") for p in query.split("&")) if query else None,
        "requestContext": {
            "accountId": "123456789012", "apiId": "abc", "domainName": "abc.execute-api.ap-south-1.amazonaws.com",
            "domainPrefix": "abc", "requestId": "r1", "routeKey": "ANY /{proxy+}", "stage": "$default",
            "time": "10/Oct/2026:10:00:00 +0000", "timeEpoch": 1791626400000,
            "http": {"method": method, "path": path, "protocol": "HTTP/1.1",
                     "sourceIp": "203.0.113.9", "userAgent": "pytest"},
        },
        "body": body, "isBase64Encoded": False,
    }


def test_lambda_handler_serves_health_demo_and_run_through_mangum():
    r = main.handler(http_api_event("GET", "/health"), Ctx())
    assert r["statusCode"] == 200 and json.loads(r["body"])["status"] == "ok"

    r = main.handler(http_api_event("GET", "/api/v1/scenarios/demo", query="weather=cloudy"), Ctx())
    assert r["statusCode"] == 200
    scenario = json.loads(r["body"])
    assert scenario["scenario_id"].endswith("cloudy")

    r = main.handler(http_api_event("POST", "/api/v1/scenarios/run", body=json.dumps(scenario)), Ctx())
    assert r["statusCode"] == 200
    body = json.loads(r["body"])
    assert set(body["strategies"]) == {"habit", "timer", "optimizer"}
    assert r["headers"]["access-control-allow-origin"] == "http://localhost:5173"


def test_lambda_handler_returns_422_for_invalid_input():
    bad = make_dict()
    bad["profiles"]["solar_actual_kw"] = [0.0] * 10
    r = main.handler(http_api_event("POST", "/api/v1/scenarios/run", body=json.dumps(bad)), Ctx())
    assert r["statusCode"] == 422


# ------------------------------------------------------- SAM template coherence
def test_sam_template_matches_the_code():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "Handler: app.main.handler" in text and "CodeUri: ../backend/" in text
    assert "python3.12" in text
    for env in ("DEMO_BUCKET", "DEMO_OBJECT_KEY", "FRONTEND_ORIGIN", "POWERTOOLS_SERVICE_NAME"):
        assert env in text
    assert "s3:GetObject" in text and "s3:*" not in text and "Resource: '*'" not in text
    assert "NatGateway" not in text and "AWS::EC2" not in text and "DynamoDB" not in text
    # the handler really exists with the name the template references
    assert callable(main.handler)
