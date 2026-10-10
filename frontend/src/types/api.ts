// ─── NeerUrja API Types ───────────────────────────────────────────────────────
// Authoritative definitions aligned with backend/app/schemas.py & docs/api-types.ts

export type ExportPolicy = 'zero_export' | 'compensated_export';
export type DataMode = 'simulated' | 'measured';
export type StrategyName = 'habit' | 'timer' | 'optimizer';
export type Weather = 'clear' | 'cloudy';

export interface Site {
  solar_capacity_kwp: number;
  sanctioned_load_kw: number;
  export_policy: ExportPolicy;
  import_tariff_per_kwh: number;
  export_tariff_per_kwh: number;
}

export interface Pump {
  power_kw: number;
  flow_litres_per_hour: number;
  minimum_run_minutes: number;
  max_starts_per_day: number;
}

export interface Tank {
  capacity_litres: number;
  initial_level_litres: number;
  minimum_level_litres: number;
  maximum_level_litres: number;
}

/** Every array has exactly 96 entries (24 h, 15-minute intervals). */
export interface Profiles {
  solar_forecast_kw: number[];
  solar_actual_kw: number[];
  water_demand_forecast_litres: number[]; // litres per 15-minute interval
  water_demand_actual_litres: number[]; // litres per 15-minute interval
  other_building_load_kw: number[];
  baseline_pump_on: number[]; // 0 | 1
  import_tariff_per_slot: number[]; // INR/kWh
}

/** Body of GET /api/v1/scenarios/demo and POST /api/v1/scenarios/run */
export interface ScenarioRequest {
  scenario_id: string;
  data_mode: DataMode;
  interval_minutes: 15;
  site: Site;
  pump: Pump;
  tank: Tank;
  profiles: Profiles;
}

export interface ConstraintViolations {
  tank_below_minimum_slots: number;
  tank_overflow_slots: number;
  power_limit_slots: number;
  minimum_runtime_violations: number;
  excess_starts: number;
  total: number;
}

export interface Metrics {
  solar_generation_kwh: number;
  solar_self_consumption_kwh: number;
  solar_self_consumption_pct: number;
  self_sufficiency_pct: number;
  curtailed_solar_kwh: number;
  exported_solar_kwh: number;
  grid_import_kwh: number;
  pump_energy_kwh: number;
  import_cost_inr: number;
  export_revenue_inr: number;
  cost_inr: number;
  peak_grid_import_kw: number;
  min_tank_level_litres: number;
  end_tank_level_litres: number;
  unmet_water_demand_litres: number;
  spilled_water_litres: number;
  pump_starts: number;
  pump_runtime_minutes: number;
  constraint_violations: ConstraintViolations;
}

/** 96 entries each. */
export interface Timeseries {
  tank_level_litres: number[];
  grid_import_kw: number[];
  solar_used_kw: number[];
  curtailed_solar_kw: number[];
  exported_solar_kw: number[];
}

export interface StrategyResult {
  schedule_pump_on: number[]; // 0 | 1, 96 entries
  metrics: Metrics;
  timeseries: Timeseries;
}

export interface Strategies {
  habit: StrategyResult;
  timer: StrategyResult;
  optimizer: StrategyResult;
}

export interface Comparison {
  best_cost_strategy: StrategyName;
  cost_difference_inr: number;
  solar_self_consumption_change_percentage_points: number;
  selection_note: string;
}

export interface ScenarioResponse {
  scenario_id: string;
  data_mode: DataMode;
  strategies: Strategies;
  comparison: Comparison;
  assumptions: string[];
  warnings: string[];
}

/** Health Check Response */
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

/** Error response types */
export interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiErrorDetail {
  code: 'optimizer_infeasible' | 'scenario_store_unavailable';
  message: string;
  details?: string[];
}

export interface ApiErrorBody {
  detail: ValidationErrorItem[] | ApiErrorDetail;
}
