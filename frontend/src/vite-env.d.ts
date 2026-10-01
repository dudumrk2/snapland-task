/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SATELLITE_TILE_URL?: string;
  readonly VITE_USE_MOCK_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module '@turf/area' {
  export default function area(geojson: any): number;
}

declare module '@turf/helpers' {
  export function polygon(coordinates: number[][][], properties?: any): any;
}

declare module '@turf/kinks' {
  export default function kinks(polygon: any): { features: any[] };
}
