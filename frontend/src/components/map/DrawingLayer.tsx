import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { useDrawing, DrawingAbortedError } from '../../hooks/useDrawing';
import { useAreasStore } from '../../store/areasStore';

export interface DrawingLayerProps {
  map: L.Map | null;
  drawingController: ReturnType<typeof useDrawing>;
}

export const DrawingLayer: React.FC<DrawingLayerProps> = ({
  map,
  drawingController,
}) => {
  const {
    isDrawing,
    points,
    cursorPoint,
    approxAreaKm2,
    formattedApproxArea,
    validationError,
    isSaveModalOpen,
    addPoint,
    updateCursorPoint,
    finishDrawing,
    cancelDrawing,
    saveDrawing,
  } = drawingController;

  const isSaving = useAreasStore((s) => s.isSaving);
  const [areaName, setAreaName] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const activeLineRef = useRef<L.Polyline | null>(null);
  const closingLineRef = useRef<L.Polyline | null>(null);
  const vertexMarkersGroupRef = useRef<L.LayerGroup | null>(null);
  const areaTooltipRef = useRef<L.Tooltip | null>(null);

  // Setup layers and panes
  useEffect(() => {
    if (!map) return;

    const group = L.layerGroup().addTo(map);
    vertexMarkersGroupRef.current = group;

    return () => {
      if (map && map.hasLayer(group)) {
        map.removeLayer(group);
      }
    };
  }, [map]);

  // Handle map interaction events for native drawing
  useEffect(() => {
    if (!map) return;

    if (isDrawing) {
      map.doubleClickZoom.disable();

      const handleClick = (e: L.LeafletMouseEvent) => {
        // Prevent click when double clicking
        addPoint({ lat: e.latlng.lat, lng: e.latlng.lng });
      };

      const handleMouseMove = (e: L.LeafletMouseEvent) => {
        updateCursorPoint({ lat: e.latlng.lat, lng: e.latlng.lng });
      };

      const handleDblClick = (e: L.LeafletMouseEvent) => {
        L.DomEvent.stopPropagation(e);
        finishDrawing();
      };

      map.on('click', handleClick);
      map.on('mousemove', handleMouseMove);
      map.on('dblclick', handleDblClick);

      return () => {
        map.off('click', handleClick);
        map.off('mousemove', handleMouseMove);
        map.off('dblclick', handleDblClick);
        map.doubleClickZoom.enable();
      };
    } else {
      map.doubleClickZoom.enable();
    }
  }, [map, isDrawing, addPoint, updateCursorPoint, finishDrawing]);

  // Update in-progress drawing preview lines & tooltip
  useEffect(() => {
    if (!map) return;

    const group = vertexMarkersGroupRef.current;
    if (group) group.clearLayers();

    if (!isDrawing || points.length === 0) {
      if (activeLineRef.current && map.hasLayer(activeLineRef.current)) {
        map.removeLayer(activeLineRef.current);
        activeLineRef.current = null;
      }
      if (closingLineRef.current && map.hasLayer(closingLineRef.current)) {
        map.removeLayer(closingLineRef.current);
        closingLineRef.current = null;
      }
      if (areaTooltipRef.current) {
        map.closeTooltip(areaTooltipRef.current);
        areaTooltipRef.current = null;
      }
      return;
    }

    const clickedLatLngs: [number, number][] = points.map((p) => [p.lat, p.lng]);

    // 1. Line through clicked points
    if (!activeLineRef.current) {
      activeLineRef.current = L.polyline(clickedLatLngs, {
        pane: 'drawingPane',
        color: '#2563eb',
        weight: 3,
        interactive: false,
      }).addTo(map);
    } else {
      activeLineRef.current.setLatLngs(clickedLatLngs);
    }

    // 2. Closing dashed line to cursor and start
    if (cursorPoint && points.length >= 1) {
      const closingLatLngs: [number, number][] = [
        clickedLatLngs[clickedLatLngs.length - 1],
        [cursorPoint.lat, cursorPoint.lng],
        clickedLatLngs[0],
      ];

      if (!closingLineRef.current) {
        closingLineRef.current = L.polyline(closingLatLngs, {
          pane: 'drawingPane',
          color: '#3b82f6',
          weight: 2,
          dashArray: '5, 5',
          interactive: false,
        }).addTo(map);
      } else {
        closingLineRef.current.setLatLngs(closingLatLngs);
      }

      // Live area tooltip at cursor
      if (points.length >= 2 && approxAreaKm2 > 0) {
        const tooltipContent = `${formattedApproxArea}${
          validationError ? ` (${validationError})` : ''
        }`;

        if (!areaTooltipRef.current) {
          areaTooltipRef.current = L.tooltip({
            pane: 'drawingPane',
            permanent: true,
            direction: 'top',
            className: 'live-area-tooltip',
          })
            .setLatLng([cursorPoint.lat, cursorPoint.lng])
            .setContent(tooltipContent)
            .addTo(map);
        } else {
          areaTooltipRef.current
            .setLatLng([cursorPoint.lat, cursorPoint.lng])
            .setContent(tooltipContent);
        }
      }
    }

    // 3. Mark clicked vertices
    const vertexDotIcon = L.divIcon({
      className: 'drawing-vertex-dot',
      html: `
        <div style="
          width: 8px;
          height: 8px;
          background-color: #2563eb;
          border: 2px solid #ffffff;
          border-radius: 50%;
          box-shadow: 0 1px 3px rgba(0,0,0,0.3);
          transform: translate(-50%, -50%);
        "></div>
      `,
      iconSize: [8, 8],
      iconAnchor: [4, 4],
    });

    points.forEach((p) => {
      if (group) {
        group.addLayer(
          L.marker([p.lat, p.lng], {
            icon: vertexDotIcon,
            interactive: false,
            pane: 'drawingPane',
          })
        );
      }
    });
  }, [
    map,
    isDrawing,
    points,
    cursorPoint,
    approxAreaKm2,
    formattedApproxArea,
    validationError,
  ]);

  const handleSaveSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!areaName.trim() || isSaving || isSubmitting) return;

    setSaveError(null);
    setIsSubmitting(true);
    try {
      await saveDrawing(areaName.trim());
      if (isMountedRef.current) {
        setAreaName('');
      }
    } catch (err: unknown) {
      if (isMountedRef.current && !(err instanceof DrawingAbortedError)) {
        const msg = err instanceof Error ? err.message : 'Failed to save area';
        setSaveError(msg);
      }
    } finally {
      if (isMountedRef.current) {
        setIsSubmitting(false);
      }
    }
  };

  return (
    <>
      {/* Drawing Instruction Pill */}
      {isDrawing && (
        <div
          style={{
            position: 'absolute',
            bottom: 24,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 1000,
            backgroundColor: '#1f2937',
            color: '#ffffff',
            padding: '8px 16px',
            borderRadius: 24,
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            fontSize: '13px',
          }}
        >
          <span>
            Click to add points. <strong>Double-click</strong> or press <strong>Enter</strong> to complete.
          </span>
          {points.length >= 2 && (
            <span style={{ color: '#60a5fa', fontWeight: 600 }}>
              {formattedApproxArea}
            </span>
          )}
          {validationError && (
            <span style={{ color: '#f87171', fontWeight: 600 }}>
              {validationError}
            </span>
          )}
          <button
            type="button"
            onClick={cancelDrawing}
            style={{
              padding: '4px 8px',
              backgroundColor: '#ef4444',
              color: '#ffffff',
              border: 'none',
              borderRadius: 12,
              cursor: 'pointer',
              fontSize: '11px',
              fontWeight: 600,
            }}
          >
            Cancel (Esc)
          </button>
        </div>
      )}

      {/* Save Polygon Modal (Required by E2E tests: input[name="areaName"], button /save/i) */}
      {isSaveModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 2000,
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              padding: '24px',
              borderRadius: '12px',
              width: '380px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
            }}
          >
            <h3 style={{ margin: '0 0 16px 0', fontSize: '18px', color: '#111827' }}>
              Save Drawn Polygon
            </h3>
            {saveError && (
              <div
                style={{
                  padding: '8px 12px',
                  backgroundColor: '#fee2e2',
                  color: '#dc2626',
                  borderRadius: '6px',
                  fontSize: '13px',
                  marginBottom: 14,
                }}
              >
                {saveError}
              </div>
            )}
            <form onSubmit={handleSaveSubmit}>
              <div style={{ marginBottom: 16 }}>
                <label
                  htmlFor="areaNameInput"
                  style={{
                    display: 'block',
                    fontSize: '13px',
                    fontWeight: 500,
                    marginBottom: 6,
                    color: '#374151',
                  }}
                >
                  Area Name
                </label>
                <input
                  id="areaNameInput"
                  name="areaName"
                  type="text"
                  placeholder="e.g. Zone A"
                  value={areaName}
                  onChange={(e) => setAreaName(e.target.value)}
                  autoFocus
                  required
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    fontSize: '14px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '8px',
                }}
              >
                <button
                  type="button"
                  onClick={cancelDrawing}
                  disabled={isSaving || isSubmitting}
                  style={{
                    padding: '8px 16px',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    backgroundColor: '#ffffff',
                    color: '#374151',
                    cursor: isSaving || isSubmitting ? 'not-allowed' : 'pointer',
                    fontSize: '14px',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving || isSubmitting || !areaName.trim()}
                  style={{
                    padding: '8px 16px',
                    border: 'none',
                    borderRadius: '6px',
                    backgroundColor: '#2563eb',
                    color: '#ffffff',
                    cursor: isSaving || isSubmitting ? 'wait' : 'pointer',
                    fontSize: '14px',
                    fontWeight: 600,
                  }}
                >
                  {isSaving || isSubmitting ? 'Saving...' : 'Save'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
