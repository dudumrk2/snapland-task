import { useState, useEffect, useCallback, useRef } from 'react';
import type { BoundingBox } from '@snapland/shared-types';
import L from 'leaflet';
import { ProjectionUtils } from '../services/map/ProjectionUtils';

export interface UseMapBoundsOptions {
  onBoundsChange?: (bounds: BoundingBox, zoom: number) => void;
  debounceMs?: number;
}

function areBoundsEqual(a: BoundingBox | null, b: BoundingBox | null): boolean {
  if (!a || !b) return a === b;
  return (
    Math.abs(a.minLng - b.minLng) < 1e-6 &&
    Math.abs(a.minLat - b.minLat) < 1e-6 &&
    Math.abs(a.maxLng - b.maxLng) < 1e-6 &&
    Math.abs(a.maxLat - b.maxLat) < 1e-6
  );
}

export function useMapBounds(
  map: L.Map | null,
  options?: UseMapBoundsOptions
) {
  const [bounds, setBounds] = useState<BoundingBox | null>(null);
  const [zoom, setZoom] = useState<number>(13);
  const timerRef = useRef<any>(null);

  // Store options in a ref so inline option objects don't trigger re-renders or reset timers
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const updateBounds = useCallback(() => {
    if (!map) return;

    const leafletBounds = map.getBounds();
    const currentZoom = map.getZoom();
    const box = ProjectionUtils.latLngBoundsToBoundingBox(leafletBounds);

    setBounds((prev) => (areBoundsEqual(prev, box) ? prev : box));
    setZoom((prev) => (prev === currentZoom ? prev : currentZoom));

    const currentOptions = optionsRef.current;
    if (currentOptions?.onBoundsChange) {
      if (timerRef.current) clearTimeout(timerRef.current);
      const delay = currentOptions.debounceMs ?? 300;
      if (delay > 0) {
        timerRef.current = setTimeout(() => {
          currentOptions.onBoundsChange?.(box, currentZoom);
        }, delay);
      } else {
        currentOptions.onBoundsChange(box, currentZoom);
      }
    }
  }, [map]);

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
