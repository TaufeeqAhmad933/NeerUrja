/**
 * TankLevelChart — displays 24-hour storage tank fill level trajectories (%)
 * for Habit, Timer, and Optimizer strategies, derived from backend timeseries data.
 * Highlights minimum safety reserve limit and maximum capacity bounds.
 */
import React, { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import type { Strategies } from '../types/api';

interface TankLevelChartProps {
  strategies: Strategies;
  capacityLitres: number;
  minLevelLitres: number;
  maxLevelLitres: number;
  initialLevelLitres: number;
  currentInterval?: number;
}

function intervalToTime(i: number): string {
  const totalMinutes = i * 15;
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

const CustomTooltip: React.FC<{
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
  minPct: number;
  capacityL: number;
}> = ({ active, payload, label, minPct, capacityL }) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: '#ffffff',
        border: '1px solid #dedad4',
        borderRadius: 4,
        padding: '8px 12px',
        fontSize: '11px',
        fontFamily: 'IBM Plex Mono, monospace',
        boxShadow: '0 2px 8px rgba(0,0,0,.08)',
      }}
    >
      <div style={{ marginBottom: 4, color: '#1c1c1e', fontWeight: 600 }}>{label}</div>
      {payload.map((p) => {
        const pct = p.value;
        const litres = Math.round((pct / 100) * capacityL);
        const isCritical = pct < minPct;
        return (
          <div
            key={p.name}
            style={{
              color: p.color,
              display: 'flex',
              gap: 12,
              justifyContent: 'space-between',
              alignItems: 'center',
              lineHeight: 1.5,
            }}
          >
            <span>{p.name}</span>
            <span style={{ fontWeight: 600 }}>
              {pct.toFixed(1)}% ({litres} L){' '}
              {isCritical && <span style={{ color: '#d13b3b' }}>⚠ Under Min!</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export const TankLevelChart: React.FC<TankLevelChartProps> = ({
  strategies,
  capacityLitres,
  minLevelLitres,
  maxLevelLitres,
  initialLevelLitres,
  currentInterval,
}) => {
  const minPct = (minLevelLitres / capacityLitres) * 100;
  const maxPct = (maxLevelLitres / capacityLitres) * 100;

  const data = useMemo(() => {
    const habitTs = strategies.habit?.timeseries?.tank_level_litres ?? [];
    const timerTs = strategies.timer?.timeseries?.tank_level_litres ?? [];
    const optTs = strategies.optimizer?.timeseries?.tank_level_litres ?? [];

    const numIntervals = Math.max(96, habitTs.length, timerTs.length, optTs.length);

    return Array.from({ length: numIntervals }, (_, i) => ({
      time: intervalToTime(i),
      Habit: habitTs[i] !== undefined ? parseFloat(((habitTs[i] / capacityLitres) * 100).toFixed(1)) : 0,
      Timer: timerTs[i] !== undefined ? parseFloat(((timerTs[i] / capacityLitres) * 100).toFixed(1)) : 0,
      Optimizer: optTs[i] !== undefined ? parseFloat(((optTs[i] / capacityLitres) * 100).toFixed(1)) : 0,
    }));
  }, [strategies, capacityLitres]);

  const xTicks = [0, 12, 24, 36, 48, 60, 72, 84, 95].map(intervalToTime);

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 12, right: 16, left: -6, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#ece9e4" vertical={false} />

          {/* Min Safety Buffer */}
          <ReferenceLine
            y={minPct}
            stroke="#d13b3b"
            strokeWidth={1.2}
            strokeDasharray="3 3"
            label={{
              value: `Safety Min (${minPct.toFixed(0)}% / ${minLevelLitres}L)`,
              fontSize: 9,
              fill: '#d13b3b',
              fontFamily: 'IBM Plex Mono, monospace',
              position: 'insideBottomRight',
            }}
          />

          {/* Max Overflow Buffer */}
          <ReferenceLine
            y={maxPct}
            stroke="#2d7da8"
            strokeWidth={1}
            strokeDasharray="3 3"
            label={{
              value: `Max Limit (${maxPct.toFixed(0)}%)`,
              fontSize: 9,
              fill: '#2d7da8',
              fontFamily: 'IBM Plex Mono, monospace',
              position: 'insideTopRight',
            }}
          />

          {/* Synchronized Current Inspection Cursor */}
          {currentInterval !== undefined && (
            <ReferenceLine
              x={intervalToTime(currentInterval)}
              stroke="#2d5a34"
              strokeWidth={1.5}
              strokeDasharray="2 2"
            />
          )}

          <XAxis
            dataKey="time"
            ticks={xTicks}
            tick={{ fontSize: 10, fontFamily: 'IBM Plex Mono, monospace', fill: '#6e6e73' }}
            axisLine={{ stroke: '#dedad4' }}
            tickLine={false}
          />

          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 10, fontFamily: 'IBM Plex Mono, monospace', fill: '#6e6e73' }}
            axisLine={false}
            tickLine={false}
            width={38}
            unit="%"
          />

          <Tooltip content={<CustomTooltip minPct={minPct} capacityL={capacityLitres} />} />

          <Line
            type="monotone"
            dataKey="Habit"
            stroke="#9ca3af"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="4 3"
            activeDot={{ r: 3, strokeWidth: 0, fill: '#9ca3af' }}
          />

          <Line
            type="monotone"
            dataKey="Timer"
            stroke="#2d7da8"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="6 3"
            activeDot={{ r: 3, strokeWidth: 0, fill: '#2d7da8' }}
          />

          <Line
            type="monotone"
            dataKey="Optimizer"
            stroke="#2d5a34"
            strokeWidth={2.4}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0, fill: '#2d5a34' }}
          />
        </LineChart>
      </ResponsiveContainer>

      <div
        style={{
          display: 'flex',
          gap: 18,
          marginTop: 10,
          paddingLeft: 28,
          fontSize: '11px',
          fontFamily: 'IBM Plex Mono, monospace',
          color: '#6e6e73',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 16, height: 2, background: '#9ca3af', borderTop: '2px dashed #9ca3af' }} />
          <span>Habit Baseline</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 16, height: 2, background: '#2d7da8', borderTop: '2px dashed #2d7da8' }} />
          <span>Timer Window</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 16, height: 3, background: '#2d5a34', borderRadius: 1 }} />
          <span style={{ color: '#2d5a34', fontWeight: 600 }}>Optimizer</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
          <div style={{ width: 10, height: 2, background: '#d13b3b' }} />
          <span style={{ color: '#d13b3b' }}>Min Safety: {minPct.toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
};
