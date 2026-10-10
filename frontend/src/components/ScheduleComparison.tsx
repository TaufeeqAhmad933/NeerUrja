/**
 * ScheduleComparison — comparative operational breakdown of the three pump strategies.
 * Displays actual backend 96-interval pump schedules (0/1), solar self-consumption %,
 * grid energy import, operational costs (INR), and constraint violation counts.
 */
import React from 'react';
import { Award, AlertCircle, CheckCircle2 } from 'lucide-react';
import type { Comparison, Strategies, StrategyName } from '../types/api';

interface ScheduleComparisonProps {
  strategies: Strategies;
  comparison: Comparison;
  isLiveBackend?: boolean;
}

const STRATEGY_META: Record<StrategyName, { label: string; description: string }> = {
  habit: {
    label: 'Habit Routine',
    description: 'Fixed morning/evening pumping schedule (baseline)',
  },
  timer: {
    label: 'Standard Timer',
    description: 'Fixed midday window (10:00–14:00) with high-level cut-off',
  },
  optimizer: {
    label: 'Solar Optimizer',
    description: 'Dynamic forecast-aware solar peak alignment',
  },
};

/** Mini 96-cell strip showing pump on/off pattern */
const ScheduleStrip: React.FC<{ schedule: number[]; isWinner?: boolean }> = ({ schedule, isWinner }) => (
  <div className="schedule-strip" title="24-hour pump schedule (green = pump ON, light grey = OFF)">
    {schedule.map((val, i) => {
      const on = val === 1;
      const h = Math.floor(i / 4).toString().padStart(2, '0');
      const m = ((i % 4) * 15).toString().padStart(2, '0');
      return (
        <div
          key={i}
          className={`schedule-strip-cell schedule-strip-cell--${on ? 'on' : 'off'}`}
          style={
            on
              ? isWinner
                ? { background: '#2d5a34' }
                : { background: '#2d7da8' }
              : undefined
          }
          title={`${h}:${m} — Pump is ${on ? 'ON (running)' : 'OFF (standby)'}`}
        />
      );
    })}
  </div>
);

export const ScheduleComparison: React.FC<ScheduleComparisonProps> = ({
  strategies,
  comparison,
  isLiveBackend = false,
}) => {
  const strategyKeys: StrategyName[] = ['habit', 'timer', 'optimizer'];

  return (
    <div className="schedule-comparison card">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span className="card-title">Strategy Benchmark</span>
          <span className="card-subtitle" style={{ marginLeft: 8 }}>
            96 × 15-minute operational intervals
          </span>
        </div>
        <span
          style={{
            fontSize: '11px',
            fontFamily: 'IBM Plex Mono, monospace',
            padding: '2px 8px',
            borderRadius: 4,
            background: isLiveBackend ? '#eaf4eb' : '#fef3c7',
            color: isLiveBackend ? '#2d5a34' : '#92400e',
            border: `1px solid ${isLiveBackend ? '#86efac' : '#fde68a'}`,
          }}
        >
          {isLiveBackend ? 'Backend Execution' : 'Local Simulation Preview'}
        </span>
      </div>

      <div className="schedule-comparison-table-wrap">
        {/* Strip Time Ruler */}
        <div className="strategy-time-ruler">
          <div style={{ width: 150 }} />
          <div className="time-ruler-marks">
            <span>00:00</span>
            <span>04:00</span>
            <span>08:00</span>
            <span>12:00 (Solar Peak)</span>
            <span>16:00</span>
            <span>20:00</span>
            <span>24:00</span>
          </div>
          <div style={{ width: 280 }} />
        </div>

        {/* Column headers */}
        <div className="strategy-row-head">
          <span className="strategy-head-label">Strategy</span>
          <span className="strategy-head-label">24-Hour Pumping Profile (96 Slots)</span>
          <span className="strategy-head-label strategy-head-label--right">Solar Self-Con. %</span>
          <span className="strategy-head-label strategy-head-label--right">Grid Import</span>
          <span className="strategy-head-label strategy-head-label--right">Net Cost (₹)</span>
          <span className="strategy-head-label strategy-head-label--right">Constraint Status</span>
        </div>

        {strategyKeys.map((key) => {
          const meta = STRATEGY_META[key];
          const strategy = strategies[key];
          const isWinner = comparison.best_cost_strategy === key;
          const violations = strategy?.metrics?.constraint_violations;
          const totalViolations = violations?.total ?? 0;
          const unmetDemandL = strategy?.metrics?.unmet_water_demand_litres ?? 0;
          const hasRisk = totalViolations > 0 || unmetDemandL > 0;

          return (
            <div
              key={key}
              className={`strategy-row${isWinner ? ' strategy-row--winner' : ''}`}
              role="row"
            >
              {/* Strategy Name & Tag */}
              <div className="strategy-name">
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span className="strategy-name-primary">{meta.label}</span>
                  {isWinner && (
                    <span className="strategy-name-winner-badge">
                      <Award size={10} strokeWidth={2.5} />
                      Lowest Cost Winner
                    </span>
                  )}
                </div>
                <span className="strategy-name-secondary">{meta.description}</span>
              </div>

              {/* 96-interval visual schedule strip */}
              <div style={{ minWidth: 200 }}>
                {strategy && (
                  <ScheduleStrip
                    schedule={strategy.schedule_pump_on}
                    isWinner={isWinner}
                  />
                )}
              </div>

              {/* Solar self consumption % */}
              <div className={`strategy-metric${isWinner ? ' strategy-metric--highlight' : ''}`}>
                {strategy?.metrics?.solar_self_consumption_pct !== undefined
                  ? `${strategy.metrics.solar_self_consumption_pct.toFixed(1)}%`
                  : '—'}
              </div>

              {/* Grid electricity used */}
              <div className="strategy-metric">
                {strategy?.metrics?.grid_import_kwh !== undefined
                  ? `${strategy.metrics.grid_import_kwh.toFixed(1)} kWh`
                  : '—'}
              </div>

              {/* Cost in INR */}
              <div className={`strategy-metric${isWinner ? ' strategy-metric--highlight' : ''}`}>
                {strategy?.metrics?.cost_inr !== undefined
                  ? `₹${strategy.metrics.cost_inr.toFixed(0)}`
                  : '—'}
              </div>

              {/* Water Shortfall & Constraint Safety Status */}
              <div
                className="strategy-metric"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'flex-end',
                  gap: 4,
                  fontSize: '12px',
                  color: hasRisk ? '#b91c1c' : '#15803d',
                }}
              >
                {hasRisk ? (
                  <>
                    <AlertCircle size={13} />
                    <span>
                      {totalViolations > 0 ? `${totalViolations} Violations` : `${unmetDemandL.toFixed(0)}L Unmet`}
                    </span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={13} />
                    <span>No Violations</span>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Selection note from backend */}
      {comparison.selection_note && (
        <div
          style={{
            marginTop: 14,
            padding: '10px 14px',
            background: '#faf8f5',
            borderTop: '1px solid #dedad4',
            fontSize: '12px',
            color: '#4b5563',
            fontFamily: 'IBM Plex Sans, sans-serif',
          }}
        >
          <strong>Backend Selection Note:</strong> {comparison.selection_note}
        </div>
      )}
    </div>
  );
};
