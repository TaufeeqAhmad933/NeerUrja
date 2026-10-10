# NeerUrja API contract (v1)

This document is the agreement between the backend (`backend/`) and the frontend
(`frontend/`). The backend implements it exactly and `backend/tests/test_contract.py`
fails if the schema and this document drift apart. **Do not rename fields or change
paths on either side without changing both.**

All profile data produced by the demo is **simulated** (synthetic). It is not measured
data and the forecasts are not validated forecasts.

## Conventions

| Item | Rule |
|---|---|
| Base URL | `VITE_API_BASE_URL` (no trailing slash). Local: `http://127.0.0.1:8000` |
| Format | JSON over HTTPS (HTTP locally) |
| Time grid | 96 intervals per day, 15 minutes each. Index `0` = 00:00-00:15, index `95` = 23:45-24:00 |
| Power profiles | **kW** (average power during the interval), not W and not kWh |
| Water demand | **litres per interval** (per 15 minutes), not litres per hour |
| Tank levels | litres |
| Money | INR |
| Pump schedule | integers, `1` = pump ON in that interval, `0` = OFF |
| Unknown fields | rejected with 422 (a misspelled field is an error, never ignored) |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/v1/scenarios/demo` | Load a demo scenario (a ready-to-POST request body) |
| POST | `/api/v1/scenarios/run` | Run all three strategies and return the comparison |

### GET `/health`

```json
{ "status": "ok", "service": "neerurja-backend", "version": "1.0.0" }
```

### GET `/api/v1/scenarios/demo?weather=clear|cloudy`

`weather` is optional (default `clear`). Any other value returns 422.
The response body is a complete request body for `POST /api/v1/scenarios/run`:
the frontend can pass it back unchanged. `scenario_id` is `campus-demo-01-clear` or
`campus-demo-01-cloudy`.

Returns 503 (`scenario_store_unavailable`) if the demo scenario file cannot be read
(for example the S3 object was not uploaded). The backend never silently substitutes
other data when S3 is configured.

### POST `/api/v1/scenarios/run`

#### Request

```json
{
  "scenario_id": "campus-demo-01-clear",
  "data_mode": "simulated",
  "interval_minutes": 15,
  "site": {
    "solar_capacity_kwp": 50,
    "sanctioned_load_kw": 60,
    "export_policy": "zero_export",
    "import_tariff_per_kwh": 8,
    "export_tariff_per_kwh": 0
  },
  "pump": {
    "power_kw": 5,
    "flow_litres_per_hour": 4000,
    "minimum_run_minutes": 45,
    "max_starts_per_day": 3
  },
  "tank": {
    "capacity_litres": 10000,
    "initial_level_litres": 6000,
    "minimum_level_litres": 2000,
    "maximum_level_litres": 10000
  },
  "profiles": {
    "solar_forecast_kw": [ "...96 numbers..." ],
    "solar_actual_kw": [ "...96 numbers..." ],
    "water_demand_forecast_litres": [ "...96 numbers..." ],
    "water_demand_actual_litres": [ "...96 numbers..." ],
    "other_building_load_kw": [ "...96 numbers..." ],
    "baseline_pump_on": [ "...96 values, each 0 or 1..." ],
    "import_tariff_per_slot": [ "...96 numbers..." ]
  }
}
```

Field rules (violations return 422):

| Field | Rule |
|---|---|
| `scenario_id` | 1-64 characters: letters, digits, `.`, `_`, `-` |
| `data_mode` | `"simulated"` or `"measured"` |
| `interval_minutes` | must be `15` |
| `site.solar_capacity_kwp` | > 0 and <= 10000 |
| `site.sanctioned_load_kw` | > 0. Applied to **grid import** in each interval |
| `site.export_policy` | `"zero_export"` or `"compensated_export"` |
| `site.import_tariff_per_kwh`, `site.export_tariff_per_kwh` | >= 0 INR/kWh |
| `pump.power_kw`, `pump.flow_litres_per_hour` | > 0 |
| `pump.minimum_run_minutes` | integer, 0-1440. Rounded up to whole intervals |
| `pump.max_starts_per_day` | integer, 1-96 |
| `tank.*` | `minimum_level_litres <= initial_level_litres <= maximum_level_litres <= capacity_litres` |
| every profile | exactly 96 entries; finite numbers; no nulls; no negatives |
| `solar_*_kw` | each entry <= 1.25 x `solar_capacity_kwp` (catches W-vs-kW mistakes) |
| `baseline_pump_on` | each entry 0 or 1 (JSON `true`/`false` accepted) |
| `import_tariff_per_slot` | used for ALL cost calculations. `site.import_tariff_per_kwh` is the nominal tariff; a warning is returned if they differ |

Export policies:

* `zero_export` - solar surplus the building cannot use is **curtailed** and earns nothing
  (`export_tariff_per_kwh` is ignored; a warning is returned if it is non-zero).
* `compensated_export` - surplus is exported and paid at `export_tariff_per_kwh`. If the
  export tariff equals the import tariff, shifting the pump into the sun saves essentially
  nothing and the response says so in `warnings`.

#### Response (200)

```json
{
  "scenario_id": "campus-demo-01-clear",
  "data_mode": "simulated",
  "strategies": {
    "habit":     { "schedule_pump_on": [], "metrics": {}, "timeseries": {} },
    "timer":     { "schedule_pump_on": [], "metrics": {}, "timeseries": {} },
    "optimizer": { "schedule_pump_on": [], "metrics": {}, "timeseries": {} }
  },
  "comparison": {
    "best_cost_strategy": "optimizer",
    "cost_difference_inr": 0,
    "solar_self_consumption_change_percentage_points": 0,
    "selection_note": ""
  },
  "assumptions": [],
  "warnings": []
}
```

(The arrays and zeros above are placeholders showing shape. Every value is computed per
request; nothing is preselected or hardcoded.)

`strategies.<name>`:

* `habit` - the schedule given in `profiles.baseline_pump_on`, evaluated as given.
* `timer` - fixed 10:00-14:00 window with high-level cut-off and low-level emergency start.
* `optimizer` - forecast-aware dynamic programme.
* `schedule_pump_on` - 96 integers (0/1).
* `metrics` - see below. All evaluated against the **actual** profiles.
* `timeseries` - per-interval results (96 entries each) so the UI can draw charts without
  re-implementing the physics.

#### `metrics`

| Field | Unit | Meaning |
|---|---|---|
| `solar_generation_kwh` | kWh | Total actual solar generation |
| `solar_self_consumption_kwh` | kWh | Solar energy used on site (building + pump) |
| `solar_self_consumption_pct` | % | `solar_self_consumption_kwh / solar_generation_kwh` |
| `self_sufficiency_pct` | % | Share of total electricity demand (building + pump) met by solar |
| `curtailed_solar_kwh` | kWh | Solar surplus wasted (only under `zero_export`) |
| `exported_solar_kwh` | kWh | Solar surplus exported (only under `compensated_export`) |
| `grid_import_kwh` | kWh | Energy bought from the grid |
| `pump_energy_kwh` | kWh | Pump electricity use |
| `import_cost_inr` | INR | Grid import kWh x per-interval tariff |
| `export_revenue_inr` | INR | Export kWh x export tariff |
| `cost_inr` | INR | `import_cost_inr - export_revenue_inr` |
| `peak_grid_import_kw` | kW | Highest grid import in any interval |
| `min_tank_level_litres` | L | Lowest end-of-interval tank level |
| `end_tank_level_litres` | L | Tank level at the end of the day |
| `unmet_water_demand_litres` | L | Demand that could not be supplied (tank empty) |
| `spilled_water_litres` | L | Water lost to tank overflow |
| `pump_starts` | count | OFF-to-ON transitions (pump assumed OFF before 00:00) |
| `pump_runtime_minutes` | min | Total pump ON time |
| `constraint_violations` | object | See next table |

`constraint_violations` (counts, evaluated against actual conditions; **highlight these in the UI**):

| Field | Meaning |
|---|---|
| `tank_below_minimum_slots` | Intervals ending below `tank.minimum_level_litres` |
| `tank_overflow_slots` | Intervals in which water overflowed |
| `power_limit_slots` | Intervals where grid import exceeded `sanctioned_load_kw` |
| `minimum_runtime_violations` | Pump runs shorter than the minimum that ended inside the day |
| `excess_starts` | Starts above `max_starts_per_day` |
| `total` | Sum of the five counts above |

Unmet water demand is reported separately in `unmet_water_demand_litres`.

#### `timeseries` (each array has 96 entries)

| Field | Unit |
|---|---|
| `tank_level_litres` | L, end of interval |
| `grid_import_kw` | kW |
| `solar_used_kw` | kW |
| `curtailed_solar_kw` | kW |
| `exported_solar_kw` | kW |

#### `comparison`

| Field | Meaning |
|---|---|
| `best_cost_strategy` | `"habit"`, `"timer"` or `"optimizer"`. The lowest-cost strategy **among those that meet every constraint** against actual conditions **and** end the day with at least the initial tank level (a strategy that only looks cheap because it drains the tank is excluded). If none qualifies, the lowest-cost strategy overall is returned and `selection_note` says so. |
| `cost_difference_inr` | `habit.cost_inr - best.cost_inr`. `0` when `habit` is the best. May be `0` when strategies tie |
| `solar_self_consumption_change_percentage_points` | `optimizer.solar_self_consumption_pct - habit.solar_self_consumption_pct` (can be negative) |
| `selection_note` | Plain-language explanation of how the winner was selected, including ties |

`assumptions` is a list of strings stating the modelling assumptions (display them). `warnings`
is a list of strings the UI must show prominently: shortages, overflow, power-limit violations,
relaxed optimizer settings, negligible-benefit notices, ignored inputs.

**Safety rule:** a plan that was feasible under the forecast is never described as safe. If
actual water demand or solar differs, the shortage or violation appears in `metrics` and `warnings`.

## Errors

| Status | When | Body |
|---|---|---|
| 422 | Request fails validation | FastAPI default: `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` |
| 422 | No feasible optimizer schedule | `{"detail": {"code": "optimizer_infeasible", "message": "...", "details": ["..."]}}` |
| 503 | Demo scenario store unreadable | `{"detail": {"code": "scenario_store_unavailable", "message": "..."}}` |

Because `detail` is a list for validation errors and an object for the other two, check
`Array.isArray(detail)` before reading `detail.code`.

## Physical and economic model (what the numbers mean)

Per interval (`dt` = 0.25 h):

```
pump_kw      = power_kw if pump ON else 0
load         = other_building_load_kw + pump_kw
solar_used   = min(solar_actual_kw, load)
grid_import  = load - solar_used
surplus      = solar_actual_kw - solar_used     (curtailed or exported)
tank         = previous level + flow_litres_per_hour x dt (if ON) - water_demand_actual_litres
               above maximum_level_litres -> spilled; below 0 -> unmet demand
cost         = grid_import x dt x import_tariff_per_slot - exported kWh x export_tariff
```

The optimizer plans on `solar_forecast_kw` and `water_demand_forecast_litres` only. Other
building load and tariffs are treated as known. It never sees the actual profiles.

## Additions relative to the original planning note

The following are additive; none rename or remove an agreed field.

* `GET /api/v1/scenarios/demo` accepts `?weather=clear|cloudy`.
* Each strategy also returns `timeseries`.
* `metrics` contains every required item plus `exported_solar_kwh`, `pump_energy_kwh`,
  `import_cost_inr`, `export_revenue_inr` and `end_tank_level_litres`.
* `constraint_violations` is an object of counts (not a list).
* `comparison` also returns `selection_note`.
* `export_policy` values are `zero_export` and `compensated_export`.
* `data_mode` also accepts `measured`.
