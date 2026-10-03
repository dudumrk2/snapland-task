# Snapland Frontend – Real-Time Collaborative GIS

[![Node.js 20](https://img.shields.io/badge/Node-20-green.svg)](https://nodejs.org/)
[![Vite](https://img.shields.io/badge/Vite-5.2-purple.svg)](https://vitejs.dev/)
[![React](https://img.shields.io/badge/React-18.2-blue.svg)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4-blue.svg)](https://www.typescriptlang.org/)
[![Vitest](https://img.shields.io/badge/Vitest-Coverage_%E2%89%A580%25-brightgreen.svg)](https://vitest.dev/)

The Snapland frontend is a modern, high-performance Single Page Application (SPA) built for real-time collaborative geographic polygon drawing, editing, and spatial analysis over Israel. It features live peer cursor tracking, collaborative drawing previews, authoritative geodesic area synchronization, and conflict resolution powered by Optimistic Concurrency Control (OCC).

---

## 🛠️ Technology Stack

| Layer / Concern | Technology | Purpose |
|---|---|---|
| **Framework** | [React 18](https://reactjs.org/) | Component-driven UI architecture |
| **Language** | [TypeScript 5](https://www.typescriptlang.org/) | Strict static typing and contract validation |
| **Build Tooling** | [Vite 5](https://vitejs.dev/) | Ultra-fast HMR and optimized production bundling |
| **Mapping Engine** | [Leaflet 1.9](https://leafletjs.com/) | Interactive map rendering and custom vector layers |
| **State Management** | [Zustand 4](https://github.com/pmndrs/zustand) | Lightweight, decoupled global reactive stores |
| **Spatial Utilities** | [Turf.js](https://turfjs.org/) (`@turf/area`, `@turf/kinks`) | Client-side live geodesic area estimation and self-intersection detection |
| **Projections** | [Proj4](https://proj4js.org/) | Coordinate transformations (EPSG:4326, EPSG:3857) |
| **Testing** | [Vitest](https://vitest.dev/) + [Happy-DOM](https://github.com/capricorn86/happy-dom) | Fast headless unit testing with V8 coverage |
| **E2E Testing** | [Playwright](https://playwright.dev/) | Cross-browser integration and end-to-end user workflows |

---

## 📂 Architecture & Directory Structure

```
frontend/
├── src/
│   ├── api/                     # REST API client & HTTP endpoints (axios)
│   ├── components/              # Reusable UI & map presentation components
│   │   ├── Map/                 # Interactive Leaflet container & overlays
│   │   ├── Drawing/             # Drawing toolbar, vertex previews, area readout
│   │   ├── Collaboration/       # Remote cursor renderer & peer presence list
│   │   └── Modals/              # OCC Conflict Resolution Dialog
│   ├── hooks/                   # Custom business logic & reactivity hooks
│   │   ├── useDrawing.ts        # Vertex collection, snapping, live area estimation
│   │   └── useWebSocket.ts      # WebSocket lifecycle, ticket auth, reconnection
│   ├── services/
│   │   ├── map/                 # LayerManager (Esri World Imagery + OSM)
│   │   └── websocket/           # WebSocketService (batching, protocol serialization)
│   ├── store/
│   │   ├── areasStore.ts        # Polygons, viewport cache, active selection, OCC
│   │   └── collaborationStore.ts# Online peers, remote cursors, in-flight drafts
│   ├── utils/
│   │   ├── areaCalculation.ts  # Geodesic area calculation helpers
│   │   ├── geoUtils.ts         # Topological validation, bounding boxes, WKT/GeoJSON
│   │   └── escapeHtml.ts        # XSS sanitization for map popups and tooltips
│   ├── App.tsx                  # Root application component
│   └── main.tsx                 # Application bootstrap entry point
├── tests/
│   ├── unit/                    # Vitest unit tests (>= 80% coverage)
│   └── e2e/                     # Playwright end-to-end test scenarios
├── vite.config.ts               # Vite configuration, dev proxy, coverage thresholds
└── package.json                 # Dependencies and NPM lifecycle scripts
```

---

## 🚀 Available Scripts

Run all scripts from the `frontend/` directory:

| Script | Command | Description |
|---|---|---|
| **Development** | `npm run dev` | Starts Vite dev server at `http://localhost:5173` with reverse proxy to backend |
| **Production Build** | `npm run build` | Compiles TypeScript (`tsc`) and generates production bundle in `dist/` |
| **Type Check** | `npm run type-check` | Validates TypeScript types across the entire project (`tsc --noEmit`) |
| **Unit Tests** | `npm run test` | Runs unit tests using Vitest in watch/interactive mode |
| **Test Coverage** | `npm run test:coverage` | Runs unit tests with V8 coverage report; enforces ≥ 80% thresholds |
| **End-to-End Tests** | `npm run test:e2e` | Executes Playwright cross-browser integration tests |

---

## 🗺️ Key Features & Implementation Highlights

### 1. Satellite Imagery & Basemaps (ADR 004)
- **Primary Basemap**: High-resolution **Esri World Imagery** satellite tiles (`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`).
- **Fallback Basemap**: OpenStreetMap standard cartographic layer.
- **Israel Bounding Constraint**: Initial view is centered on central Israel (`[32.0853, 34.7818]`, zoom 10) with map panning clamped to the Israeli region `[34.2, 29.5, 35.8, 33.3]` to optimize viewport spatial caching.

### 2. Live Drawing & Geodesic Calculation
- As users click vertices, the `useDrawing` hook updates the active draft polygon.
- In-flight geodesic area is estimated locally in real-time via `@turf/area` and displayed with an approximate prefix (`≈ 1.42 km²`).
- Upon saving (`DRAW_COMMIT` or `POST /areas`), the backend computes the authoritative area over the WGS84 ellipsoid via PostGIS `ST_Area(geom::geography)` and updates the client store.
- Polygons are validated on the client for self-intersections (`@turf/kinks`) and vertex bounds before network transmission.

### 3. Real-Time Collaboration & Presence
- **Ticket-Based Handshake**: Before opening a WebSocket connection, the client obtains a single-use 30-second ticket via `POST /api/v1/auth/ws-ticket`.
- **Cursor Streaming**: Mouse movements over the map canvas stream at 10 Hz with client-side timestamping.
- **In-Flight Previews**: Uncommitted polygon drafting emits `DRAW_START`, `DRAW_UPDATE`, and `DRAW_CANCEL` deltas, allowing remote peers to view in-progress drafting boundaries in real time.
- **Catch-up Sync**: On reconnect, the client passes `lastEventId` to stream missed mutations from Redis Streams without refetching the entire database.

### 4. Optimistic Concurrency Control (OCC) Handling
When two users edit the same polygon simultaneously, the server rejects conflicting submissions with HTTP `409 CONFLICT`. The frontend intercepts this and opens the **Conflict Resolution Modal**, presenting three resolution pathways:
1. **Accept Remote**: Discards local edits and loads the remote user's latest geometry.
2. **Force Overwrite**: Updates the local draft to the latest remote version number and re-submits.
3. **Save as New**: Keeps local edits and creates a new, independent polygon entity with a unique ID.

---

## 🧪 Testing & Quality Assurance

The frontend enforces strict quality gates in CI:
- **TypeScript**: Zero compiler errors (`tsc --noEmit`).
- **Vitest Coverage**: Minimum 80% line, statement, and function coverage across critical hooks, stores, and utilities.
- Run tests locally with:
  ```bash
  npm run type-check
  npm run test:coverage
  ```
