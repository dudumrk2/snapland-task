import { useState, useEffect, useCallback, useRef } from 'react';
import type { BoundingBox } from '@snapland/shared-types';
import L from 'leaflet';
import { ProjectionUtils } from '../services/map/ProjectionUtils';

export interface UseMapBoundsOptions {
  onBoundsChange?: (bounds: BoundingBox, zoom: number) => void;
  debounceMs?: number;
}

export function useMapBounds(
  map: L.Map | null,
  options?: UseMapBoundsOptions
) {
  const [bounds, setBounds] = useState<BoundingBox | null>(null);
  const [zoom, setZoom] = useState<number>(13);
  const timerRef = useRef<any>(null);

  const updateBounds = useCallback(() => {
    if (!map) return;

    const leafletBounds = map.getBounds();
    const currentZoom = map.getZoom();
    const box = ProjectionUtils.latLngBoundsToBoundingBox(leafletBounds);

    setBounds(box);
    setZoom(currentZoom);

    if (options?.onBoundsChange) {
      if (timerRef.current) clearTimeout(timerRef.current);
      const delay = options.debounceMs ?? 300;
      if (delay > 0) {
        timerRef.current = setTimeout(() => {
          options.onBoundsChange?.(box, currentZoom);
        }, delay);
      } else {
        options.onBoundsChange(box, currentZoom);
      }
    }
  }, [map, options]);

  useEffect(() => {
    if (!map) return;

    updateBounds();

    map.on('moveend', updateBounds);
    map.on('zoomend', updateBounds);

    return () => {
      map.off('moveend', updateBounds);
      map.off('zoomend', updateBounds);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [map, updateBounds]);

  return {
    bounds,
    zoom,
    updateBounds,
  };
}
