/**
 * EnergyFlowDiagram — custom SVG engineering illustration showing the building energy system:
 * Rooftop solar panels → Facility distribution → Water Pump → Storage Tank,
 * with utility grid integration as an active fallback.
 *
 * Fully reactive to backend scenario data (clear vs cloudy, solar kW, pump status, grid import, tank level).
 */
import React, { useMemo } from 'react';

export interface EnergyFlowDiagramProps {
  /** Weather condition from current scenario */
  weatherCondition?: 'clear' | 'cloudy';
  /** True when solar generation is active */
  solarActive: boolean;
  /** True when the water pump is running */
  pumpOn: boolean;
  /** True when utility grid is actively importing power */
  gridFallback: boolean;
  /** Real-time solar generation (kW) */
  solarKw?: number;
  /** Rated pump power (kW) */
  pumpKw?: number;
  /** Power imported from grid (kW) */
  gridImportKw?: number;
  /** Solar power surplus (kW) */
  solarSurplusKw?: number;
  /** Tank level in Litres */
  tankLevelLitres?: number;
  /** Tank capacity in Litres */
  tankCapacityLitres?: number;
  /** Minimum allowable safety level in Litres */
  minLevelLitres?: number;
  /** Maximum allowable fill level in Litres */
  maxLevelLitres?: number;
  className?: string;
}

