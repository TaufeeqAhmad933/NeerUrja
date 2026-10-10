"""Where the demo scenarios come from.

  * DEMO_BUCKET set   -> read s3://$DEMO_BUCKET/$DEMO_OBJECT_KEY (default
                         scenarios/demo_scenario.json). Any failure is raised as
                         ScenarioStoreError (HTTP 503): it never silently falls back
                         to local data, so a deployed API never pretends S3 was used.
  * DEMO_BUCKET unset -> local development: DEMO_SCENARIO_PATH, else the repo's
                         data/demo_scenario.json, else the same scenarios generated
                         in memory by scenario_generator.

No AWS credentials are read or stored here; boto3 uses the Lambda execution role
(or the developer's own AWS CLI profile) via its default credential chain.
"""

import json
import os
from pathlib import Path

from .scenario_generator import generate_demo_file
from .schemas import ScenarioRequest

DEFAULT_OBJECT_KEY = "scenarios/demo_scenario.json"
REPO_DEMO_FILE = Path(__file__).resolve().parents[2] / "data" / "demo_scenario.json"
WEATHERS = ("clear", "cloudy")


class ScenarioStoreError(Exception):
    pass


def _read_s3(bucket: str, key: str) -> dict:
    try:
        import boto3  # imported lazily: only needed when S3 storage is configured

        body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body)
    except Exception as exc:  # noqa: BLE001 - surfaced as a clear 503
        raise ScenarioStoreError(
            f"Could not read demo scenario s3://{bucket}/{key}: {type(exc).__name__}. "
            "Check that the object was uploaded and the function role may read it."
        ) from exc


def _read_local() -> tuple[dict, str]:
    path = Path(os.environ.get("DEMO_SCENARIO_PATH") or REPO_DEMO_FILE)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8")), f"file:{path}"
        except (OSError, json.JSONDecodeError) as exc:
            raise ScenarioStoreError(f"Could not read local demo scenario file {path}: {exc}") from exc
    return generate_demo_file(), "generated-in-memory"


def demo_source() -> str:
    bucket = os.environ.get("DEMO_BUCKET")
    if bucket:
        return f"s3://{bucket}/{os.environ.get('DEMO_OBJECT_KEY') or DEFAULT_OBJECT_KEY}"
    return "local"


def load_demo_scenario(weather: str = "clear") -> ScenarioRequest:
    if weather not in WEATHERS:
        raise ScenarioStoreError(f"unknown weather {weather!r}; expected one of {list(WEATHERS)}")
    bucket = os.environ.get("DEMO_BUCKET")
    if bucket:
        data = _read_s3(bucket, os.environ.get("DEMO_OBJECT_KEY") or DEFAULT_OBJECT_KEY)
    else:
        data, _ = _read_local()
    try:
        return ScenarioRequest.model_validate(data["scenarios"][weather])
    except (KeyError, TypeError, ValueError) as exc:
        raise ScenarioStoreError(f"Demo scenario file is missing or invalid for weather={weather!r}") from exc
