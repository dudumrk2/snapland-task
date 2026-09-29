import React, { useState } from 'react';
import { useAreas } from '../../hooks/useAreas';
import { formatArea } from '../../utils/areaCalculation';

export const ConflictDialog: React.FC = () => {
  const {
    conflict,
    resolveAcceptRemote,
    resolveForceOverwrite,
    resolveSaveAsNew,
    setConflict,
  } = useAreas();

  const [newAreaName, setNewAreaName] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);

  if (!conflict) return null;

  const { localArea, currentArea } = conflict;

  const handleAcceptRemote = () => {
    resolveAcceptRemote();
  };

  const handleForceOverwrite = async () => {
    setIsProcessing(true);
    try {
      await resolveForceOverwrite();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSaveAsNew = async () => {
    setIsProcessing(true);
    try {
      await resolveSaveAsNew(newAreaName || undefined);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 3000,
      }}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          width: '500px',
          maxWidth: '90vw',
          padding: '24px',
          boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <div
            style={{
              backgroundColor: '#fee2e2',
              color: '#dc2626',
              padding: '8px',
              borderRadius: '50%',
              display: 'flex',
            }}
          >
            ⚠️
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '18px', color: '#111827' }}>
              Edit Conflict Detected (OCC)
            </h3>
            <p style={{ margin: 0, fontSize: '12px', color: '#6b7280' }}>
              Another user updated this area while you were editing.
            </p>
          </div>
        </div>

        {/* Comparison Box */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 12,
            marginBottom: 20,
            fontSize: '13px',
          }}
        >
          <div
            style={{
              padding: 12,
              backgroundColor: '#f9fafb',
              borderRadius: 8,
              border: '1px solid #e5e7eb',
            }}
          >
            <div style={{ fontWeight: 600, color: '#374151', marginBottom: 4 }}>
              Your Local Edit
            </div>
            <div>Version: v{localArea.version}</div>
            <div>Name: {localArea.name}</div>
            <div>Vertices: {localArea.coordinates.length}</div>
          </div>

          <div
            style={{
              padding: 12,
              backgroundColor: '#eff6ff',
              borderRadius: 8,
              border: '1px solid #bfdbfe',
            }}
          >
            <div style={{ fontWeight: 600, color: '#1d4ed8', marginBottom: 4 }}>
              Remote Server State
            </div>
            <div>Version: v{currentArea.version}</div>
            <div>Name: {currentArea.name}</div>
            <div>Area: {formatArea(currentArea.areaKm2, false)}</div>
            <div>Last Edited: {currentArea.lastEditedBy}</div>
          </div>
        </div>

        {/* 3 Resolution Options (HLD §14) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Option 1: Accept Remote */}
          <button
            type="button"
            onClick={handleAcceptRemote}
            disabled={isProcessing}
            style={{
              padding: '10px 16px',
              backgroundColor: '#f3f4f6',
              color: '#374151',
              border: '1px solid #d1d5db',
              borderRadius: 8,
              textAlign: 'left',
              cursor: isProcessing ? 'wait' : 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
            }}
          >
            <strong style={{ fontSize: '14px' }}>Accept Remote</strong>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              Discard your local edits and adopt the latest remote version.
            </span>
          </button>

          {/* Option 2: Force Overwrite */}
          <button
            type="button"
            onClick={handleForceOverwrite}
            disabled={isProcessing}
            style={{
              padding: '10px 16px',
              backgroundColor: '#fee2e2',
              color: '#991b1b',
              border: '1px solid #fca5a5',
              borderRadius: 8,
              textAlign: 'left',
              cursor: isProcessing ? 'wait' : 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
            }}
          >
            <strong style={{ fontSize: '14px' }}>Force Overwrite</strong>
            <span style={{ fontSize: '12px', color: '#b91c1c' }}>
              Overwrite the remote changes with your local geometry (creates v
              {currentArea.version + 1}).
            </span>
          </button>

          {/* Option 3: Save as New */}
          <div
            style={{
              padding: '10px 16px',
              backgroundColor: '#f0fdf4',
              color: '#166534',
              border: '1px solid #bbf7d0',
              borderRadius: 8,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <strong style={{ fontSize: '14px' }}>Save as New</strong>
              <span style={{ fontSize: '12px', color: '#15803d' }}>
                Keep remote changes and save your local geometry as a separate new area.
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                placeholder={`${localArea.name} (Copy)`}
                value={newAreaName}
                onChange={(e) => setNewAreaName(e.target.value)}
                style={{
                  flex: 1,
                  padding: '6px 10px',
                  borderRadius: 6,
                  border: '1px solid #86efac',
                  fontSize: '13px',
                }}
              />
              <button
                type="button"
                onClick={handleSaveAsNew}
                disabled={isProcessing}
                style={{
                  padding: '6px 12px',
                  backgroundColor: '#16a34a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 6,
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: isProcessing ? 'wait' : 'pointer',
                }}
              >
                Save
              </button>
            </div>
          </div>
        </div>

        <div style={{ marginTop: 16, textAlign: 'right' }}>
          <button
            type="button"
            onClick={() => setConflict(null)}
            style={{
              background: 'none',
              border: 'none',
              color: '#6b7280',
              fontSize: '13px',
              cursor: 'pointer',
            }}
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
};
