/**
 * SolarLoadChart — overlays the 96-interval solar generation profile (kW)
 * and water demand profile (litres/15-min) on an area chart.
 * Features synchronized time cursor, peak solar annotation, and responsive layout.
 */
import React, { useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

interface SolarLoadChartProps {
  solarKw: number[];
  demandLitres: number[];
  pumpSchedule?: number[];
  currentInterval?: number;
}

/** Convert interval index (0-95) to "HH:MM" label */
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
}> = ({ active, payload, label }) => {
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
        const isDemand = p.name.includes('Demand');
        const unit = isDemand ? ' L / 15m' : ' kW';
        const displayVal = isDemand ? p.value.toFixed(0) : p.value.toFixed(2);
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
            <span>{isDemand ? 'Water Demand' : 'Solar Generation'}</span>
            <span style={{ fontWeight: 600 }}>
              {displayVal}
              {unit}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export const SolarLoadChart: React.FC<SolarLoadChartProps> = ({
  solarKw,
  demandLitres,
  pumpSchedule,
  currentInterval,
}) => {
  const data = useMemo(() => {
    return solarKw.map((solar, i) => ({
      time: intervalToTime(i),
      interval: i,
      'Solar (kW)': parseFloat((solar ?? 0).toFixed(2)),
      'Demand (Litres)': parseFloat((demandLitres[i] ?? 0).toFixed(1)),
      pumpOn: pumpSchedule ? pumpSchedule[i] === 1 : false,
    }));
  }, [solarKw, demandLitres, pumpSchedule]);

  // Find peak solar interval
  const peakSolar = Math.max(...solarKw, 0);
  const peakIdx = solarKw.indexOf(peakSolar);

  // X-axis ticks — every 3 hours (every 12th interval)
  const xTicks = [0, 12, 24, 36, 48, 60, 72, 84, 95].map(intervalToTime);

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 12, right: 16, left: -6, bottom: 0 }}>
          <defs>
            <linearGradient id="solarGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#e8a020" stopOpacity=".4" />
              <stop offset="100%" stopColor="#e8a020" stopOpacity=".02" />
            </linearGradient>
            <linearGradient id="demandGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2d7da8" stopOpacity=".25" />
              <stop offset="100%" stopColor="#2d7da8" stopOpacity=".02" />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="2 4" stroke="#ece9e4" vertical={false} />

          <XAxis
            dataKey="time"
            ticks={xTicks}
            tick={{ fontSize: 10, fontFamily: 'IBM Plex Mono, monospace', fill: '#6e6e73' }}
            axisLine={{ stroke: '#dedad4' }}
            tickLine={false}
          />

          <YAxis
            yAxisId="solar"
            tick={{ fontSize: 10, fontFamily: 'IBM Plex Mono, monospace', fill: '#6e6e73' }}
            axisLine={false}
            tickLine={false}
            width={38}
            unit="kW"
          />

          <YAxis
            yAxisId="demand"
            orientation="right"
            tick={{ fontSize: 9, fontFamily: 'IBM Plex Mono, monospace', fill: '#2d7da8' }}
            axisLine={false}
            tickLine={false}
            width={38}
            unit="L"
          />

          <Tooltip content={<CustomTooltip />} />

          {/* Peak Solar Annotation */}
          {peakSolar > 0.5 && (
            <ReferenceLine
              yAxisId="solar"
              x={intervalToTime(peakIdx)}
              stroke="#e8a020"
              strokeWidth={1}
              strokeDasharray="3 3"
              label={{
                value: `Peak ${peakSolar.toFixed(1)}kW`,
                fontSize: 9,
                fill: '#9a6800',
                fontFamily: 'IBM Plex Mono, monospace',
                position: 'insideTopLeft',
              }}
            />
          )}

          {/* Synchronized Current Inspection Cursor */}
          {currentInterval !== undefined && (
            <ReferenceLine
              yAxisId="solar"
              x={intervalToTime(currentInterval)}
              stroke="#2d5a34"
              strokeWidth={1.5}
              strokeDasharray="2 2"
              label={{
                value: intervalToTime(currentInterval),
                fontSize: 9,
                fill: '#2d5a34',
                fontFamily: 'IBM Plex Mono, monospace',
                position: 'top',
              }}
            />
          )}

          <Area
            yAxisId="solar"
            type="monotone"
            dataKey="Solar (kW)"
            stroke="#e8a020"
            strokeWidth={2}
            fill="url(#solarGrad)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0, fill: '#e8a020' }}
          />

          <Area
            yAxisId="demand"
            type="monotone"
            dataKey="Demand (Litres)"
            stroke="#2d7da8"
            strokeWidth={1.5}
            fill="url(#demandGrad)"
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0, fill: '#2d7da8' }}
            strokeDasharray="4 3"
          />
        </AreaChart>
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
          <div style={{ width: 18, height: 3, background: '#e8a020', borderRadius: 1 }} />
          <span>Solar PV Actual (kW)</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div
            style={{
              width: 18,
              height: 2,
              background: '#2d7da8',
              borderTop: '2px dashed #2d7da8',
              borderRadius: 1,
            }}
          />
          <span>Water Demand Actual (Litres/15-min)</span>
        </div>
        {currentInterval !== undefined && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
            <div style={{ width: 10, height: 10, background: '#eaf4eb', border: '1px solid #2d5a34', borderRadius: 2 }} />
            <span style={{ color: '#2d5a34', fontWeight: 500 }}>
              Inspecting: {intervalToTime(currentInterval)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
