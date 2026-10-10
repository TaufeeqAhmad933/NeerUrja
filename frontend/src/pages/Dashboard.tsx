/**
 * Dashboard — Primary control console for NeerUrja.
 *
 * Integrates directly with NeerUrja FastAPI backend (/health, /api/v1/scenarios/demo, /api/v1/scenarios/run):
 * - Live scenario loading (Clear Sky vs Monsoon/Overcast)
 * - Real-time scenario execution and strategy comparisons (Habit, Timer, Solar Optimizer)
 * - Interactive 24-hour time playhead scrubber
 * - Energy Flow SVG schematic reacting to actual 15-minute interval data
 * - Dual-axis Solar vs Water Demand chart and Tank level trajectories
 * - Honest water safety, constraint violation warnings, and backend selection notes
 */
import React, { useCallback, useEffect, useState, useMemo } from 'react';
import {
  Sun,
  Droplets,
  Zap,
  Leaf,
  AlertTriangle,
  RefreshCw,
  Info,
  Play,
  Pause,
  SkipForward,
  ShieldCheck,
  ShieldAlert,
  CloudSun,
  PlayCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { EnergyFlowDiagram } from '../components/EnergyFlowDiagram';
import { SolarLoadChart } from '../components/SolarLoadChart';
import { TankLevelChart } from '../components/TankLevelChart';
import { ScheduleComparison } from '../components/ScheduleComparison';
import { MetricCard } from '../components/MetricCard';
import type {
  ScenarioRequest,
  ScenarioResponse,
  StrategyName,
  Weather,
} from '../types/api';

export const Dashboard: React.FC = () => {
  const [selectedWeather, setSelectedWeather] = useState<Weather>('clear');
  const [scenario, setScenario] = useState<ScenarioRequest | null>(null);
  const [result, setResult] = useState<ScenarioResponse | null>(null);
  const [selectedStrategyKey, setSelectedStrategyKey] = useState<StrategyName>('optimizer');

  const [loading, setLoading] = useState<boolean>(true);
  const [runningComparison, setRunningComparison] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false);

  // Time scrubber state: 0 to 95 intervals (15 mins each)
  const [currentInterval, setCurrentInterval] = useState<number>(48); // defaults to 12:00 (midday peak)
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  // Auto-play interval timer
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      setCurrentInterval((prev) => (prev + 1) % 96);
    }, 850);
    return () => clearInterval(timer);
  }, [isPlaying]);

  // Load scenario from backend
  const loadScenario = useCallback(async (weather: Weather) => {
    setLoading(true);
    setError(null);

    try {
      // 1. Fetch demo scenario configuration & profiles
      const demoReq = await apiClient.getDemoScenario(weather);
      setScenario(demoReq);

      // 2. Execute scenario run comparison against actual backend solver
      const runRes = await apiClient.runScenario(demoReq);
      setResult(runRes);
      setSelectedStrategyKey(runRes.comparison.best_cost_strategy || 'optimizer');
      setIsLiveBackend(true);
      setLoading(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to connect to NeerUrja backend API.';
      setError(msg);
      setIsLiveBackend(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadScenario(selectedWeather);
  }, [selectedWeather, loadScenario]);

  // Manual Trigger: Run Comparison button
  const handleRunComparison = async () => {
    if (!scenario || runningComparison) return;
    setRunningComparison(true);
    setError(null);

    try {
      const runRes = await apiClient.runScenario(scenario);
      setResult(runRes);
      setSelectedStrategyKey(runRes.comparison.best_cost_strategy || 'optimizer');
      setIsLiveBackend(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scenario comparison run failed.';
      setError(msg);
    } finally {
      setRunningComparison(false);
    }
  };

  // Weather switch handler
  const handleWeatherChange = (weather: Weather) => {
    if (weather === selectedWeather && scenario) return;
    setSelectedWeather(weather);
  };

  // Active strategy strategy result
  const activeStrategy = result?.strategies?.[selectedStrategyKey] ?? result?.strategies?.optimizer;

  // Selected interval data for EnergyFlowDiagram
  const currentSolarKw = scenario?.profiles?.solar_actual_kw?.[currentInterval] ?? 0;
  const isPumpRunningNow = activeStrategy?.schedule_pump_on?.[currentInterval] === 1;
  const currentGridImportKw = activeStrategy?.timeseries?.grid_import_kw?.[currentInterval] ?? 0;
  const currentSolarUsedKw = activeStrategy?.timeseries?.solar_used_kw?.[currentInterval] ?? 0;
  const currentCurtailedKw = activeStrategy?.timeseries?.curtailed_solar_kw?.[currentInterval] ?? 0;
  const currentExportedKw = activeStrategy?.timeseries?.exported_solar_kw?.[currentInterval] ?? 0;
  const currentSolarSurplusKw = currentCurtailedKw + currentExportedKw;
  const currentTankLevelLitres = activeStrategy?.timeseries?.tank_level_litres?.[currentInterval] ?? scenario?.tank?.initial_level_litres ?? 6000;

  // Compute current tank fill %
  const tankCapacityL = scenario?.tank?.capacity_litres ?? 10000;
  const currentTankLevelPct = (currentTankLevelLitres / tankCapacityL) * 100;
  const minSafetyPct = scenario?.tank ? (scenario.tank.minimum_level_litres / scenario.tank.capacity_litres) * 100 : 20;

  // Format time HH:MM
  const currentHour = Math.floor(currentInterval / 4);
  const currentMinute = (currentInterval % 4) * 15;
  const currentTimeString = `${String(currentHour).padStart(2, '0')}:${String(currentMinute).padStart(2, '0')}`;

  // Water safety verification
  const totalViolations = activeStrategy?.metrics?.constraint_violations?.total ?? 0;
  const unmetDemandLitres = activeStrategy?.metrics?.unmet_water_demand_litres ?? 0;
  const isWaterSafe = totalViolations === 0 && unmetDemandLitres === 0;

  // Baseline habit metrics for delta calculation
  const habitMetrics = result?.strategies?.habit?.metrics;

  return (
    <div className="page-main">
      {/* ── Editorial Hero Strip ─────────────────────────────── */}
      <section className="hero-strip animate-in">
        <h1 className="hero-headline">
          Run the building<br />
          <em>when the sun is up.</em>
        </h1>
        <p className="hero-sub">
          Dynamic rooftop solar alignment for campus water pump scheduling. Evaluated strictly against
          actual solar and water demand profiles with complete constraint safety enforcement.
        </p>
      </section>

      {/* ── Status Banner / Error / Loading ─────────────────── */}
      {!isLiveBackend && !loading && (
        <div className="state-banner state-banner--warning animate-in animate-in--delay-1" role="status">
          <Info size={16} />
          <div style={{ flex: 1, fontSize: '13px' }}>
            <strong>Backend API Offline / Unreachable</strong> — Could not reach{' '}
            <code style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '11px' }}>
              {import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'}
            </code>
            . Please confirm local FastAPI backend is running (<code style={{ fontFamily: 'IBM Plex Mono, monospace' }}>uvicorn app.main:app</code>).
          </div>
          <button
            className="btn btn-secondary"
            onClick={() => loadScenario(selectedWeather)}
            style={{ flexShrink: 0 }}
            title="Retry connecting to live backend API"
          >
            <RefreshCw size={13} />
            Retry Backend
          </button>
        </div>
      )}

      {loading && (
        <div className="state-banner state-banner--loading" role="status">
          <div className="spinner" />
          <span>Loading backend scenario data and running strategy solver…</span>
        </div>
      )}

      {error && isLiveBackend && (
        <div className="state-banner state-banner--error" role="alert">
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button
            className="btn btn-secondary"
            onClick={handleRunComparison}
            style={{ marginLeft: 'auto' }}
          >
            Retry Run
          </button>
        </div>
      )}

      {/* ── Facility Site Summary & Weather Switcher ────────── */}
      {scenario && (
        <section className="site-summary animate-in animate-in--delay-1">
          <div className="site-summary-item">
            <span className="site-summary-label">Scenario ID</span>
            <span className="site-summary-value" style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '13px' }}>
              {scenario.scenario_id}
            </span>
          </div>
          <div className="site-summary-sep" />
          <div className="site-summary-item">
            <span className="site-summary-label">Solar PV Capacity</span>
            <span className="site-summary-value">
              {scenario.site.solar_capacity_kwp} kWp ({scenario.site.export_policy.replace('_', ' ')})
            </span>
          </div>
          <div className="site-summary-sep" />
          <div className="site-summary-item">
            <span className="site-summary-label">Pump Rating</span>
            <span className="site-summary-value">
              {scenario.pump.power_kw} kW · {(scenario.pump.flow_litres_per_hour / 1000).toFixed(1)} kL/hr
            </span>
          </div>
          <div className="site-summary-sep" />
          <div className="site-summary-item">
            <span className="site-summary-label">Storage Tank</span>
            <span className="site-summary-value">
              {(scenario.tank.capacity_litres / 1000).toFixed(0)} kL (Min safety {(scenario.tank.minimum_level_litres / 1000).toFixed(0)} kL)
            </span>
          </div>
          <div className="site-summary-sep" />

          {/* Scenario Selector & Run Control */}
          <div className="site-summary-item" style={{ flexGrow: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="site-summary-label">Weather Profile</span>
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button
                  type="button"
                  className={`scenario-pill ${selectedWeather === 'clear' ? 'scenario-pill--active' : ''}`}
                  onClick={() => handleWeatherChange('clear')}
                  disabled={loading}
                >
                  <Sun size={13} />
                  Clear Sky (High Irradiance)
                </button>
                <button
                  type="button"
                  className={`scenario-pill ${selectedWeather === 'cloudy' ? 'scenario-pill--active' : ''}`}
                  onClick={() => handleWeatherChange('cloudy')}
                  disabled={loading}
                >
                  <CloudSun size={13} />
                  Monsoon / Overcast
                </button>
              </div>
            </div>

            <button
              type="button"
              className="btn btn-primary"
              onClick={handleRunComparison}
              disabled={runningComparison || loading || !isLiveBackend}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', fontSize: '13px' }}
            >
              {runningComparison ? (
                <>
                  <div className="spinner" style={{ width: 14, height: 14 }} />
                  Solving POST Request…
                </>
              ) : (
                <>
                  <PlayCircle size={15} />
                  Run Comparison (POST)
                </>
              )}
            </button>
          </div>
        </section>
      )}

      {/* ── Water Safety & Reserve Notification Banner ──────── */}
      {result && activeStrategy && (
        <div
          className="animate-in animate-in--delay-2"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 18px',
            borderRadius: 6,
            background: isWaterSafe ? '#f0fdf4' : '#fef2f2',
            border: `1px solid ${isWaterSafe ? '#bbf7d0' : '#fecaca'}`,
            color: isWaterSafe ? '#166534' : '#991b1b',
          }}
        >
          {isWaterSafe ? (
            <>
              <ShieldCheck size={18} style={{ flexShrink: 0, color: '#15803d' }} />
              <div style={{ fontSize: '13px' }}>
                <strong>Water Reserve & Constraint Compliant (Backend Verified):</strong> The selected{' '}
                <span style={{ textTransform: 'uppercase', fontWeight: 700 }}>{selectedStrategyKey}</span> schedule
                maintains tank level strictly above safety minimum with 0 constraint violations.
              </div>
            </>
          ) : (
            <>
              <ShieldAlert size={18} style={{ flexShrink: 0, color: '#dc2626' }} />
              <div style={{ fontSize: '13px' }}>
                <strong>Water Safety / Constraint Alert:</strong> Strategy{' '}
                <span style={{ textTransform: 'uppercase', fontWeight: 700 }}>{selectedStrategyKey}</span> has{' '}
                {totalViolations} constraint violations
                {unmetDemandLitres > 0 ? ` and ${unmetDemandLitres.toFixed(0)} L unmet water demand` : ''}.
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Strategy Tabs & Primary Operational KPI Cards ────── */}
      {result && activeStrategy && scenario && (
        <section className="animate-in animate-in--delay-2">
          <div className="section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span className="section-label">Performance Metrics —</span>
              {/* Strategy Selector Tabs */}
              <div style={{ display: 'flex', gap: 4 }}>
                {(['habit', 'timer', 'optimizer'] as StrategyName[]).map((key) => {
                  const isBest = result.comparison.best_cost_strategy === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`scenario-pill ${selectedStrategyKey === key ? 'scenario-pill--active' : ''}`}
                      onClick={() => setSelectedStrategyKey(key)}
                      style={{ textTransform: 'capitalize', padding: '4px 10px', fontSize: '12px' }}
                    >
                      {key} {isBest ? '★ (Best)' : ''}
                    </button>
                  );
                })}
              </div>
            </div>
            <span
              style={{
                fontSize: '11px',
                fontFamily: 'IBM Plex Mono, monospace',
                color: '#6e6e73',
              }}
            >
              Data Mode: {result.data_mode.toUpperCase()} (Backend Evaluated)
            </span>
          </div>

          <div className="metric-cards-grid">
            <MetricCard
              label="Solar Self-Consumption"
              value={activeStrategy.metrics.solar_self_consumption_pct.toFixed(1)}
              unit="%"
              icon={<Sun size={18} />}
              iconVariant="solar"
              delta={getDeltaText(
                activeStrategy.metrics.solar_self_consumption_pct,
                habitMetrics?.solar_self_consumption_pct,
                '%',
                true,
              )}
              deltaPositive={true}
              isEstimate={false}
              subtext={`${activeStrategy.metrics.solar_self_consumption_kwh.toFixed(1)} kWh used on site`}
            />

            <MetricCard
              label="Grid Electricity Import"
              value={activeStrategy.metrics.grid_import_kwh.toFixed(1)}
              unit=" kWh"
              icon={<Zap size={18} />}
              delta={getDeltaText(
                activeStrategy.metrics.grid_import_kwh,
                habitMetrics?.grid_import_kwh,
                ' kWh',
                false,
              )}
              deltaPositive={false}
              isEstimate={false}
              subtext={`Peak grid draw: ${activeStrategy.metrics.peak_grid_import_kw.toFixed(1)} kW`}
            />

            <MetricCard
              label="Net Operating Cost"
              value={`₹${activeStrategy.metrics.cost_inr.toFixed(0)}`}
              icon={<Leaf size={18} />}
              delta={getDeltaText(
                activeStrategy.metrics.cost_inr,
                habitMetrics?.cost_inr,
                ' ₹',
                false,
              )}
              deltaPositive={false}
              isEstimate={false}
              subtext={
                activeStrategy.metrics.export_revenue_inr > 0
                  ? `Revenue: ₹${activeStrategy.metrics.export_revenue_inr.toFixed(0)}`
                  : `Import cost: ₹${activeStrategy.metrics.import_cost_inr.toFixed(0)}`
              }
            />

            <MetricCard
              label="Pump Energy & Runtime"
              value={activeStrategy.metrics.pump_energy_kwh.toFixed(1)}
              unit=" kWh"
              icon={<Sun size={18} />}
              iconVariant="solar"
              subtext={`${activeStrategy.metrics.pump_runtime_minutes} mins (${activeStrategy.metrics.pump_starts} starts)`}
              isEstimate={false}
            />

            <MetricCard
              label="Constraint Violations"
              value={activeStrategy.metrics.constraint_violations.total}
              unit=" events"
              icon={<Droplets size={18} />}
              iconVariant={activeStrategy.metrics.constraint_violations.total > 0 ? 'warning' : 'water'}
              subtext={
                activeStrategy.metrics.constraint_violations.total === 0
                  ? 'Compliant with all rules'
                  : `${activeStrategy.metrics.constraint_violations.tank_below_minimum_slots} low tank slots`
              }
              isEstimate={false}
            />
          </div>
        </section>
      )}

      {/* ── Two-Column Interactive Layout ────────────────────── */}
      <section className="two-col animate-in animate-in--delay-3">
        {/* Left Column: Interactive Energy Flow Diagram & Time Scrubber */}
        <div>
          <div className="section-header">
            <span className="section-label">Energy System Schematic</span>
            <span
              style={{
                fontSize: '11px',
                fontFamily: 'IBM Plex Mono, monospace',
                color: '#2d5a34',
                fontWeight: 600,
              }}
            >
              {currentTimeString} (Interval {currentInterval + 1}/96)
            </span>
          </div>

          <div className="card">
            {/* Energy Flow SVG */}
            <EnergyFlowDiagram
              weatherCondition={selectedWeather}
              solarActive={currentSolarKw > 0.2}
              pumpOn={isPumpRunningNow}
              gridFallback={currentGridImportKw > 0.1}
              solarKw={currentSolarKw}
              pumpKw={scenario?.pump?.power_kw ?? 5.0}
              gridImportKw={currentGridImportKw}
              solarSurplusKw={currentSolarSurplusKw}
              tankLevelLitres={currentTankLevelLitres}
              tankCapacityLitres={tankCapacityL}
              minLevelLitres={scenario?.tank?.minimum_level_litres ?? 2000}
              maxLevelLitres={scenario?.tank?.maximum_level_litres ?? 10000}
            />

            {/* Time Controller & Inspector Bar */}
            <div
              style={{
                padding: '14px 18px',
                background: '#faf8f5',
                borderTop: '1px solid var(--color-border)',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#1c1c1e' }}>
                  24-Hour Playhead Inspection
                </span>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ padding: '4px 8px', fontSize: '11px' }}
                    onClick={() => setIsPlaying(!isPlaying)}
                    title={isPlaying ? 'Pause simulation' : 'Play simulation across 24 hours'}
                  >
                    {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                    {isPlaying ? 'Pause' : 'Play 24h'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ padding: '4px 8px', fontSize: '11px' }}
                    onClick={() => setCurrentInterval((prev) => (prev + 1) % 96)}
                    title="Step forward 15 minutes"
                  >
                    <SkipForward size={12} />
                    +15m
                  </button>
                </div>
              </div>

              {/* Range Slider */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: '10px', fontFamily: 'IBM Plex Mono, monospace', color: '#71717a' }}>
                  00:00
                </span>
                <input
                  type="range"
                  min={0}
                  max={95}
                  value={currentInterval}
                  onChange={(e) => {
                    setCurrentInterval(Number(e.target.value));
                    setIsPlaying(false);
                  }}
                  style={{
                    flex: 1,
                    accentColor: '#2d5a34',
                    cursor: 'pointer',
                  }}
                  aria-label="Time of day interval scrubber"
                />
                <span style={{ fontSize: '10px', fontFamily: 'IBM Plex Mono, monospace', color: '#71717a' }}>
                  23:45
                </span>
              </div>

              {/* Quick Jump Time Presets */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="scenario-pill"
                  style={{ padding: '2px 8px', fontSize: '11px' }}
                  onClick={() => {
                    setCurrentInterval(28); // 07:00
                    setIsPlaying(false);
                  }}
                >
                  07:00 Morning Demand
                </button>
                <button
                  type="button"
                  className="scenario-pill"
                  style={{ padding: '2px 8px', fontSize: '11px' }}
                  onClick={() => {
                    setCurrentInterval(50); // 12:30
                    setIsPlaying(false);
                  }}
                >
                  12:30 Solar Peak
                </button>
                <button
                  type="button"
                  className="scenario-pill"
                  style={{ padding: '2px 8px', fontSize: '11px' }}
                  onClick={() => {
                    setCurrentInterval(76); // 19:00
                    setIsPlaying(false);
                  }}
                >
                  19:00 Peak Demand
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Dual Charts */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          {/* Solar Generation & Water Demand Chart */}
          {scenario && (
            <div>
              <div className="section-header">
                <span className="section-label">Solar Generation & Water Demand</span>
                <span style={{ fontSize: '11px', fontFamily: 'IBM Plex Mono, monospace', color: '#6e6e73' }}>
                  Cursor: {currentTimeString}
                </span>
              </div>
              <div className="card">
                <SolarLoadChart
                  solarKw={scenario.profiles.solar_actual_kw}
                  demandLitres={scenario.profiles.water_demand_actual_litres}
                  pumpSchedule={activeStrategy?.schedule_pump_on}
                  currentInterval={currentInterval}
                />
              </div>
            </div>
          )}

          {/* Storage Tank Fill Level by Strategy */}
          {result && scenario && (
            <div>
              <div className="section-header">
                <span className="section-label">Tank Trajectory (%) — Backend Timeseries</span>
                <span
                  style={{
                    fontSize: '11px',
                    fontFamily: 'IBM Plex Mono, monospace',
                    color: currentTankLevelPct < minSafetyPct ? '#dc2626' : '#2d5a34',
                    fontWeight: 600,
                  }}
                >
                  Tank at {currentTimeString}: {currentTankLevelLitres.toFixed(0)} L ({currentTankLevelPct.toFixed(1)}%)
                </span>
              </div>
              <div className="card">
                <TankLevelChart
                  strategies={result.strategies}
                  capacityLitres={scenario.tank.capacity_litres}
                  minLevelLitres={scenario.tank.minimum_level_litres}
                  maxLevelLitres={scenario.tank.maximum_level_litres}
                  initialLevelLitres={scenario.tank.initial_level_litres}
                  currentInterval={currentInterval}
                />
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── Scheduling Strategy Benchmark Table ─────────────── */}
      {result && (
        <section className="animate-in animate-in--delay-4">
          <div className="section-header">
            <span className="section-label">Operational Strategy Comparison</span>
            <span style={{ fontSize: '11px', color: '#6e6e73' }}>
              Evaluated against actual profiles
            </span>
          </div>
          <ScheduleComparison
            strategies={result.strategies}
            comparison={result.comparison}
            isLiveBackend={isLiveBackend}
          />
        </section>
      )}

      {/* ── Modeling Assumptions & Backend Warnings ────────── */}
      {result && (
        <section className="animate-in animate-in--delay-4">
          <div className="section-header">
            <span className="section-label">Engineering Parameters & Model Assumptions</span>
          </div>
          <div className="card">
            <div className="assumptions-grid">
              {result.assumptions.map((item, idx) => (
                <div key={idx} className="assumption-item">
                  <span className="assumption-label">Assumption #{idx + 1}</span>
                  <span className="assumption-value">{item}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ── Active Backend Warnings ──────────────────────────── */}
      {result && result.warnings && result.warnings.length > 0 && (
        <section className="warnings-list animate-in animate-in--delay-4" style={{ marginTop: 16 }}>
          {result.warnings.map((w, i) => (
            <div key={i} className="state-banner state-banner--warning">
              <AlertTriangle size={15} style={{ flexShrink: 0 }} />
              <span><strong>Backend Warning:</strong> {w}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
};

// ── Helper Utilities ──────────────────────────────────────────────────────────

function getDeltaText(
  currentVal: number | undefined,
  baselineVal: number | undefined,
  unit: string,
  higherIsBetter: boolean,
): string | undefined {
  if (currentVal === undefined || baselineVal === undefined) return undefined;
  const diff = currentVal - baselineVal;
  if (Math.abs(diff) < 0.05) return undefined;
  const sign = diff > 0 ? '+' : '';
  const isPositiveChange = higherIsBetter ? diff > 0 : diff < 0;
  const arrow = isPositiveChange ? '↑' : '↓';
  return `${arrow} ${sign}${diff.toFixed(1)}${unit} vs habit`;
}
