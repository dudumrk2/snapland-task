import { describe, it, expect } from 'vitest';
import {
  removeDuplicateConsecutive,
  toGeoJsonPolygon,
  hasSelfIntersections,
  validatePolygonCoordinates,
  isPointInBounds,
} from '../../../src/utils/geoUtils';

describe('geoUtils', () => {
  describe('removeDuplicateConsecutive', () => {
    it('removes consecutive duplicate points within tolerance', () => {
      const coords = [
        { lat: 32.0, lng: 34.0 },
        { lat: 32.0, lng: 34.0 }, // Duplicate
        { lat: 32.1, lng: 34.1 },
        { lat: 32.1, lng: 34.1 }, // Duplicate
        { lat: 32.0, lng: 34.0 }, // Non-consecutive duplicate (valid ring end)
      ];

      const cleaned = removeDuplicateConsecutive(coords);
      expect(cleaned).toHaveLength(3);
      expect(cleaned[0]).toEqual({ lat: 32.0, lng: 34.0 });
      expect(cleaned[1]).toEqual({ lat: 32.1, lng: 34.1 });
      expect(cleaned[2]).toEqual({ lat: 32.0, lng: 34.0 });
    });

    it('returns empty array when given empty input', () => {
      expect(removeDuplicateConsecutive([])).toEqual([]);
    });
  });

  describe('toGeoJsonPolygon', () => {
    it('creates valid GeoJSON polygon with [lng, lat] and closed ring', () => {
      const openRing = [
        { lat: 32.0, lng: 34.0 },
        { lat: 32.0, lng: 34.1 },
        { lat: 32.1, lng: 34.1 },
      ];

      const geojson = toGeoJsonPolygon(openRing);
      expect(geojson.type).toBe('Polygon');
      expect(geojson.coordinates[0]).toHaveLength(4); // Closed ring: 3 points + 1 closing
      expect(geojson.coordinates[0][0]).toEqual([34.0, 32.0]);
      expect(geojson.coordinates[0][3]).toEqual([34.0, 32.0]); // Matches first
    });

    it('throws error when given fewer than 3 distinct vertices', () => {
      expect(() =>
        toGeoJsonPolygon([
          { lat: 32.0, lng: 34.0 },
          { lat: 32.1, lng: 34.1 },
        ])
      ).toThrow();
    });
  });

  describe('hasSelfIntersections', () => {
    it('returns false for simple non-intersecting convex polygon', () => {
      const square = [
        { lat: 32.0, lng: 34.0 },
        { lat: 32.0, lng: 34.1 },
        { lat: 32.1, lng: 34.1 },
        { lat: 32.1, lng: 34.0 },
      ];
      expect(hasSelfIntersections(square)).toBe(false);
    });

    it('returns true for bowtie self-intersecting polygon', () => {
      const bowtie = [
        { lat: 32.0, lng: 34.0 },
        { lat: 32.1, lng: 34.1 },
        { lat: 32.0, lng: 34.1 },
        { lat: 32.1, lng: 34.0 },
      ];
      expect(hasSelfIntersections(bowtie)).toBe(true);
    });
  });

  describe('validatePolygonCoordinates', () => {
    it('validates a correct triangle', () => {
      const triangle = [
        { lat: 32.0, lng: 34.0 },
        { lat: 32.0, lng: 34.2 },
        { lat: 32.2, lng: 34.1 },
      ];
      const result = validatePolygonCoordinates(triangle);
      expect(result.valid).toBe(true);
    });

    it('rejects coordinates with NaN or out-of-range latitude', () => {
      const invalid = [
        { lat: 95.0, lng: 34.0 }, // Lat > 90
        { lat: 32.0, lng: 34.2 },
        { lat: 32.2, lng: 34.1 },
      ];
      const result = validatePolygonCoordinates(invalid);
      expect(result.valid).toBe(false);
      expect(result.reason).toContain('Invalid coordinate');
    });

    it('rejects polygon with self-intersections', () => {
      const bowtie = [
        { lat: 32.0, lng: 34.0 },
        { lat: 32.1, lng: 34.1 },
        { lat: 32.0, lng: 34.1 },
        { lat: 32.1, lng: 34.0 },
      ];
      const result = validatePolygonCoordinates(bowtie);
      expect(result.valid).toBe(false);
      expect(result.reason).toContain('self-intersections');
    });
  });

  describe('isPointInBounds', () => {
    const bbox = { minLng: 34.0, minLat: 31.0, maxLng: 35.5, maxLat: 33.0 };

    it('returns true for point inside bounds', () => {
      expect(isPointInBounds({ lat: 32.0, lng: 34.8 }, bbox)).toBe(true);
    });

    it('returns false for point outside bounds', () => {
      expect(isPointInBounds({ lat: 30.0, lng: 34.8 }, bbox)).toBe(false);
    });
  });
});
