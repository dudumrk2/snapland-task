import React, { useState } from 'react';
import { useAreas } from '../../hooks/useAreas';
import { AreaList } from './AreaList';
import { AreaDetails } from './AreaDetails';

export interface AreaPanelProps {
  isDrawing: boolean;
  onStartDrawing: () => void;
  onCancelDrawing: () => void;
}

export const AreaPanel: React.FC<AreaPanelProps> = ({
  isDrawing,
  onStartDrawing,
  onCancelDrawing,
}) => {
  const { areas, selectedArea, selectedAreaId, selectArea } = useAreas();
  const [searchQuery, setSearchQuery] = useState('');

  const filteredAreas = areas.filter((a) =>
    a.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div
      style={{
        position: 'absolute',
        top: 64,
        right: 16,
        width: 320,
        maxHeight: 'calc(100vh - 84px)',
        backgroundColor: '#ffffff',
        borderRadius: 12,
        boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        padding: 16,
        boxSizing: 'border-box',
      }}
    >
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12,
        }}
      >
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#111827' }}>
          Areas
        </h2>
        <span
          style={{
            fontSize: '12px',
            backgroundColor: '#e0e7ff',
            color: '#4338ca',
            padding: '2px 8px',
            borderRadius: 12,
            fontWeight: 600,
          }}
        >
          {areas.length} {areas.length === 1 ? 'zone' : 'zones'}
        </span>
      </div>

      {/* Primary Action Button: Draw Polygon */}
      <div style={{ marginBottom: 12 }}>
        {isDrawing ? (
          <button
            type="button"
            onClick={onCancelDrawing}
            style={{
              width: '100%',
              padding: '10px 14px',
              backgroundColor: '#ef4444',
              color: '#ffffff',
              border: 'none',
              borderRadius: 8,
              fontWeight: 600,
              fontSize: '14px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              transition: 'background-color 0.15s ease',
            }}
          >
            Cancel Drawing
          </button>
        ) : (
          <button
            type="button"
            onClick={onStartDrawing}
            style={{
              width: '100%',
              padding: '10px 14px',
              backgroundColor: '#2563eb',
              color: '#ffffff',
              border: 'none',
              borderRadius: 8,
              fontWeight: 600,
              fontSize: '14px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              transition: 'background-color 0.15s ease',
            }}
          >
            <span>✏️</span> Draw Polygon
          </button>
        )}
      </div>

      {/* Search Input */}
      <div style={{ marginBottom: 12 }}>
        <input
          type="text"
          placeholder="Filter areas by name..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: 6,
            border: '1px solid #d1d5db',
            fontSize: '13px',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Areas List */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <AreaList
          areas={filteredAreas}
          selectedAreaId={selectedAreaId}
          onSelectArea={(id) => selectArea(id === selectedAreaId ? null : id)}
        />
      </div>

      {/* Selected Area Details */}
      {selectedArea && (
        <AreaDetails area={selectedArea} onClose={() => selectArea(null)} />
      )}
    </div>
  );
};
