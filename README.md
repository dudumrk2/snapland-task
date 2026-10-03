# Snapland – Real-Time Collaborative GIS

[![CI](https://github.com/dudumrk2/snapland/actions/workflows/ci.yml/badge.svg)](https://github.com/dudumrk2/snapland/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Node.js 20](https://img.shields.io/badge/Node-20-green.svg)](https://nodejs.org/)

Snapland is a high-performance, real-time collaborative GIS web application designed for simultaneous geographic polygon drawing, editing, and spatial analysis over Israel. Multiple users can concurrently create and edit geographic boundaries on interactive maps while seeing each other's live cursors, in-flight drawing previews, and presence updates with sub-100ms latency.

---

## Architecture Overview

Snapland uses an event-driven, decoupled microservices architecture designed for horizontal scalability, zero-downtime deployments, and robust data integrity:

```mermaid
flowchart TD
    subgraph Clients["Web Clients (React + Leaflet)"]
        C1["User A (Browser)"]
        C2["User B (Browser)"]
    end

    subgraph Edge["Edge Gateway (Nginx)"]
        LB["Nginx Reverse Proxy & Load Balancer\nleast_conn · SSL Termination · Rate Limiting · WS Upgrade"]
    end

    subgraph BackendCluster["Application Tier (Stateless Replicas)"]
        BE1["FastAPI Replica 1\nREST API + WebSocket Manager"]
        BE2["FastAPI Replica 2\nREST API + WebSocket Manager"]
    end

    subgraph RealTimeBus["Real-Time & Caching Tier (Redis 7)"]
        PUB["Redis Pub/Sub\nEphemeral Events (cursors, delta previews)"]
        STR["Redis Streams\nDurable AREA_* Events & Catch-up Replay"]
        PR["Redis Presence (ZSET)\nHeartbeats & Expiration Reaper"]
        CA["Redis L2 Viewport Cache\n0.01° Outward Grid Snapping"]
    end

    subgraph Storage["Data Tier (PostgreSQL 16)"]
    PostgreSQL with PostGIS 3.4
    Spatial GiST Index: areas_geom_gist
    Optimistic Concurrency Control (OCC)
    end

    subgraph Observability["Observability Tier"]
        PROM["Prometheus 2.x\nDNS Service Discovery Scrapes /metrics"]
        GRAF["Grafana 10.x\nPre-provisioned System Dashboard"]
    end

    C1 & C2 <-->|"HTTPS / WSS"| LB
    LB -->|"Round Robin / least_conn"| BE1 & BE2
    BE1 & BE2 <-->|"Publish & Subscribe"| PUB
    BE1 & BE2 <-->|"Append & Stream Follow"| STR
    BE1 & BE2 <-->|"Presence & Cache"| PR & CA
    BE1 & BE2 -->|"Async SQLAlchemy / asyncpg"| PG
    PROM -->|"Scrapes replicas"| BE1 & BE2
    GRAF -->|"PromQL Queries"| PROM
```

Detailed design documentation:
- [High-Level Design Specification (HLD)](docs/hld.md)
- [Architectural Decision Records (ADRs)](docs/adr/)
- [ADR 004: Projections & Satellite Source Findings](docs/adr/004-projections-and-satellite-source.md)
- [Performance & Benchmark Evidence](docs/performance.md)

---

## Quickstart (One Command Deployment)

The entire production stack (PostgreSQL + PostGIS, Redis, database migrations, 2 backend replicas, frontend SPA, Nginx gateway, Prometheus, and Grafana) runs out-of-the-box via Docker Compose.

### Prerequisites
- Docker Engine 24+ and Docker Compose v2+
- Ports 80, 5432, 6379, 9090, 3000 free on the host

### Launching the Stack
From the project root, run:
```bash
docker compose -f infra/docker-compose.yml up -d --build
```
> [!TIP]
> In environments where Docker Compose runs without Swarm mode enabled and ignores `deploy.replicas`, scale the backend replicas explicitly with:
> `docker compose -f infra/docker-compose.yml up -d --build --scale backend=2`

### Access Endpoints
| Component | URL | Credentials / Notes |
|---|---|---|
| **Web Application** | [http://localhost](http://localhost) | Main collaborative map interface |
| **API Swagger Docs** | [http://localhost/docs](http://localhost/docs) | Interactive OpenAPI documentation |
| **API Health Check** | [http://localhost/health/ready](http://localhost/health/ready) | System readiness probe (DB + Redis + Workers) |
| **Prometheus** | [http://localhost:9090](http://localhost:9090) | Metrics scraping engine & target status |
| **Grafana Dashboard** | [http://localhost:3000](http://localhost:3000) | Username: `admin`, Password: `admin` |

> [!WARNING]
> **Production Security Note:** Ports 9090 (Prometheus) and 3000 (Grafana) are exposed for local development and monitoring demonstrations. In shared, staging, or production networks, restrict host port bindings, keep them behind an authenticated reverse proxy, and change default credentials.

### Verifying Service Health
```bash
# Check Docker services status
docker compose -f infra/docker-compose.yml ps

# Test readiness probe via Nginx
curl -i http://localhost/health/ready
```

To stop the stack and clean up containers:
```bash
docker compose -f infra/docker-compose.yml down -v
```

---

## Local Development Setup

For local debugging and active feature development outside Docker:

### 1. Start Infrastructure Dependencies
```bash
# Run PostgreSQL and Redis in background
docker compose -f infra/docker-compose.yml up -d postgres redis
```

### 2. Backend Setup
Requires **Python 3.12+**.
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install dependencies in editable mode
pip install -e backend/
pip install pytest pytest-asyncio pytest-cov httpx fakeredis ruff mypy

# Run database migrations
cd backend
alembic upgrade head

# Start FastAPI server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup
Requires **Node.js 20+**.
```bash
# Install and link shared types package
cd packages/shared-types
npm install

# Install frontend dependencies and launch dev server
cd ../../frontend
npm install
npm run dev
```
The Vite development server runs on `http://localhost:5173` with automatic reverse proxy configured to forward `/api` and `/ws` to `http://localhost:8000`.

---

## Key Technical Decisions & Architecture Highlights

### 1. Decoupled Real-Time Transport (Redis Pub/Sub vs. Redis Streams)
- **Ephemeral Events (Redis Pub/Sub)**: Live cursor movements (`CURSOR_MOVE`) and in-flight drawing previews (`REMOTE_DRAW`) are high-frequency, loss-tolerant messages. They bypass persistent storage and fan out across backend instances via Redis Pub/Sub, with micro-batching (50ms frames) and sender-coalescing to prevent client buffer saturation.
- **Durable Events (Redis Streams)**: Area mutations (`AREA_CREATED`, `AREA_UPDATED`, `AREA_DELETED`) require guaranteed delivery. They are appended to a Redis Stream (`areas:events`) with sequential IDs (`lastEventId`). Connected clients replay missed events upon reconnection without querying the database.

### 2. Multi-Instance Stateless Backend
- Backend instances are completely stateless. A WebSocket connection stays pinned only for network transport to whichever instance accepted it; all state synchronization (presence, live drafts, persistent mutations) occurs through Redis.
- Nginx uses `least_conn` load balancing so traffic dynamically balances across all backend replicas without requiring sticky sessions (`ip_hash`), which degrade behind shared NATs.

### 3. Authoritative Spatial Engine & Projections (ADR-004)
- **Authoritative Geodesic Calculations**: All polygon areas are authoritatively computed on the backend over the WGS84 ellipsoid (`PostGIS geography(Polygon, 4326)`). The frontend shows a real-time approximate calculation during drawing using spherical Turf.js and transitions to the exact server-calculated value upon save.
- **Basemap Findings (ADR-004)**: Investigation of the `cdnil.govmap.gov.il` endpoint revealed it provides administrative vector/street tiles in Web Mercator rather than satellite/aerial imagery. Snapland adopts **Esri World Imagery** as the high-resolution satellite layer, retaining Web Mercator (EPSG:3857) compatibility without custom ITM projection libraries. See [ADR 004](docs/adr/004-projections-and-satellite-source.md).

### 4. Optimistic Concurrency Control (OCC)
- When multiple users attempt to modify the same polygon simultaneously, changes are arbitrated using an integer `version` column:
  ```sql
  UPDATE areas SET geom = :geom, version = version + 1
  WHERE id = :id AND version = :client_version;
  ```
- If another user committed changes first, `rowcount == 0` triggers an HTTP `409 CONFLICT` carrying the current remote version (`details.current_area`). The frontend presents a three-way Conflict Resolution Dialog:
  1. **Accept Remote**: Discard local draft and load the newest remote polygon.
  2. **Force Overwrite**: Re-apply local modifications against the latest version.
  3. **Save as New**: Save local draft as a new polygon entity.

---

## Performance Considerations & Optimizations

Documented and verified under load testing (see [docs/performance.md](docs/performance.md)):

1. **Two-Tier Caching**:
   - **L1 In-Memory LRU**: Caches static JWT public keys and application configurations per replica (30s TTL).
   - **L2 Redis Viewport Cache**: Viewport spatial queries are snapped outward to a 0.01° grid boundary. Results are cached with a 10s TTL and invalidated cluster-wide on any mutation via an atomic `INCR areas:epoch`.
2. **PostGIS GiST Spatial Indexing**:
   - An R-Tree GiST index on `areas(geom)` (`areas_geom_gist`) evaluates bounding box intersections (`ST_Intersects`) in < 15ms for datasets exceeding 100,000 polygons.
3. **Outbound WebSocket Coalescing & Batching**:
   - Cursors are throttled to 10 Hz and coalesced (latest cursor wins per user).
   - Ephemeral previews are packaged into 50ms micro-batch frames, keeping cluster-wide egress at ~2,000 frames/s for 100 active collaborators rather than 114,000 individual frames/s.
4. **Connection Pool Management**:
   - Asynchronous connection pooling via `asyncpg` with per-instance limits and SQL statement timeout hierarchy (`statement_timeout = 25000ms`, route timeout = 30s).

---

## Security Implementation

- **Ticket-Based WebSocket Authentication**:
  - WebSockets do not transmit bearer tokens in query parameters or URL headers.
  - Clients exchange their short-lived access token for a single-use, 30-second ticket via `POST /api/v1/auth/ws-ticket`.
  - The ticket is verified and atomically consumed in Redis via `GETDEL ws_ticket:{ticket}` during the WebSocket upgrade handshake.
- **Nginx Log Sanitization**:
  - WebSocket access logs record `$request_method $uri $server_protocol` rather than `$request`, ensuring tickets and query strings never appear in web server access logs.
- **Internal Endpoint Protection**:
  - `/health/db` (EXPLAIN query inspection) and `/metrics` (Prometheus metrics) are restricted in Nginx via `allow 10.0.0.0/8`, `allow 172.16.0.0/12`, `allow 127.0.0.1` and `deny all;`.
- **JWT RS256 & Token Family Rotation**:
  - Access tokens expire in 15 minutes and remain in client memory only (never `localStorage`).
  - Refresh tokens are stored in `httpOnly; Secure; SameSite=Strict` cookies, hashed with SHA-256 before storage in PostgreSQL, and rotated on every use with family reuse theft detection.
- **Geometry Sanitization**:
  - Every polygon is validated for self-intersections (`ST_IsValid`), duplicate coordinate pruning, minimum area (1 m²), maximum area (`MAX_AREA_KM2`), and vertex bounds (3 to 1,000 vertices).

---

## Known Limitations & Scaling Path

| Limitation | Current State | Production Roadmap |
|---|---|---|
| **govmap.gov.il Satellite Basemap** | Govmap XYZ endpoint provides street vector imagery; Esri World Imagery is used as satellite layer ([ADR-004](docs/adr/004-projections-and-satellite-source.md)) | Integrate Govmap WMTS Israeli Grid (EPSG:2039) via Proj4 Leaflet plugin once official aerial endpoints are licensed |
| **Real-time Collaboration Engine** | Optimistic Concurrency Control (OCC) per-polygon save | Implement Yjs / Automerge CRDTs for real-time vertex-by-vertex co-editing |
| **Pub/Sub Room Scope** | Single global room (all users receive all updates) | Viewport-partitioned Redis channels (quadkey / tile-based pub/sub) |
| **Egress Scale** | Single-node Redis instance | Migrate to Redis Cluster / Redis Sentinel, Kafka or NATS for > 10,000 concurrent active drawers |
| **Database Read Scaling** | Primary PostgreSQL instance | Add streaming read-replicas with read-your-writes sticky routing |

---

## Testing Strategy & Quality Assurance

Snapland maintains a strict test pyramid with ≥ 80% coverage enforced on all layers:

### Running Tests Locally

```bash
# 1. Backend Linting & Type Checking
ruff check backend/src/
mypy --config-file backend/pyproject.toml backend/src/

# 2. Backend Unit & Integration Tests (Coverage >= 80%)
pytest backend/tests/ -v --cov=snapland --cov-fail-under=80

# 3. Frontend Type Checking & Coverage (Coverage >= 80%)
cd frontend
npx tsc --noEmit
npx vitest run --coverage

# 4. Type Drift Check between Python Pydantic Models & TypeScript
python scripts/gen_types.py
git diff --exit-code packages/shared-types
```

### GitHub Actions CI Pipeline
Every Pull Request automatically triggers `.github/workflows/ci.yml`:
1. **Backend**: Runs Ruff, Mypy (`backend/pyproject.toml`), and Pytest with 80% coverage check.
2. **Frontend**: Runs `tsc --noEmit` and Vitest with 80% coverage check.
3. **Type Drift**: Executes `scripts/gen_types.py` and asserts zero uncommitted drift in `packages/shared-types`.
4. **Docker Build**: Validates that all production Docker images compile without errors.
5. **Integration & Smoke**: Launches the composed test stack (`infra/docker-compose.test.yml`), confirms `/health/ready` returns 200, executes API + WS integration tests across live replicas, and tears down the environment.

---

## Environment Variables Reference

See `.env.example` for all configurable parameters:

| Variable | Description | Default (Local / Docker) |
|---|---|---|
| `ENVIRONMENT` | Deployment environment (`development`, `staging`, `production`) | `development` |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://snapland:password@postgres:5432/snapland` |
| `REDIS_URL` | Redis instance connection string | `redis://redis:6379/0` |
| `JWT_PRIVATE_KEY` | RSA-2048 private key in PEM format | Generated on first start if blank |
| `JWT_PUBLIC_KEY` | RSA-2048 public key in PEM format | Generated on first start if blank |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifespan | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifespan | `7` |
| `WS_ALLOWED_ORIGINS` | Allowed origins for WS handshake | `*` (development) |
| `MAX_AREA_KM2` | Maximum polygon area in square kilometers | `1000.0` |
| `MAX_POLYGON_VERTICES` | Maximum vertices per polygon | `1000` |
| `VITE_API_URL` | Frontend REST API base URL | `/api/v1` |
| `VITE_WS_URL` | Frontend WebSocket endpoint | `/ws` |
| `VITE_SATELLITE_TILE_URL` | Satellite imagery XYZ tile URL | Esri World Imagery |