export const EnergyFlowDiagram: React.FC<EnergyFlowDiagramProps> = ({
  weatherCondition = 'clear',
  solarActive,
  pumpOn,
  gridFallback,
  solarKw = 0,
  pumpKw = 5.0,
  gridImportKw = 0,
  solarSurplusKw = 0,
  tankLevelLitres = 6000,
  tankCapacityLitres = 10000,
  minLevelLitres = 2000,
  maxLevelLitres = 10000,
  className = '',
}) => {
  // Normalize tank level to 0..100 percentage
  const levelPct = useMemo(() => {
    if (tankCapacityLitres <= 0) return 50;
    const raw = (tankLevelLitres / tankCapacityLitres) * 100;
    return Math.max(0, Math.min(100, Math.round(raw)));
  }, [tankLevelLitres, tankCapacityLitres]);

  const minLevelPct = (minLevelLitres / tankCapacityLitres) * 100;
  const maxLevelPct = (maxLevelLitres / tankCapacityLitres) * 100;

  // Tank fill calculations for SVG height (tank height is 64px, bottom y = 236)
  const tankInnerHeight = 60;
  const fillHeight = Math.round((levelPct / 100) * tankInnerHeight);
  const fillY = 236 - fillHeight;

  // Water safety status
  const isTankLow = levelPct < minLevelPct;
  const isTankFull = levelPct >= maxLevelPct;
  const currentVolumeKL = (tankLevelLitres / 1000).toFixed(1);

  // Power breakdown when pump is running
  const pumpEffectiveKw = pumpOn ? pumpKw : 0;
  const activeSolarToPumpKw = pumpOn ? Math.min(solarKw, pumpKw) : 0;
  const activeGridToPumpKw = pumpOn ? Math.max(0, pumpKw - solarKw) : 0;
  const isHybridPower = pumpOn && activeSolarToPumpKw > 0.1 && activeGridToPumpKw > 0.1;
  const isPureSolar = pumpOn && activeSolarToPumpKw >= pumpKw - 0.05;

  const isCloudy = weatherCondition === 'cloudy';

  return (
    <div className={`energy-flow-wrap ${className}`}>
      <div className="energy-flow-svg-container">
        <svg
          viewBox="0 0 350 370"
          xmlns="http://www.w3.org/2000/svg"
          role="img"
          aria-label="Schematic diagram of rooftop solar, building distribution, utility grid fallback, pump, and water tank"
          className="energy-flow-svg"
          style={{ width: '100%', height: 'auto', display: 'block' }}
        >
          <defs>
            {/* Gradients */}
            <linearGradient id="ef-solar-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1a2e1f" />
              <stop offset="100%" stopColor="#2d5a34" />
            </linearGradient>

            <linearGradient id="ef-sky-clear" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f3efe6" />
              <stop offset="100%" stopColor="#f6f4f0" />
            </linearGradient>

            <linearGradient id="ef-sky-cloudy" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#e5e7eb" />
              <stop offset="100%" stopColor="#f3f4f6" />
            </linearGradient>

            <linearGradient id="ef-water-normal" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7ec8e3" stopOpacity=".95" />
              <stop offset="100%" stopColor="#2d7da8" stopOpacity=".98" />
            </linearGradient>

            <linearGradient id="ef-water-low" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f87171" stopOpacity=".9" />
              <stop offset="100%" stopColor="#d13b3b" stopOpacity=".95" />
            </linearGradient>

            <clipPath id="ef-tank-clip">
              <rect x="236" y="174" width="68" height="62" rx="3" />
            </clipPath>
          </defs>

          {/* ── Background canvas ─────────────────────────────────── */}
          <rect x="0" y="0" width="350" height="370" fill="#fcfbf9" rx="6" />
          <rect
            x="0"
            y="0"
            width="350"
            height="115"
            fill={isCloudy ? 'url(#ef-sky-cloudy)' : 'url(#ef-sky-clear)'}
            rx="6"
          />

          {/* ── Weather: Sun / Clouds ────────────────────────────── */}
          {isCloudy ? (
            /* Cloudy / Overcast scenario */
            <g id="ef-cloudy-weather">
              {/* Dimmed Sun */}
              <circle cx="282" cy="40" r="16" fill="#fde68a" opacity=".7" />
              {/* Cloud Formation */}
              <path
                d="M 245 48 C 245 40, 252 35, 260 35 C 263 28, 272 25, 280 28 C 286 24, 296 26, 300 32 C 308 32, 314 38, 314 46 C 314 52, 308 56, 300 56 L 254 56 C 248 56, 245 52, 245 48 Z"
                fill="#cbd5e1"
                stroke="#94a3b8"
                strokeWidth="1.2"
                opacity=".9"
              />
              <path
                d="M 230 52 C 230 46, 236 42, 243 42 C 246 36, 254 34, 260 37 C 265 33, 273 35, 277 40 C 283 40, 288 45, 288 51 C 288 56, 283 58, 276 58 L 238 58 C 233 58, 230 55, 230 52 Z"
                fill="#e2e8f0"
                stroke="#cbd5e1"
                strokeWidth="1"
                opacity=".85"
              />
              <text
                x="280"
                y="68"
                textAnchor="middle"
                fontSize="8"
                fontFamily="IBM Plex Mono, monospace"
                fill="#64748b"
                fontWeight="500"
              >
                MONSOON · CLOUDY
              </text>
            </g>
          ) : (
            /* Clear Sky scenario */
            <g id="ef-clear-weather" opacity={solarActive ? 1 : 0.4}>
              <circle cx="280" cy="42" r="20" fill="#fef3c7" />
              <circle cx="280" cy="42" r="14" fill="#f59e0b" />
              {/* Sun rays */}
              {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, i) => {
                const rad = (angle * Math.PI) / 180;
                const x1 = 280 + Math.cos(rad) * 18;
                const y1 = 42 + Math.sin(rad) * 18;
                const x2 = 280 + Math.cos(rad) * 26;
                const y2 = 42 + Math.sin(rad) * 26;
                return (
                  <line
                    key={i}
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    stroke="#f59e0b"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                  />
                );
              })}
              <text
                x="280"
                y="76"
                textAnchor="middle"
                fontSize="8"
                fontFamily="IBM Plex Mono, monospace"
                fill="#9a6800"
                fontWeight="500"
              >
                CLEAR SKY · DIRECT
              </text>
            </g>
          )}

          {/* ── Utility Grid Connection (Left) ────────────────────── */}
          <g id="ef-grid-infrastructure">
            {/* Utility pole */}
            <line x1="28" y1="130" x2="28" y2="210" stroke="#71717a" strokeWidth="2.5" />
            <line x1="16" y1="145" x2="40" y2="145" stroke="#71717a" strokeWidth="2" />
            <line x1="20" y1="160" x2="36" y2="160" stroke="#71717a" strokeWidth="1.5" />
            <circle cx="28" cy="130" r="3.5" fill="#52525b" />
            {/* Transformer drum */}
            <rect x="22" y="165" width="12" height="16" rx="2" fill="#a1a1aa" stroke="#71717a" strokeWidth="1" />

            {/* Grid label badge */}
            <g transform="translate(10, 218)">
              <rect
                x="0"
                y="0"
                width="42"
                height="22"
                rx="3"
                fill={gridFallback ? '#fef2f2' : '#f4f4f5'}
                stroke={gridFallback ? '#f87171' : '#e4e4e7'}
                strokeWidth="1"
              />
              <text
                x="21"
                y="10"
                textAnchor="middle"
                fontSize="7"
                fontFamily="IBM Plex Mono, monospace"
                fill={gridFallback ? '#b91c1c' : '#71717a'}
                fontWeight="600"
              >
                GRID
              </text>
              <text
                x="21"
                y="18"
                textAnchor="middle"
                fontSize="6.5"
                fontFamily="IBM Plex Mono, monospace"
                fill={gridFallback ? '#b91c1c' : '#a1a1aa'}
              >
                {gridFallback ? `${gridImportKw.toFixed(1)} kW` : 'IDLE'}
              </text>
            </g>
          </g>

          {/* ── Building & Rooftop PV Array ───────────────────────── */}
          <g id="ef-building-structure">
            {/* Sloped Roof */}
            <polygon
              points="80,94 175,56 270,94"
              fill="#e7e4dd"
              stroke="#c8c3bb"
              strokeWidth="1.2"
            />

            {/* Solar PV Panels */}
            <g transform="rotate(-18, 120, 72)">
              <rect
                x="94"
                y="58"
                width="34"
                height="22"
                rx="1.5"
                fill="url(#ef-solar-grad)"
                stroke={solarActive ? '#e8a020' : '#2d5a34'}
                strokeWidth="1"
              />
              <line x1="111" y1="58" x2="111" y2="80" stroke="#4ade80" strokeWidth=".8" opacity=".5" />
              <line x1="94" y1="69" x2="128" y2="69" stroke="#4ade80" strokeWidth=".8" opacity=".5" />
            </g>
            <g transform="rotate(-18, 165, 68)">
              <rect
                x="142"
                y="52"
                width="34"
                height="22"
                rx="1.5"
                fill="url(#ef-solar-grad)"
                stroke={solarActive ? '#e8a020' : '#2d5a34'}
                strokeWidth="1"
              />
              <line x1="159" y1="52" x2="159" y2="74" stroke="#4ade80" strokeWidth=".8" opacity=".5" />
              <line x1="142" y1="63" x2="176" y2="63" stroke="#4ade80" strokeWidth=".8" opacity=".5" />
            </g>

            {/* Solar Generation Readout */}
            <g transform="translate(175, 46)">
              <rect
                x="-36"
                y="-11"
                width="72"
                height="16"
                rx="3"
                fill="#ffffff"
                stroke={solarActive ? '#e8a020' : '#dedad4'}
                strokeWidth="1"
              />
              <text
                x="0"
                y="1"
                textAnchor="middle"
                fontSize="8"
                fontFamily="IBM Plex Mono, monospace"
                fill={solarActive ? '#9a6800' : '#a1a1a6'}
                fontWeight="600"
              >
                ☀ {solarKw.toFixed(2)} kW
              </text>
            </g>

            {/* Building Body */}
            <rect
              x="96"
              y="94"
              width="158"
              height="114"
              fill="#f5f3ee"
              stroke="#c8c3bb"
              strokeWidth="1.2"
            />
            {/* Windows */}
            <rect x="114" y="112" width="22" height="18" rx="1.5" fill="#dbeafe" stroke="#bfdbfe" strokeWidth=".8" />
            <rect x="164" y="112" width="22" height="18" rx="1.5" fill="#dbeafe" stroke="#bfdbfe" strokeWidth=".8" />
            <rect x="214" y="112" width="22" height="18" rx="1.5" fill="#dbeafe" stroke="#bfdbfe" strokeWidth=".8" />
            {/* Distribution Box badge */}
            <rect x="150" y="148" width="50" height="26" rx="2" fill="#ffffff" stroke="#c8c3bb" strokeWidth="1" />
            <text
              x="175"
              y="159"
              textAnchor="middle"
              fontSize="6.5"
              fontFamily="IBM Plex Mono, monospace"
              fill="#6e6e73"
              fontWeight="600"
            >
              MAIN BUS
            </text>
            <text
              x="175"
              y="169"
              textAnchor="middle"
              fontSize="6.5"
              fontFamily="IBM Plex Mono, monospace"
              fill={pumpOn ? '#2d5a34' : '#a1a1a6'}
            >
              {pumpOn ? (isPureSolar ? 'SOLAR RUN' : isHybridPower ? 'HYBRID' : 'GRID RUN') : 'STANDBY'}
            </text>
          </g>

          {/* ── Ground Base Line ──────────────────────────────────── */}
          <line x1="15" y1="208" x2="335" y2="208" stroke="#d6d1c8" strokeWidth="1.5" />

          {/* ── Energy Flow Lines (Electrical) ────────────────────── */}
          {/* 1. Solar Panels to Main Bus */}
          <path
            d="M 175 74 L 175 148"
            fill="none"
            stroke={solarActive ? '#e8a020' : '#e5e2da'}
            strokeWidth={solarActive ? 2.5 : 1.5}
            strokeDasharray={solarActive ? '5 5' : 'none'}
            strokeLinecap="round"
            className="energy-flow-path"
          >
            {solarActive && (
              <animate
                attributeName="stroke-dashoffset"
                from="0"
                to="-20"
                dur="1s"
                repeatCount="indefinite"
              />
            )}
          </path>

          {/* 2. Grid Fallback to Main Bus */}
          <path
            d="M 34 165 L 70 165 L 70 162 L 150 162"
            fill="none"
            stroke={gridFallback ? '#d13b3b' : '#dedad4'}
            strokeWidth={gridFallback ? 2.5 : 1}
            strokeDasharray={gridFallback ? '4 4' : '3 3'}
            strokeLinecap="round"
            className="energy-flow-path"
          >
            {gridFallback && (
              <animate
                attributeName="stroke-dashoffset"
                from="0"
                to="-16"
                dur="0.9s"
                repeatCount="indefinite"
              />
            )}
          </path>

          {/* 3. Main Bus to Pump */}
          <path
            d="M 160 174 L 160 196 L 98 196 L 98 226"
            fill="none"
            stroke={
              pumpOn
                ? isPureSolar
                  ? '#2d5a34'
                  : isHybridPower
                  ? '#d97706'
                  : '#d13b3b'
                : '#dedad4'
            }
            strokeWidth={pumpOn ? 2.5 : 1.2}
            strokeDasharray={pumpOn ? '5 5' : 'none'}
            strokeLinecap="round"
            className="energy-flow-path"
          >
            {pumpOn && (
              <animate
                attributeName="stroke-dashoffset"
                from="0"
                to="-20"
                dur="0.8s"
                repeatCount="indefinite"
              />
            )}
          </path>

          {/* ── Water Pump Assembly ─────────────────── */}
          <g id="ef-pump-assembly" transform="translate(98, 240)">
            <circle
              cx="0"
              cy="0"
              r="20"
              fill={pumpOn ? '#eaf4eb' : '#f0ede8'}
              stroke={pumpOn ? '#2d5a34' : '#c8c3bb'}
              strokeWidth="2"
            />
            {/* Impeller Blades */}
            <g
              className={pumpOn ? 'pump-impeller-spinning' : ''}
              style={{ transformOrigin: '0px 0px' }}
            >
              {[0, 90, 180, 270].map((deg, i) => (
                <line
                  key={i}
                  x1="0"
                  y1="0"
                  x2={Math.cos((deg * Math.PI) / 180) * 14}
                  y2={Math.sin((deg * Math.PI) / 180) * 14}
                  stroke={pumpOn ? '#2d5a34' : '#a1a1a6'}
                  strokeWidth="2.5"
                  strokeLinecap="round"
                />
              ))}
              <circle cx="0" cy="0" r="4.5" fill={pumpOn ? '#2d5a34' : '#8e8e93'} />
            </g>

            <text
              x="0"
              y="32"
              textAnchor="middle"
              fontSize="8"
              fontFamily="IBM Plex Mono, monospace"
              fill={pumpOn ? '#2d5a34' : '#71717a'}
              fontWeight="600"
            >
              {pumpOn ? 'PUMP RUNNING' : 'PUMP OFF'}
            </text>
            <text
              x="0"
              y="42"
              textAnchor="middle"
              fontSize="7.5"
              fontFamily="IBM Plex Mono, monospace"
              fill="#6e6e73"
            >
              {pumpOn ? `${pumpEffectiveKw.toFixed(1)} kW` : '0.0 kW'}
            </text>
          </g>

          {/* ── Water Pipe (Pump → Storage Tank) ──────────────────── */}
          <g id="ef-water-pipe">
            <path
              d="M 118 240 L 236 240"
              fill="none"
              stroke="#b8d2e3"
              strokeWidth="7"
              strokeLinecap="round"
            />
            <path
              d="M 118 240 L 236 240"
              fill="none"
              stroke={pumpOn ? '#2d7da8' : '#e0edf4'}
              strokeWidth="3.5"
              strokeDasharray={pumpOn ? '6 6' : 'none'}
              strokeLinecap="round"
              className="water-flow-path"
            >
              {pumpOn && (
                <animate
                  attributeName="stroke-dashoffset"
                  from="0"
                  to="-24"
                  dur="0.9s"
                  repeatCount="indefinite"
                />
              )}
            </path>

            <path
              d="M 236 240 L 244 240 L 244 190 L 254 190"
              fill="none"
              stroke={pumpOn ? '#2d7da8' : '#b8d2e3'}
              strokeWidth="3.5"
              strokeDasharray={pumpOn ? '5 5' : 'none'}
              strokeLinecap="round"
            >
              {pumpOn && (
                <animate
                  attributeName="stroke-dashoffset"
                  from="0"
                  to="-20"
                  dur="0.8s"
                  repeatCount="indefinite"
                />
              )}
            </path>
          </g>

          {/* ── Storage Tank ──────────────────────────────── */}
          <g id="ef-water-tank">
            <rect
              x="236"
              y="174"
              width="68"
              height="64"
              rx="4"
              fill="#ffffff"
              stroke="#a8a29e"
              strokeWidth="1.8"
            />

            <rect
              x="236"
              y={fillY}
              width="68"
              height={fillHeight}
              fill={isTankLow ? 'url(#ef-water-low)' : 'url(#ef-water-normal)'}
              clipPath="url(#ef-tank-clip)"
            />

            {pumpOn && (
              <ellipse
                cx="270"
                cy={fillY + 1}
                rx="24"
                ry="3"
                fill="#ffffff"
                opacity=".35"
              >
                <animate
                  attributeName="rx"
                  values="18;28;18"
                  dur="1.6s"
                  repeatCount="indefinite"
                />
              </ellipse>
            )}

            {/* Max limit line */}
            <line
              x1="236"
              y1={236 - Math.round((maxLevelPct / 100) * tankInnerHeight)}
              x2="304"
              y2={236 - Math.round((maxLevelPct / 100) * tankInnerHeight)}
              stroke="#2d7da8"
              strokeWidth="1"
              strokeDasharray="2 3"
              opacity=".7"
            />
            {/* Min safety limit line */}
            <line
              x1="236"
              y1={236 - Math.round((minLevelPct / 100) * tankInnerHeight)}
              x2="304"
              y2={236 - Math.round((minLevelPct / 100) * tankInnerHeight)}
              stroke="#d13b3b"
              strokeWidth="1.2"
              strokeDasharray="3 3"
              opacity=".9"
            />

            <text
              x="270"
              y="167"
              textAnchor="middle"
              fontSize="8"
              fontFamily="IBM Plex Mono, monospace"
              fill="#52525b"
              fontWeight="600"
              letterSpacing=".5"
            >
              STORAGE TANK
            </text>

            <g transform="translate(270, 252)">
              <text
                x="0"
                y="0"
                textAnchor="middle"
                fontSize="9"
                fontFamily="IBM Plex Mono, monospace"
                fill={isTankLow ? '#d13b3b' : isTankFull ? '#2d7da8' : '#2d5a34'}
                fontWeight="600"
              >
                {levelPct}% ({currentVolumeKL} kL)
              </text>
              <text
                x="0"
                y="10"
                textAnchor="middle"
                fontSize="7"
                fontFamily="IBM Plex Mono, monospace"
                fill={isTankLow ? '#b91c1c' : '#71717a'}
              >
                {isTankLow ? '⚠ BELOW SAFETY MIN' : isTankFull ? 'MAX CAPACITY' : 'RESERVE HEALTHY'}
              </text>
            </g>
          </g>

          <text
            x="175"
            y="312"
            textAnchor="middle"
            fontSize="8"
            fontFamily="IBM Plex Mono, monospace"
            fill="#a1a1aa"
            letterSpacing=".8"
          >
            NEERURJA · REAL-TIME SYSTEM FLOW
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="flow-legend">
        <div className="flow-legend-item">
          <div
            className="flow-legend-line"
            style={{
              background: solarActive ? '#e8a020' : '#d4d4d8',
              boxShadow: solarActive ? '0 0 6px #fde047' : 'none',
            }}
          />
          <span>
            Solar:{' '}
            <strong style={{ color: solarActive ? '#9a6800' : 'inherit' }}>
              {solarKw.toFixed(2)} kW
            </strong>
          </span>
        </div>

        <div className="flow-legend-item">
          <div
            className="flow-legend-line"
            style={{
              background: pumpOn ? (isPureSolar ? '#2d5a34' : isHybridPower ? '#d97706' : '#d13b3b') : '#d4d4d8',
            }}
          />
          <span>
            Pump:{' '}
            <strong style={{ color: pumpOn ? '#2d5a34' : 'inherit' }}>
              {pumpOn ? `${pumpEffectiveKw.toFixed(1)} kW (${isPureSolar ? 'Solar' : isHybridPower ? 'Hybrid' : 'Grid'})` : 'Off'}
            </strong>
          </span>
        </div>

        <div className="flow-legend-item">
          <div
            className="flow-legend-line"
            style={{
              background: gridFallback ? '#d13b3b' : '#d4d4d8',
            }}
          />
          <span>
            Grid Import:{' '}
            <strong style={{ color: gridFallback ? '#d13b3b' : 'inherit' }}>
              {gridFallback ? `${gridImportKw.toFixed(1)} kW` : '0 kW'}
            </strong>
          </span>
        </div>

        <div className="flow-legend-item">
          <div
            className="flow-legend-line"
            style={{
              background: isTankLow ? '#d13b3b' : '#2d7da8',
            }}
          />
          <span>
            Tank:{' '}
            <strong style={{ color: isTankLow ? '#d13b3b' : '#2d7da8' }}>
              {levelPct}% ({currentVolumeKL} kL)
            </strong>
          </span>
        </div>
      </div>
    </div>
  );
};
