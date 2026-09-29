import React from 'react';
import type { Area } from '@snapland/shared-types';
import { formatArea } from '../../utils/areaCalculation';

export interface AreaListProps {
  areas: Area[];
  selectedAreaId: string | null;
  onSelectArea: (id: string) => void;
}

export const AreaList: React.FC<AreaListProps> = ({
  areas,
  selectedAreaId,
  onSelectArea,
}) => {
  if (areas.length === 0) {
    return (
      <div
        className="area-list"
        style={{
          padding: '24px 16px',
          textAlign: 'center',
          color: '#6b7280',
          fontSize: '14px',
        }}
      >
        No areas found. Draw a polygon to get started.
      </div>
    );
  }

  return (
    <div
      className="area-list"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        overflowY: 'auto',
        maxHeight: 'calc(100vh - 280px)',
      }}
    >
      {areas.map((area) => {
        const isSelected = area.id === selectedAreaId;
        return (
          <div
            key={area.id}
            onClick={() => onSelectArea(area.id)}
            style={{
              padding: '12px 14px',
              borderRadius: '8px',
              border: isSelected ? '2px solid #2563eb' : '1px solid #e5e7eb',
              backgroundColor: isSelected ? '#eff6ff' : '#ffffff',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span
                style={{
                  fontWeight: 600,
                  fontSize: '14px',
                  color: isSelected ? '#1d4ed8' : '#111827',
                }}
              >
                {area.name}
              </span>
              <span
                style={{
                  fontSize: '11px',
                  color: '#6b7280',
                  backgroundColor: '#f3f4f6',
                  padding: '2px 6px',
                  borderRadius: '4px',
                }}
              >
                v{area.version}
              </span>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontSize: '12px',
                color: '#4b5563',
              }}
            >
              <span>{formatArea(area.areaKm2, false)}</span>
              <span style={{ fontSize: '11px', color: '#9ca3af' }}>
                {area.coordinates?.length || 0} vertices
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};
