import React, { useState, useEffect } from 'react';
import type { Area } from '@snapland/shared-types';
import { useAreas } from '../../hooks/useAreas';
import { formatArea } from '../../utils/areaCalculation';

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
  } = useAreas();

  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const isEditingThis = editingAreaId === area.id;

  useEffect(() => {
    if (showHistory) {
      fetchHistory(area.id);
    }
  }, [showHistory, area.id, fetchHistory]);

  const handleSaveEdit = async () => {
    if (!editedCoordinates) return;
    setIsSaving(true);
    try {
      await updateArea(area.id, {
        coordinates: editedCoordinates,
        version: area.version,
      });
      cancelEditing();
    } catch {
      // Conflict will trigger ConflictDialog
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Are you sure you want to delete "${area.name}"?`)) return;
    setIsDeleting(true);
    try {
      await deleteArea(area.id);
      onClose();
    } finally {
      setIsDeleting(false);
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
              backgroundColor: '#f59e0b',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 600,
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
            backgroundColor: '#fee2e2',
            color: '#dc2626',
            border: 'none',
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 600,
            cursor: isDeleting ? 'wait' : 'pointer',
          }}
        >
          Delete
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
            textAlign: 'left',
          }}
        >
          {showHistory ? 'Hide Version History ▲' : 'Show Version History ▼'}
        </button>

        {showHistory && (
          <div
            style={{
              marginTop: 8,
              padding: 8,
              backgroundColor: '#f9fafb',
              borderRadius: 6,
              fontSize: '11px',
              maxHeight: 120,
              overflowY: 'auto',
            }}
          >
            {history.length === 0 ? (
              <div style={{ color: '#9ca3af' }}>Loading history...</div>
            ) : (
              history.map((ver) => (
                <div
                  key={ver.versionNumber}
                  style={{
                    padding: '4px 0',
                    borderBottom: '1px solid #f3f4f6',
                  }}
                >
                  <strong>v{ver.versionNumber}</strong> by {ver.editedBy} (
                  {ver.changeType}) - {formatArea(ver.areaKm2, false)}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
