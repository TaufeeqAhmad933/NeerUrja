import React from 'react';

export interface MetricCardProps {
  label: string;
  value: string | number | null | undefined;
  unit?: string;
  delta?: string;
  deltaPositive?: boolean;
  icon?: React.ReactNode;
  iconVariant?: 'default' | 'solar' | 'warning' | 'water';
  isEstimate?: boolean;
  subtext?: string;
  className?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  unit,
  delta,
  deltaPositive = true,
  icon,
  iconVariant = 'default',
  isEstimate = false,
  subtext,
  className = '',
}) => {
  const isAvailable = value !== null && value !== undefined && value !== '';

  return (
    <div className={`metric-card ${className}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        {icon && (
          <div className={`metric-card-icon metric-card-icon--${iconVariant}`}>
            {icon}
          </div>
        )}
        {isEstimate && (
          <span
            style={{
              fontSize: '9px',
              fontFamily: 'IBM Plex Mono, monospace',
              color: '#92400e',
              background: '#fef3c7',
              border: '1px solid #fde68a',
              borderRadius: 3,
              padding: '1px 5px',
              textTransform: 'uppercase',
            }}
          >
            Preview
          </span>
        )}
      </div>

      <div className="metric-card-label">{label}</div>

      <div className="metric-card-value">
        {isAvailable ? (
          <>
            {value}
            {unit && <span>{unit}</span>}
          </>
        ) : (
          <span style={{ fontSize: '1rem', color: '#a1a1aa' }}>Unavailable</span>
        )}
      </div>

      {delta && isAvailable && (
        <div
          className={`metric-card-delta${
            !deltaPositive ? ' metric-card-delta--negative' : ''
          }`}
        >
          {delta}
        </div>
      )}

      {subtext && (
        <div style={{ fontSize: '11px', color: '#71717a', marginTop: 2 }}>
          {subtext}
        </div>
      )}
    </div>
  );
};
