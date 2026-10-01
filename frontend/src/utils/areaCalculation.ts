import type { Coordinate } from '@snapland/shared-types';
import turfArea from '@turf/area';
import { polygon as turfPolygon } from '@turf/helpers';
import { toGeoJsonPolygon, removeDuplicateConsecutive } from './geoUtils';

/**
 * Calculates the approximate area of a polygon in square kilometers (km²)
 * using Turf.js spherical calculation.
 */
export function calculatePolygonAreaKm2(coordinates: Coordinate[]): number {
  const clean = removeDuplicateConsecutive(coordinates);
  if (clean.length < 3) return 0;

  try {
    const geojson = toGeoJsonPolygon(clean);
    const feature = turfPolygon(geojson.coordinates);
    const areaM2 = turfArea(feature);
    const areaKm2 = areaM2 / 1_000_000;
    return Math.round(areaKm2 * 1000) / 1000; // 3 decimal places
  } catch {
    return 0;
  }
}

/**
 * Formats area value for display.
 * @param areaKm2 Area in square kilometers
 * @param isApprox Whether this is a client-side Turf estimate (prepends "≈ ")
 */
export function formatArea(areaKm2: number, isApprox = false): string {
  if (areaKm2 <= 0) return isApprox ? '≈ 0 km²' : '0 km²';

  let formatted: string;
  if (areaKm2 < 0.01) {
    formatted = '< 0.01';
  } else if (areaKm2 < 10) {
    formatted = areaKm2.toFixed(3);
  } else if (areaKm2 < 100) {
    formatted = areaKm2.toFixed(2);
  } else {
    formatted = areaKm2.toLocaleString('en-US', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 2,
    });
  }

  return isApprox ? `≈ ${formatted} km²` : `${formatted} km²`;
}
