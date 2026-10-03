import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { useAreasStore } from '../../store/areasStore';
import { formatArea } from '../../utils/areaCalculation';
import { escapeHtml } from '../../utils/escapeHtml';

export interface AreaOverlayProps {
  map: L.Map | null;
  isDrawing?: boolean;
}

export const AreaOverlay: React.FC<AreaOverlayProps> = ({ map, isDrawing = false }) => {
  const { areas, selectedAreaId, selectArea } = useAreasStore();
  const polygonsGroupRef = useRef<L.LayerGroup | null>(null);
  const isDrawingRef = useRef(isDrawing);
  isDrawingRef.current = isDrawing;

  // Initialize LayerGroup
  useEffect(() => {
    if (!map) return;

    const group = L.layerGroup().addTo(map);
    polygonsGroupRef.current = group;

    return () => {
      if (map && map.hasLayer(group)) {
        map.removeLayer(group);
      }
    };
  }, [map]);

  // Dynamically toggle pointer-events on polygonsPane without rebuilding layers
  useEffect(() => {
    if (!map) return;
    const pane = map.getPane('polygonsPane');
    if (pane) {
      if (isDrawing) {
        pane.classList.add('snapland-polygons-drawing');
      } else {
        pane.classList.remove('snapland-polygons-drawing');
      }
    }
    return () => {
      if (pane) {
        pane.classList.remove('snapland-polygons-drawing');
      }
    };
  }, [map, isDrawing]);

  // Render polygons in polygonsPane
  useEffect(() => {
    if (!map || !polygonsGroupRef.current) return;

    const group = polygonsGroupRef.current;
    group.clearLayers();

    areas.forEach((area) => {
      if (!area.coordinates || area.coordinates.length < 3) return;

      const isSelected = area.id === selectedAreaId;
      const latLngs: [number, number][] = area.coordinates.map((c) => [
        c.lat,
        c.lng,
      ]);

      const polygon = L.polygon(latLngs, {
        pane: 'polygonsPane', // Dedicated pane (z-index: 450) ensures no flicker or movement
        className: 'leaflet-interactive snapland-area-polygon',
        interactive: true,
        color: isSelected ? '#ef4444' : '#2563eb',
        weight: isSelected ? 3 : 2,
        fillColor: isSelected ? '#f87171' : '#3b82f6',
        fillOpacity: isSelected ? 0.35 : 0.2,
      });

      // Escape area.name to prevent stored XSS vulnerabilities
      const safeName = escapeHtml(area.name);
      const safeArea = escapeHtml(formatArea(area.areaKm2, false));

      polygon.bindTooltip(
        `<strong>${safeName}</strong><br/>${safeArea}`,
        {
          pane: 'polygonsPane',
          direction: 'center',
          className: 'snapland-polygon-tooltip',
        }
      );

      polygon.on('click', (e: L.LeafletMouseEvent) => {
        // While drawing, let map receive the click event instead of selecting area
        if (isDrawingRef.current) {
          return;
        }
        L.DomEvent.stopPropagation(e);
        selectArea(area.id);
      });

      group.addLayer(polygon);
    });
  }, [map, areas, selectedAreaId, selectArea]);

  return null;
};
