import type { Coordinate, BoundingBox } from '@snapland/shared-types';
import L from 'leaflet';

export class ProjectionUtils {
  /**
   * Converts Leaflet LatLng to Coordinate { lat, lng }
   */
  static latLngToCoordinate(latLng: L.LatLng): Coordinate {
    return {
      lat: latLng.lat,
      lng: latLng.lng,
    };
  }

  /**
   * Converts Coordinate { lat, lng } to Leaflet LatLng
   */
  static coordinateToLatLng(coord: Coordinate): L.LatLng {
    return L.latLng(coord.lat, coord.lng);
  }

  /**
   * Converts Coordinate array to Leaflet LatLngExpression array [lat, lng]
   */
  static coordinatesToLatLngExpression(coords: Coordinate[]): [number, number][] {
    return coords.map((c) => [c.lat, c.lng]);
  }

  /**
   * Converts Leaflet LatLngBounds to BoundingBox { minLng, minLat, maxLng, maxLat }
   */
  static latLngBoundsToBoundingBox(bounds: L.LatLngBounds): BoundingBox {
    return {
      minLng: bounds.getWest(),
      minLat: bounds.getSouth(),
      maxLng: bounds.getEast(),
      maxLat: bounds.getNorth(),
    };
  }

  /**
   * Converts BoundingBox to Leaflet LatLngBounds
   */
  static boundingBoxToLatLngBounds(box: BoundingBox): L.LatLngBounds {
    return L.latLngBounds(
      L.latLng(box.minLat, box.minLng),
      L.latLng(box.maxLat, box.maxLng)
    );
  }

  /**
   * Converts Coordinate { lat, lng } to GeoJSON point tuple [lng, lat]
   */
  static coordinateToGeoJsonPoint(coord: Coordinate): [number, number] {
    return [coord.lng, coord.lat];
  }

  /**
   * Converts GeoJSON point tuple [lng, lat] to Coordinate { lat, lng }
   */
  static geoJsonPointToCoordinate(point: [number, number]): Coordinate {
    return {
      lng: point[0],
      lat: point[1],
    };
  }
}
