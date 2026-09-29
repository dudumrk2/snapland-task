# ADR 004: Projections and Satellite Source

## Status
Accepted

## Context
Snapland requires a satellite basemap for drawing and analyzing geographic polygons over Israel. The initial design considered using the Israeli `govmap.gov.il` tiles (`https://cdnil.govmap.gov.il/xyz/heb/{z}/{x}/{y}.png`) as the primary satellite imagery source. Phase 1 required verification of the endpoint, imagery type, CRS, and constraints.

## Findings
During Phase 1 verification, the following was found regarding the proposed govmap XYZ endpoint:
- **Imagery Type**: The endpoint `https://cdnil.govmap.gov.il/xyz/heb/{z}/{x}/{y}.png` returns a standard street/administrative basemap (vector-style data rendered as PNG), **not** satellite or aerial imagery.
- **Tile Grid & CRS**: The endpoint uses the standard Web Mercator (EPSG:3857) XYZ tile scheme, making it fully compatible with Leaflet without needing custom ITM (EPSG:2039) projection logic.
- **Constraints**: No special CORS or token requirements were observed for this endpoint; it responded with HTTP 200.

Since the goal is to provide a *satellite* layer, and the provided govmap endpoint is a street basemap, we cannot use it for our satellite imagery requirement. 

## Decision
1. We will use the **Esri World Imagery** layer (`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`) as our primary satellite base layer.
2. The Esri layer works natively with Web Mercator (EPSG:3857), avoiding the need to implement custom Leaflet CRS logic (`proj4leaflet`) for an ITM projection. 
3. The frontend `LayerManager` and base layer configurations will default `VITE_SATELLITE_TILE_URL` to the Esri World Imagery URL.
4. Leaflet will continue using EPSG:3857 for display while all geographic data remains in WGS84 (EPSG:4326) for storage and geometry operations. Authoritative area calculation will be performed on the backend using the WGS84 ellipsoid.

## Consequences
- No custom projection code (`proj4`) is required on the frontend.
- We rely on Esri instead of govmap for satellite imagery. This is noted as a known limitation, but it meets the requirement for a functional satellite layer.
