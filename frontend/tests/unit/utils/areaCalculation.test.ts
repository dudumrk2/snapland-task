import { describe, it, expect } from 'vitest';
import {
  calculatePolygonAreaKm2,
  formatArea,
} from '../../../src/utils/areaCalculation';

describe('areaCalculation', () => {
  describe('calculatePolygonAreaKm2', () => {
    it('returns 0 for fewer than 3 vertices', () => {
      expect(calculatePolygonAreaKm2([])).toBe(0);
      expect(
        calculatePolygonAreaKm2([
          { lat: 32.0, lng: 34.0 },
          { lat: 32.1, lng: 34.1 },
        ])
      ).toBe(0);
    });

    it('calculates area for a polygon in Israel within 1% of reference value', () => {
      // ~10 km x ~10 km square near Tel Aviv (~94.2 km² reference area)
      const coords = [
        { lat: 32.0, lng: 34.8 },
        { lat: 32.0, lng: 34.9 },
        { lat: 32.09, lng: 34.9 },
        { lat: 32.09, lng: 34.8 },
      ];
      const area = calculatePolygonAreaKm2(coords);
      // Expected geodesic area is ~94.23 km²
      expect(area).toBeGreaterThan(93.0);
      expect(area).toBeLessThan(95.5);
      expect(Math.abs(area - 94.23) / 94.23).toBeLessThan(0.01);
    });
  });

  describe('formatArea', () => {
    it('formats approx area with ≈ prefix', () => {
      const formatted = formatArea(1.456, true);
      expect(formatted).toBe('≈ 1.456 km²');
    });

    it('formats authoritative area without ≈ prefix', () => {
      const formatted = formatArea(1.456, false);
      expect(formatted).toBe('1.456 km²');
      expect(formatted).not.toContain('≈');
    });

    it('formats small areas accurately', () => {
      const formatted = formatArea(0.004, false);
      expect(formatted).toBe('< 0.01 km²');
    });

    it('formats large areas with locale grouping', () => {
      const formatted = formatArea(1250.5, false);
      expect(formatted).toBe('1,250.5 km²');
    });
  });
});
