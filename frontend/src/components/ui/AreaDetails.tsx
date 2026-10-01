import React, { useState, useEffect } from 'react';
import type { Area } from '@snapland/shared-types';
import { useAreas } from '../../hooks/useAreas';
import { formatArea } from '../../utils/areaCalculation';
import { ConflictError } from '../../api/interfaces/IAreaApi';

export interface AreaDetailsProps {
  area: Area;
  onClose: () => void;
}

export const AreaDetails: React.FC<AreaDetailsProps> = ({ area, onClose }) => {
  const {
    editingAreaId,
    editedCoordinates,
    startEditing,
    cancelEditing,
    updateArea,
    deleteArea,
    history,
    fetchHistory,
    isSaving,
    isDeleting,
  } = useAreas();

  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const isEditingThis = editingAreaId === area.id;

  useEffect(() => {
    if (showHistory) {
      setIsLoadingHistory(true);
      fetchHistory(area.id).finally(() => {
        setIsLoadingHistory(false);
      });
    }
  }, [showHistory, area.id, fetchHistory]);

  const handleSaveEdit = async () => {
    if (!editedCoordinates) return;
    setLocalError(null);
    try {
      await updateArea(area.id, {
        coordinates: editedCoordinates,
        version: area.version,
      });
      cancelEditing();
    } catch (err: unknown) {
      // Non-conflict errors are displayed locally (ConflictError handled by OCC dialog)
      if (!(err instanceof ConflictError)) {
        const msg = err instanceof Error ? err.message : 'Failed to save vertices';
        setLocalError(msg);
      }
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Are you sure you want to delete "${area.name}"?`)) return;
    setLocalError(null);
    try {
      await deleteArea(area.id);
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete area';
      setLocalError(msg);
    }
  };

  return (
    <div
      style={{
        borderTop: '1px solid #e5e7eb',
        paddingTop: 16,
        marginTop: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600 }}>
          {area.name}
        </h4>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close details"
          style={{
            border: 'none',
            background: 'none',
            fontSize: '18px',
            cursor: 'pointer',
            color: '#9ca3af',
          }}
        >
          ×
        </button>
      </div>

      {localError && (
        <div
          style={{
            padding: '8px 10px',
            backgroundColor: '#fee2e2',
            color: '#dc2626',
            borderRadius: '6px',
            fontSize: '12px',
          }}
        >
          {localError}
        </div>
      )}

      <div style={{ fontSize: '13px', color: '#4b5563', lineHeight: '1.6' }}>
        <div>
          <strong>Authoritative Area:</strong> {formatArea(area.areaKm2, false)}
        </div>
        <div>
          <strong>Version:</strong> v{area.version}
        </div>
        <div>
          <strong>Vertices:</strong> {area.coordinates?.length || 0}
        </div>
        <div>
          <strong>Last Edited:</strong>{' '}
          {new Date(area.updatedAt).toLocaleTimeString()}
        </div>
      </div>

      {/* Editing Controls */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {isEditingThis ? (
          <>
            <button
              type="button"
              onClick={handleSaveEdit}
              disabled={isSaving}
              style={{
                flex: 1,
                padding: '6px 12px',
                backgroundColor: '#10b981',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: isSaving ? 'wait' : 'pointer',
              }}
            >
              {isSaving ? 'Saving...' : 'Save Vertices'}
            </button>
            <button
              type="button"
              onClick={cancelEditing}
              style={{
                padding: '6px 12px',
                backgroundColor: '#f3f4f6',
                color: '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => startEditing(area.id)}
            style={{
              flex: 1,
              padding: '6px 12px',
              backgroundColor: '#3b82f6',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Edit Vertices
          </button>
        )}

        <button
          type="button"
          onClick={handleDelete}
          disabled={isDeleting}
          style={{
            padding: '6px 12px',
            backgroundColor: '#ef4444',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            fontSize: '12px',
            cursor: isDeleting ? 'wait' : 'pointer',
          }}
        >
          {isDeleting ? 'Deleting...' : 'Delete'}
        </button>
      </div>

      {/* History Toggle */}
      <div>
        <button
          type="button"
          onClick={() => setShowHistory(!showHistory)}
          style={{
            background: 'none',
            border: 'none',
            color: '#2563eb',
            fontSize: '12px',
            cursor: 'pointer',
            padding: 0,
            textDecoration: 'underline',
          }}
        >
          {showHistory ? 'Hide Version History' : 'View Version History'}
        </button>

        {showHistory && (
          <div
            style={{
              marginTop: 8,
              maxHeight: '120px',
              overflowY: 'auto',
              fontSize: '11px',
              backgroundColor: '#f9fafb',
              padding: 8,
              borderRadius: 6,
              border: '1px solid #e5e7eb',
            }}
          >
            {isLoadingHistory ? (
              <span style={{ color: '#9ca3af' }}>Loading history...</span>
            ) : history.length === 0 ? (
              <span style={{ color: '#9ca3af' }}>No version history available</span>
            ) : (
              history.map((ver) => (
                <div
                  key={ver.versionNumber}
                  style={{
                    padding: '4px 0',
                    borderBottom: '1px solid #f3f4f6',
                    display: 'flex',
                    justifyContent: 'space-between',
                  }}
                >
                  <span>
                    v{ver.versionNumber} ({ver.changeType})
                  </span>
                  <span style={{ color: '#6b7280' }}>
                    {new Date(ver.createdAt).toLocaleTimeString()}
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
