import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import type { Coordinate } from '@snapland/shared-types';
import { useAreasStore } from '../../store/areasStore';

export interface VertexEditorProps {
  map: L.Map | null;
}

export const VertexEditor: React.FC<VertexEditorProps> = ({ map }) => {
  const { editingAreaId, editedCoordinates, setEditedCoordinates } =
    useAreasStore();

  const layerGroupRef = useRef<L.LayerGroup | null>(null);
  const previewPolygonRef = useRef<L.Polygon | null>(null);

  // Initialize LayerGroup and cleanup everything on unmount
  useEffect(() => {
    if (!map) return;

    const group = L.layerGroup();
    group.addTo(map);
    layerGroupRef.current = group;

    return () => {
      if (previewPolygonRef.current && map.hasLayer(previewPolygonRef.current)) {
        map.removeLayer(previewPolygonRef.current);
        previewPolygonRef.current = null;
      }
      if (map && map.hasLayer(group)) {
        map.removeLayer(group);
      }
    };
  }, [map]);

  // Render draggable markers for each vertex
  useEffect(() => {
    if (!map || !layerGroupRef.current) return;

    const group = layerGroupRef.current;
    group.clearLayers();

    if (!editingAreaId || !editedCoordinates || editedCoordinates.length === 0) {
      if (previewPolygonRef.current && map.hasLayer(previewPolygonRef.current)) {
        map.removeLayer(previewPolygonRef.current);
        previewPolygonRef.current = null;
      }
      return;
    }

    // 1. Create or update preview polygon in drawingPane
    const latLngs: [number, number][] = editedCoordinates.map((c) => [
      c.lat,
      c.lng,
    ]);

    if (!previewPolygonRef.current) {
      previewPolygonRef.current = L.polygon(latLngs, {
        pane: 'drawingPane',
        color: '#f59e0b',
        weight: 2,
        dashArray: '4, 4',
        fillColor: '#fbbf24',
        fillOpacity: 0.25,
        interactive: false,
      }).addTo(map);
    } else {
      previewPolygonRef.current.setLatLngs(latLngs);
    }

    // 2. Create custom draggable L.marker with L.divIcon for each vertex
    // (CRITICAL: Do NOT use L.circleMarker which cannot be dragged natively)
    const vertexIcon = L.divIcon({
      className: 'snapland-vertex-handle',
      html: `
        <div style="
          width: 14px;
          height: 14px;
          background-color: #ffffff;
          border: 3px solid #f59e0b;
          border-radius: 50%;
          box-shadow: 0 1px 4px rgba(0,0,0,0.3);
          cursor: grab;
          transform: translate(-50%, -50%);
        "></div>
      `,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });

    editedCoordinates.forEach((coord, index) => {
      const marker = L.marker([coord.lat, coord.lng], {
        icon: vertexIcon,
        draggable: true,
        pane: 'drawingPane',
      });

      marker.on('drag', (e: L.LeafletEvent) => {
        const target = e.target as L.Marker;
        const newLatLng = target.getLatLng();

        // Update preview polygon immediately during drag
        const currentCoords = [...editedCoordinates];
        currentCoords[index] = { lat: newLatLng.lat, lng: newLatLng.lng };
        if (previewPolygonRef.current) {
          previewPolygonRef.current.setLatLngs(
            currentCoords.map((c) => [c.lat, c.lng])
          );
        }
      });

      marker.on('dragend', (e: L.LeafletEvent) => {
        const target = e.target as L.Marker;
        const newLatLng = target.getLatLng();

        const updated: Coordinate[] = editedCoordinates.map((c, i) =>
          i === index ? { lat: newLatLng.lat, lng: newLatLng.lng } : c
        );

        setEditedCoordinates(updated);
      });

      group.addLayer(marker);
    });
  }, [map, editingAreaId, editedCoordinates, setEditedCoordinates]);

  return null;
};
