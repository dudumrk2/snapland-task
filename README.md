# Snapland – Real-Time Collaborative GIS

[![CI](https://github.com/dudumrk2/snapland/actions/workflows/ci.yml/badge.svg)](https://github.com/dudumrk2/snapland/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Node.js 20](https://img.shields.io/badge/Node-20-green.svg)](https://nodejs.org/)
[![PostGIS 3.4](https://img.shields.io/badge/PostGIS-3.4-darkblue.svg)](https://postgis.net/)
[![Redis 7](https://img.shields.io/badge/Redis-7.2-red.svg)](https://redis.io/)

Snapland is a high-performance, real-time collaborative GIS web application designed for simultaneous geographic polygon drawing, editing, and spatial analysis over Israel. Multiple analysts can concurrently draft and edit geographic boundaries on interactive maps while viewing each other's live cursor positions, in-flight drawing previews, and presence updates with sub-100ms latency.

---

## 🏛️ Architecture Overview

Snapland uses an event-driven, decoupled microservices architecture designed for horizontal scalability, zero-downtime deployments, and authoritative spatial data integrity:

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
        PG["PostgreSQL 16 with PostGIS 3.4\nSpatial GiST Index: areas_geom_gist\nOptimistic Concurrency Control (OCC)"]
    end

    subgraph Observability["Observability Tier"]
        PROM["Prometheus 2.x\nDNS Service Discovery Scrapes /metrics"]
        GRAF["Grafana 10.x\nPre-provisioned System Dashboard"]
    end

    C1 & C2 <-->|"HTTPS / WSS"| LB
    LB -->|"least_conn"| BE1 & BE2
    BE1 & BE2 <-->|"Publish & Subscribe"| PUB
    BE1 & BE2 <-->|"Append & Stream Follow"| STR
    BE1 & BE2 <-->|"Presence & Cache"| PR & CA
    BE1 & BE2 -->|"Async SQLAlchemy / asyncpg"| PG
    PROM -->|"Scrapes /metrics"| BE1 & BE2
    GRAF -->|"PromQL Queries"| PROM
```

### Detailed Design & Architecture Decision Records:
- [High-Level Design Specification (HLD)](docs/hld.md)
- [ADR 001: Choice of PostgreSQL 16 + PostGIS 3.4 for Spatial Engine](docs/adr/001-postgis-choice.md)
- [ADR 002: Hybrid Real-Time Transport (Redis Pub/Sub & Streams)](docs/adr/002-redis-pubsub-and-streams.md)
- [ADR 003: Optimistic Concurrency Control (OCC) for Polygon Edits](docs/adr/003-occ-conflict.md)
- [ADR 004: Projections and Satellite Source Findings](docs/adr/004-projections-and-satellite-source.md)
- [Performance & Benchmark Evidence](docs/performance.md)

---

## ⚡ Quickstart (One-Command Deployment)

The entire production stack (PostgreSQL + PostGIS, Redis, automated database migrations, 2 backend replicas, frontend SPA, Nginx gateway, Prometheus, and Grafana) launches out of the box.

### Prerequisites
- Docker Engine 24+ and Docker Compose v2+
- Available ports on host: `80` (HTTP/WS), `5432` (PostgreSQL), `6379` (Redis), `9090` (Prometheus), `3000` (Grafana)

### 1. Automated Bootstrap Script (Recommended)
From the repository root, run:
```bash
./scripts/setup.sh
```
Or with explicit options:
```bash
# Launch Docker Compose with 2 backend replicas and wait for readiness
./scripts/setup.sh --docker

# Seed the database with 10,000 realistic polygons across Israel
./scripts/setup.sh --seed 10000

# Tear down the stack and clean up volumes
./scripts/setup.sh --down
```

### 2. Manual Docker Compose Launch
```bash
docker compose -f infra/docker-compose.yml up -d --build --scale backend=2
```

### 3. Service Access Endpoints
| Component | URL | Notes / Credentials |
|---|---|---|
| **Web Application** | [http://localhost](http://localhost) | Main collaborative map interface |
| **API Swagger UI** | [http://localhost/docs](http://localhost/docs) | Interactive OpenAPI documentation |
| **OpenAPI Spec** | [http://localhost/openapi.json](http://localhost/openapi.json) | Raw OpenAPI JSON schema |
| **Readiness Health Check** | [http://localhost/health/ready](http://localhost/health/ready) | System probe (PostgreSQL + Redis + Worker connectivity) |
| **Liveness Health Check** | [http://localhost/health/live](http://localhost/health/live) | Lightweight application process ping |
| **Prometheus** | [http://localhost:9090](http://localhost:9090) | Target scrape status and metrics engine |
| **Grafana Dashboard** | [http://localhost:3000](http://localhost:3000) | Username: `admin`, Password: `admin` |

---

## 💻 Local Development Setup

For debugging and active development outside Docker containers:

### 1. Start Infrastructure Dependencies
```bash
docker compose -f infra/docker-compose.yml up -d postgres redis
```

### 2. Backend Setup
Requires **Python 3.12+**.
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install hatchling
pip install -e backend/
pip install pytest pytest-asyncio pytest-cov httpx fakeredis ruff mypy

# Run database migrations
cd backend
alembic upgrade head

# Start FastAPI development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup
Requires **Node.js 20+**.
```bash
# Install and link shared types package
cd packages/shared-types
npm install

# Install frontend dependencies and start Vite dev server
cd ../../frontend
npm install
npm run dev
```
The Vite development server runs on `http://localhost:5173` with reverse proxy pre-configured to forward `/api` and `/ws` to `http://localhost:8000`.

---

## 📐 Key Technical Decisions & Rationale

### 1. PostGIS 3.4 Spatial Database ([ADR 001](docs/adr/001-postgis-choice.md))
- **Authoritative Geodesic Calculations**: All polygon areas are authoritatively computed on the server over the WGS84 ellipsoid via `ST_Area(geom::geography)`. Planar projections (such as Web Mercator EPSG:3857) distort area by up to 40% at Israel's latitude (~32°N); PostGIS ensures millimeter-accurate ground truth.
- **Topological Integrity**: Polygons are validated upon submission via `ST_IsValid(geom)`. Bowties, self-intersecting segments, duplicate consecutive vertices, and degenerate polygons are rejected before database commit.
- **R-Tree GiST Indexing**: Viewport bounding box filtering is accelerated with a partial spatial index (`areas_geom_gist`) on `areas USING GIST (geom) WHERE deleted_at IS NULL`.

### 2. Decoupled Real-Time Transport ([ADR 002](docs/adr/002-redis-pubsub-and-streams.md))
- **Ephemeral Telemetry (Redis Pub/Sub)**: High-frequency mouse cursors (`CURSOR_MOVE` at 10 Hz) and in-flight drafting previews (`DRAW_START`, `DRAW_UPDATE`, `DRAW_CANCEL`) fan out cluster-wide through channel `snapland:events:ephemeral`. Messages bypass the database and persistent logs. Outbound messages are micro-batched into 50ms frames with latest-cursor coalescing.
- **Durable Mutations (Redis Streams)**: Persistent changes (`AREA_CREATED`, `AREA_UPDATED`, `AREA_DELETED`) are appended to Redis Stream `areas:events` with monotonic IDs (`timestamp-sequence`).
- **Catch-up Sync**: Clients pass `lastEventId` on WebSocket connect/reconnect to replay missed mutations via `XREAD`. If the client lags beyond the retention window, the server returns `RESYNC_REQUIRED` to trigger an efficient viewport re-fetch.
- **Distributed Presence**: Heartbeats track user activity in Redis Sorted Sets (`presence:heartbeats`) with an atomic periodic reaper publishing `USER_LEFT`.

### 3. Optimistic Concurrency Control ([ADR 003](docs/adr/003-occ-conflict.md))
- To prevent the "lost update" anomaly during concurrent editing without locking polygons:
  ```sql
  UPDATE areas
  SET geom = :new_geom, name = :new_name, version = version + 1, updated_at = NOW()
  WHERE id = :id AND version = :expected_version AND deleted_at IS NULL
  RETURNING version;
  ```
- If another user committed an edit first, `rowcount == 0` triggers an HTTP `409 CONFLICT` carrying the latest remote polygon payload (`details.current_area`).
- The frontend displays an interactive Conflict Resolution Dialog with three distinct options:
  1. **Accept Remote**: Discards local edits and applies the remote user's updated boundary.
  2. **Force Overwrite**: Advances local version counter and reapplies local edits over the remote boundary.
  3. **Save as New**: Saves local modifications as a brand-new, independent polygon entity.

### 4. Authoritative Projections & Basemap Findings ([ADR 004](docs/adr/004-projections-and-satellite-source.md))
- Investigation of the `cdnil.govmap.gov.il` XYZ tile endpoint showed that it serves vector street map tiles rather than high-resolution satellite imagery.
- Snapland adopts **Esri World Imagery** as the high-resolution satellite basemap layer in Web Mercator (EPSG:3857), allowing seamless map rendering in Leaflet without custom ITM (EPSG:2039) reprojection overhead.

---

## 🚀 Performance Optimizations & Benchmarks

Empirical performance numbers captured from the hardened application stack (see [docs/performance.md](docs/performance.md)):

1. **Spatial Indexing & Viewport Queries**:
   - Evaluated on a 100,000 polygon dataset seeded across Israel (`scripts/seed_db.py`).
   - PostGIS partial GiST index (`areas_geom_gist`) executes regional and city-level bounding box queries in **< 40ms cold DB** and **< 3ms via Redis cache**.
2. **Two-Tier Caching Hierarchy**:
   - **L1 In-Memory LRU**: Caches static JWT RSA public keys and configuration per replica.
   - **L2 Redis Viewport Cache**: Viewport bounding box queries snap outward to a 0.01° grid. Cached results (10s TTL) are invalidated cluster-wide on any mutation via an atomic `INCR areas:epoch`.
3. **Outbound WebSocket Coalescing & Micro-Batching**:
   - Outbound writer task buffers messages up to 50ms, coalescing cursor positions per user (latest wins) and merging contiguous drawing deltas into single JSON array frames.
   - Reduces cluster egress from ~114,000 frames/sec down to ~2,000 frames/sec for 100 active collaborators.
4. **Asynchronous Connection Pooling**:
   - `asyncpg` connection pool with query timeout hierarchy (`statement_timeout = 25000ms`, route timeout = 30s) prevents runaway queries from starving workers.

---

## 🔒 Security Implementations

- **Ticket-Based WebSocket Authentication**:
  - Tokens are never sent as query parameters in WebSocket URLs.
  - Clients exchange access tokens via `POST /api/v1/auth/ws-ticket` for a single-use 30-second ticket.
  - The ticket is redeemed atomically via Redis `GETDEL ws_ticket:{ticket}` before upgrading the WebSocket connection.
- **Nginx Access Log Sanitization**:
  - WebSocket access logs record `$request_method $uri $server_protocol` instead of `$request`, preventing tokens and query parameters from ever appearing on disk.
- **Internal Endpoint Isolation**:
  - Administrative and diagnostic endpoints (`/health/db` and `/metrics`) are restricted in Nginx:
    ```nginx
    location = /metrics {
        allow 127.0.0.1;
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        deny all;
        proxy_pass http://backend/metrics;
    }
    ```
- **JWT RS256 & Token Family Rotation**:
  - Access tokens (RS256, 15-minute lifespan) stay exclusively in client browser memory (never `localStorage`).
  - Refresh tokens are stored in `httpOnly; Secure; SameSite=Strict` cookies, hashed with SHA-256 before storage in PostgreSQL, and rotated on every refresh with token family reuse theft detection.
- **Sliding Window Rate Limiting**:
  - Redis sliding window rate limits protect auth endpoints (5 req/min for login/register), general API routes (60 req/min), drawing actions (30 req/min), and WebSocket drawing streams (900 req/min).
  - Nginx provides an IP-level rate-limiting backstop (`30r/s`, burst 20).
- **SQL Injection & Input Validation**:
  - Parameterized queries throughout SQLAlchemy 2.0 and asyncpg.
  - Pydantic models validate geometry limits (3 to 1,000 vertices, minimum 1 m², maximum 1,000 km²).

---

## 📈 Scaling Strategy & Production Roadmap

| Layer | Current Architecture | Scaling Path for 10,000+ Concurrent Users |
|---|---|---|
| **Edge Gateway** | Nginx with `least_conn` load balancing | Multiple Nginx / HAProxy nodes behind DNS round-robin / Cloudflare |
| **Backend Workers** | Stateless FastAPI replicas (2 in compose) | Auto-scaling Kubernetes deployment (HPA based on CPU / WS connections) |
| **Real-Time Bus** | Single Redis 7 instance | Redis Cluster / Redis Sentinel, migrating to Kafka or NATS for > 10k users |
| **Room Partitioning** | Single global room (Israel) | Spatial tile-based Redis channels (quadkey / Geohash-scoped pub/sub) |
| **Database Reads** | PostgreSQL 16 primary | Read replicas with PgBouncer connection pooling and read-your-writes routing |
| **Collaboration Model** | OCC with Conflict Resolution Dialog | Hybrid OCC + CRDTs (Yjs / Automerge) for real-time vertex-level co-editing |

---

## 🧪 Testing Pyramid & Quality Gates

Snapland enforces strict quality gates across all layers with **≥ 80% test coverage** enforced in CI:

```
          / \
         /   \       Playwright E2E Tests (Full User Flow & Map Drawing)
        / E2E \
       /-------\
      / Integr- \    Live Multi-Instance Tests (PostGIS + Redis + Nginx)
     /   ation   \   pytest integration, loadtest_collab.py, ws_collab.js
    /-------------\
   /     Unit      \  Backend: pytest --cov-fail-under=80 (68+ tests)
  /                 \ Frontend: vitest --coverage (thresholds >= 80%)
 /-------------------\
```

### Running Tests Locally

```bash
# 1. Backend Linting & Static Typing
ruff check backend/src/
mypy --config-file backend/pyproject.toml backend/src/

# 2. Backend Unit & Integration Tests (Coverage >= 80%)
pytest backend/tests/ -v --cov=snapland --cov-fail-under=80

# 3. Frontend Type Checking & Coverage (Coverage >= 80%)
cd frontend
npm run type-check
npm run test:coverage

# 4. Type Drift Check between Python Pydantic Models & TypeScript
python scripts/gen_types.py
git diff --exit-code packages/shared-types

# 5. Spatial Seeding & Viewport Benchmark
python scripts/seed_db.py --help
python scripts/seed_db.py --polygons 10000
python scripts/seed_db.py --benchmark

# 6. WebSocket Load Testing (k6)
k6 run loadtest/ws_collab.js
```

### GitHub Actions CI Pipeline
Every Pull Request and push to `main` or `feat/**` automatically triggers `.github/workflows/ci.yml`:
1. **`backend`**: Runs Ruff linter, Mypy type checker, runs database migrations against PostGIS service container, and executes Pytest with 80% coverage check.
2. **`frontend`**: Runs `npm run type-check` (`tsc --noEmit`) and `npm run test:coverage` (Vitest with 80% coverage check).
3. **`types`**: Executes `scripts/gen_types.py` and confirms zero uncommitted type drift in `packages/shared-types`.
4. **`docker-build`**: Validates that all production Docker images build cleanly with Buildx.
5. **`integration-and-smoke`**: Deploys the composed test stack (`infra/docker-compose.test.yml`), verifies `/health/ready` probe, executes multi-replica integration tests across live services, and tears down the environment.

---

## ⚙️ Environment Variables Reference

See `.env.example` for the complete configuration schema:

| Variable | Description | Default (Local / Docker) |
|---|---|---|
| `ENVIRONMENT` | Deployment environment (`development`, `staging`, `production`) | `development` |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://snapland:password@postgres:5432/snapland` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `JWT_PRIVATE_KEY` | RSA-2048 private key in PEM format | Generated automatically on startup if omitted |
| `JWT_PUBLIC_KEY` | RSA-2048 public key in PEM format | Generated automatically on startup if omitted |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `WS_ALLOWED_ORIGINS` | Allowed origins for WebSocket handshake | `*` |
| `MAX_AREA_KM2` | Maximum polygon area in square kilometers | `1000.0` |
| `MAX_POLYGON_VERTICES` | Maximum vertex count per polygon | `1000` |
| `VITE_API_URL` | Frontend REST API base URL | `/api/v1` |
| `VITE_WS_URL` | Frontend WebSocket endpoint URL | `/ws` |
| `VITE_SATELLITE_TILE_URL` | Satellite imagery XYZ tile URL | Esri World Imagery |
