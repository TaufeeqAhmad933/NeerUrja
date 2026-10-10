"""FastAPI application and AWS Lambda entry point.

Endpoints (the contract shared with the frontend; see docs/API_CONTRACT.md):
    GET  /health
    GET  /api/v1/scenarios/demo?weather=clear|cloudy
    POST /api/v1/scenarios/run

Lambda handler: `app.main.handler` (Mangum adapter for API Gateway HTTP API).
"""

import os
import time
from typing import Literal

from aws_lambda_powertools import Logger
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from . import __version__
from .optimizer import InfeasibleScheduleError
from .scenario_store import ScenarioStoreError, demo_source, load_demo_scenario
from .schemas import ScenarioRequest, ScenarioResponse
from .strategies import run_comparison

logger = Logger(service=os.environ.get("POWERTOOLS_SERVICE_NAME", "neerurja-api"))

app = FastAPI(
    title="NeerUrja API",
    version=__version__,
    description="Solar-aware water-pump scheduling: compares habit, timer and optimizer strategies.",
)


def _allowed_origins() -> list[str]:
    raw = os.environ.get(
        "FRONTEND_ORIGIN",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
    )
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


# CORS is handled here (one place, works locally and behind API Gateway).
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=600,
)


@app.exception_handler(InfeasibleScheduleError)
async def _infeasible(_, exc: InfeasibleScheduleError):
    logger.warning("optimizer_infeasible", extra={"detail": exc.details})
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "optimizer_infeasible", "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(ScenarioStoreError)
async def _store_error(_, exc: ScenarioStoreError):
    logger.error("scenario_store_error", extra={"error": str(exc)})
    return JSONResponse(
        status_code=503,
        content={"detail": {"code": "scenario_store_unavailable", "message": str(exc)}},
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "neerurja-backend", "version": __version__}


@app.get("/api/v1/scenarios/demo", response_model=ScenarioRequest)
def get_demo_scenario(weather: Literal["clear", "cloudy"] = Query("clear")):
    logger.info("demo_scenario_requested", extra={"weather": weather, "source": demo_source()})
    return load_demo_scenario(weather)


@app.post("/api/v1/scenarios/run", response_model=ScenarioResponse)
def run_scenario(request: ScenarioRequest):
    started = time.perf_counter()
    result = run_comparison(request)
    logger.info(
        "scenario_run",
        extra={
            "scenario_id": request.scenario_id,
            "data_mode": request.data_mode,
            "export_policy": request.site.export_policy,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "best_cost_strategy": result.comparison.best_cost_strategy,
            "cost_inr": {k: getattr(result.strategies, k).metrics.cost_inr
                         for k in ("habit", "timer", "optimizer")},
            "warning_count": len(result.warnings),
        },
    )
    return result


_mangum = Mangum(app, lifespan="off")


@logger.inject_lambda_context(clear_state=True)
def handler(event, context):
    """AWS Lambda entry point (API Gateway HTTP API, payload format 2.0)."""
    return _mangum(event, context)
