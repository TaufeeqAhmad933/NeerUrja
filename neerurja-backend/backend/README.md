# NeerUrja backend

FastAPI + Mangum + Pydantic. Simulation, strategies and optimizer use the Python standard library only (no NumPy, SciPy, pandas, pvlib or solver). See the root `README.md` for setup, run, deploy and clean-up, and `../docs/API_CONTRACT.md` for the API.

## Modules

| File | Role |
|---|---|
| `app/main.py` | FastAPI app, CORS, error handlers, Powertools logging, Lambda `handler` |
| `app/schemas.py` | Request/response models and input validation |
| `app/simulator.py` | Physics: power flows, tank balance, cost helpers, `simulate()` (no FastAPI/Pydantic) |
| `app/strategies.py` | habit, timer, `run_comparison()` (forecast vs actual wiring), warnings and assumptions |
| `app/optimizer.py` | Dynamic-programming scheduler |
| `app/metrics.py` | Metrics from simulation results and the winner selection |
| `app/scenario_generator.py` | Synthetic clear/cloudy scenario generator (simulated data) |
| `app/scenario_store.py` | Demo scenarios from S3 (when configured) or local file |

The simulator, strategies and metrics can be used without starting FastAPI:

```python
from app.scenario_generator import generate_scenario
from app.schemas import ScenarioRequest
from app.strategies import run_comparison

result = run_comparison(ScenarioRequest.model_validate(generate_scenario("cloudy")))
print(result.comparison, result.warnings)
```

## Fair evaluation

* `inputs_from_request(req, "forecast")` builds the optimizer's inputs from forecast solar and forecast water demand only. `optimize_schedule` receives nothing else, so it cannot see actual conditions (tests change the actual profiles and assert the plan does not change).
* `inputs_from_request(req, "actual")` is used to simulate **all three** schedules, with the same actual solar, water demand, other load and tariffs (a test records the inputs of every `simulate` call and asserts they are identical).
* Other building load and tariffs are treated as known to the planner.

## Optimizer: algorithm, assumptions, limits

**Method.** Forward dynamic programme over the 96 intervals. State = (tank-level bucket, pump run state, starts used). Run state encodes OFF / ON-but-minimum-run-not-yet-met / ON-and-free-to-stop, so the minimum runtime is enforced exactly. Transitions are pump OFF or ON.

**Constraints (under the forecast).**
* minimum runtime per start, maximum starts per day;
* pump ON only if forecast grid import stays within the sanctioned load;
* tank level after each interval within `[minimum + reserve, maximum_level_litres]` (no overflow, no shortage);
* each run must complete inside the day;
* end-of-day tank level at least the initial level (so a plan cannot look cheap by draining the tank).

**Objective (lexicographic).** Minimise forecast electricity cost (grid import cost minus export revenue; under `zero_export` surplus earns nothing); then fewer starts; then less runtime; then more forecast solar headroom (a hedge that never overrides cost). Self-consumption is reported separately and is not the objective.

**Settings.** Tank-level bucket = usable range / 80 (100 L for the demo tank). Safety reserve = 5 % of the usable range above the minimum level (400 L for the demo tank). Both are in `OptimizerConfig`; they are not request fields.

**Relaxation ladder.** If no plan exists, the optimizer first drops the reserve, then the "end at least at the initial level" target. Every relaxation is returned in `warnings`. If nothing is feasible, the API returns HTTP 422 with `optimizer_infeasible` and the binding limits. An invalid schedule is never returned silently.

**Exactness and limits (honest version).**
* Level buckets are used only to merge states; every state keeps the exact continuous level of its best path, so each returned schedule is exactly feasible under the forecast (no rounding drift).
* With a bucket step small enough that distinct reachable levels never share a bucket, the DP is exactly optimal. `tests/test_optimizer.py` verifies this against exhaustive search on 10-interval problems (random solar, demand, tariffs, limits, both export policies).
* With the coarser default bucket, two paths in the same bucket are compared by cost alone, so the result is feasible and near-optimal but **not guaranteed optimal**.
* Optimality and feasibility hold under the **forecast**. Against actual conditions the plan can still short the tank, overflow, or exceed the sanctioned load; those results appear in the metrics and `warnings`.
* The model is a single day with the pump OFF at 00:00; no carry-over, no demand charges, no equipment wear costs, no multi-day planning.

## Timer strategy

Window 10:00-14:00. A run starts if starts remain and pumping for one minimum run would not overflow the tank (forecast demand used to track the level); it continues while inside the window and the next interval would not overflow (high-level cut-off). Low-level safeguard: if the tank is about to fall below the minimum level the pump starts or keeps running regardless of the window. It uses no solar information.

## Evaluation conventions

* Tank balance: `level + delivered - demand`; above `maximum_level_litres` is spilled, below 0 is unmet demand.
* Sanctioned load is applied to grid import per interval.
* "Best cost strategy" = lowest cost among strategies that meet all constraints, have no unmet demand and end the day with at least the initial tank level. Spilled water is reported but does not disqualify. Ties within 0.005 INR are broken by solar self-consumption and disclosed in `selection_note`.

## Commands

```bash
pip install -r requirements-dev.txt
python -m pytest -q                      # from backend/
uvicorn app.main:app --reload --app-dir backend   # from the repo root
```

## Deployment prerequisites

AWS account with permission to create Lambda, API Gateway, S3, IAM roles and CloudWatch log groups via CloudFormation; AWS CLI with local credentials; AWS SAM CLI; Python 3.12; Docker only if you need `sam build --use-container`. Details in the root README.
