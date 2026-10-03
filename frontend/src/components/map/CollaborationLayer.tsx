import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { useCollaborationStore } from '../../store/collaborationStore';
import { escapeHtml } from '../../utils/escapeHtml';

export interface CollaborationLayerProps {
  map: L.Map | null;
}

export const CollaborationLayer: React.FC<CollaborationLayerProps> = ({
  map,
}) => {
  const { remoteCursors, remoteShapes, connectionState } = useCollaborationStore();
  const cursorsGroupRef = useRef<L.LayerGroup | null>(null);
  const shapesGroupRef = useRef<L.LayerGroup | null>(null);

  // Initialize LayerGroups
  useEffect(() => {
    if (!map) return;

    const cursorsGroup = L.layerGroup().addTo(map);
    const shapesGroup = L.layerGroup().addTo(map);

    cursorsGroupRef.current = cursorsGroup;
    shapesGroupRef.current = shapesGroup;

    return () => {
      if (map) {
        if (map.hasLayer(cursorsGroup)) map.removeLayer(cursorsGroup);
        if (map.hasLayer(shapesGroup)) map.removeLayer(shapesGroup);
      }
    };
  }, [map]);

  // Render Remote Cursors
  useEffect(() => {
    if (!map || !cursorsGroupRef.current) return;
    const group = cursorsGroupRef.current;
    group.clearLayers();

    // Disable remote cursors when degraded in polling mode
    if (connectionState === 'polling') return;

    const now = Date.now();
    const CURSOR_TTL_MS = 30000; // Drop cursors older than 30s

    Object.values(remoteCursors).forEach((cursor) => {
      if (cursor.updatedAt && now - cursor.updatedAt > CURSOR_TTL_MS) {
        return;
      }

      const rawLabel = cursor.displayName || cursor.userId.substring(0, 6);
      const safeLabel = escapeHtml(rawLabel);

      const cursorIcon = L.divIcon({
        className: 'remote-cursor-icon',
        html: `
          <div style="position: relative; pointer-events: none;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="#8b5cf6" stroke="#ffffff" stroke-width="2">
              <path d="M3 3l7 18 3-7 7-3L3 3z"/>
            </svg>
            <div style="
              position: absolute;
              left: 14px;
              top: 14px;
              background-color: #8b5cf6;
              color: #ffffff;
              padding: 2px 6px;
              border-radius: 4px;
              font-size: 11px;
              font-weight: 500;
              white-space: nowrap;
              box-shadow: 0 1px 4px rgba(0,0,0,0.2);
            ">
              ${safeLabel}
            </div>
          </div>
        `,
        iconSize: [24, 24],
        iconAnchor: [0, 0],
      });

      const marker = L.marker([cursor.lat, cursor.lng], {
        icon: cursorIcon,
        pane: 'collaborationPane',
        interactive: false,
      });

      group.addLayer(marker);
    });
  }, [map, remoteCursors, connectionState]);

  // Render Remote Shapes
  useEffect(() => {
    if (!map || !shapesGroupRef.current) return;
    const group = shapesGroupRef.current;
    group.clearLayers();

    // In degraded polling mode, disable remote previews (HLD §9.7 / Task 8)
    if (connectionState === 'polling') return;

    Object.values(remoteShapes).forEach((shape) => {
      if (!shape.points || shape.points.length < 2) return;

      const latLngs: [number, number][] = shape.points.map((p) => [
        p.lat,
        p.lng,
      ]);

      const polyline = L.polyline(latLngs, {
        pane: 'collaborationPane',
        color: '#8b5cf6',
        weight: 2,
        dashArray: '4, 4',
        interactive: false,
      });

      group.addLayer(polyline);
    });
  }, [map, remoteShapes, connectionState]);

  return null;
};
