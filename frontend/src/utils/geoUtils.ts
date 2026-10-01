import type { Coordinate, BoundingBox } from '@snapland/shared-types';
import kinks from '@turf/kinks';
import { polygon as turfPolygon } from '@turf/helpers';

/**
 * Removes consecutive duplicate points within a small tolerance.
 */
export function removeDuplicateConsecutive(
  coordinates: Coordinate[],
  tolerance = 1e-7
): Coordinate[] {
  if (coordinates.length <= 1) return [...coordinates];

  const result: Coordinate[] = [coordinates[0]];
  for (let i = 1; i < coordinates.length; i++) {
    const prev = result[result.length - 1];
    const curr = coordinates[i];
    const distSq =
      Math.pow(prev.lat - curr.lat, 2) + Math.pow(prev.lng - curr.lng, 2);
    if (distSq > tolerance * tolerance) {
      result.push(curr);
    }
  }
  return result;
}

/**
 * Converts open ring coordinates {lat, lng} to GeoJSON Polygon with [lng, lat] closed ring.
 */
export function toGeoJsonPolygon(coordinates: Coordinate[]): {
  type: 'Polygon';
  coordinates: number[][][];
} {
  const clean = removeDuplicateConsecutive(coordinates);
  if (clean.length < 3) {
    throw new Error('Polygon must contain at least 3 distinct vertices');
  }

  const ring: number[][] = clean.map((pt) => [pt.lng, pt.lat]);
  // Ensure ring is closed
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (first[0] !== last[0] || first[1] !== last[1]) {
    ring.push([first[0], first[1]]);
  }

  return {
    type: 'Polygon',
    coordinates: [ring],
  };
}

/**
 * Checks if a polygon has self-intersections using Turf kinks.
 */
export function hasSelfIntersections(coordinates: Coordinate[]): boolean {
  const clean = removeDuplicateConsecutive(coordinates);
  if (clean.length < 4) {
    // A triangle (3 distinct points) cannot self-intersect
    return false;
  }

  try {
    const geojson = toGeoJsonPolygon(clean);
    const feature = turfPolygon(geojson.coordinates);
    const result = kinks(feature);
    return result.features.length > 0;
  } catch {
    return false;
  }
}

/**
 * Validates polygon coordinates according to Snapland rules:
 * - Finite numbers within valid ranges
 * - At least 3 distinct vertices
 * - Maximum 1000 vertices
 * - No self-intersections
 */
export function validatePolygonCoordinates(coordinates: Coordinate[]): {
  valid: boolean;
  reason?: string;
} {
  if (!coordinates || coordinates.length < 3) {
    return { valid: false, reason: 'Polygon must have at least 3 vertices' };
  }

  if (coordinates.length > 1000) {
    return { valid: false, reason: 'Polygon exceeds maximum of 1000 vertices' };
  }

  for (let i = 0; i < coordinates.length; i++) {
    const pt = coordinates[i];
    if (
      !Number.isFinite(pt.lat) ||
      !Number.isFinite(pt.lng) ||
      pt.lat < -90 ||
      pt.lat > 90 ||
      pt.lng < -180 ||
      pt.lng > 180
    ) {
      return { valid: false, reason: `Invalid coordinate at index ${i}` };
    }
  }

  const clean = removeDuplicateConsecutive(coordinates);
  if (clean.length < 3) {
    return { valid: false, reason: 'Polygon must have at least 3 distinct vertices' };
  }

  if (hasSelfIntersections(clean)) {
    return { valid: false, reason: 'Polygon cannot have self-intersections' };
  }

  return { valid: true };
}

/**
 * Checks if a point falls within a bounding box.
 */
export function isPointInBounds(point: Coordinate, bounds: BoundingBox): boolean {
  return (
    point.lng >= bounds.minLng &&
    point.lng <= bounds.maxLng &&
    point.lat >= bounds.minLat &&
    point.lat <= bounds.maxLat
  );
}
