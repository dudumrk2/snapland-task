# Snapland Backend

Production-ready backend service for **Snapland**, an enterprise-grade collaborative GIS mapping application. Built with **FastAPI**, **PostgreSQL 16 + PostGIS 3.4**, and **Redis 7**, offering sub-10 ms spatial queries and real-time multi-user WebSocket collaboration.

---

## Architecture Overview

- **Framework:** FastAPI / Starlette (Python 3.12 / 3.13)
- **Database:** PostgreSQL 16 with PostGIS 3.4 extension
- **Data Access:** SQLAlchemy 2.0 (asyncio) + GeoAlchemy2 + asyncpg driver
- **Cache & Message Broker:** Redis 7 (L2 spatial cache, Redis Pub/Sub for ephemeral fan-out, Redis Streams for durable area mutations)
- **Task Scheduling:** APScheduler (in-process daily data retention with distributed Redis lock)
- **Observability:** Prometheus Client exposition (`GET /metrics`), `structlog` for structured JSON logging with secret/PII redaction

---

## Local Development Setup

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- PostgreSQL client / PostGIS (or run via Docker)

### 1. Start Infrastructure Services

Run the PostgreSQL + PostGIS and Redis containers:

```bash
# From repository root
docker compose -f infra/docker-compose.yml up -d postgres redis migrate
```

### 2. Configure Environment

Create your `.env` file (reference variable names in the section below):

```bash
cp .env.example .env
```

*(Note: In local development, if RSA key variables are omitted, ephemeral dev RSA keys are automatically generated in the OS temp directory on startup).*

### 3. Install Dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Launch Development Server

```bash
uvicorn main:app --reload --port 8000
```

---

## Docker Setup

To run the entire backend container stack:

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

This brings up:
- `backend` replicas (scaled across multiple workers)
- `postgres` (with PostGIS 3.4)
- `redis` (Pub/Sub + Streams + Cache)
- `nginx` (reverse proxy, least_conn load balancer, `/metrics` access restriction)

---

## Environment Variables Reference

> **Security Notice:** Only variable names are documented below. Secrets, tokens, and credentials must never be committed to source control.

| Variable Name | Required | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | No | `development` | Runtime environment (`development`, `staging`, `production`). In production, origin wildcard `*` is blocked and valid RSA keys are enforced. |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://...` | Connection URL for PostgreSQL. Must use the `postgresql+asyncpg` driver. |
| `REDIS_URL` | Yes | `redis://localhost:6379` | Connection URI for Redis broker and cache. |
| `JWT_PRIVATE_KEY` | Conditional | Dev ephemeral key | RSA private key (PEM format) used to sign RS256 JWT access tokens. |
| `JWT_PUBLIC_KEY` | Conditional | Dev ephemeral key | RSA public key (PEM format) used to verify RS256 JWT access tokens. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Lifetime in minutes for issued access tokens. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Lifetime in days for refresh token families. |
| `INSTANCE_ID` | No | Auto-generated | Unique identifier for the backend process instance (included in logs and presence frames). |
| `WS_ALLOWED_ORIGINS` | No | `*` | Allowed CORS and WebSocket origin whitelist (comma-separated). |
| `MAX_AREA_KM2` | No | `25000.0` | Maximum allowable polygon surface area in square kilometers (~Israel territory). |
| `MAX_POLYGON_VERTICES` | No | `1000` | Maximum number of coordinate vertices permitted per polygon. |

---

## API Endpoints Reference

Interactive OpenAPI documentation is accessible at `/docs` (Swagger UI) and `/redoc`.

### Health & Diagnostics
- `GET /health/live` — Liveness probe (HTTP 200).
- `GET /health/ready` — Readiness probe (verifies database and Redis connectivity).
- `GET /health/db` — Internal diagnostic running `EXPLAIN` on spatial queries to verify `areas_geom_gist` index usage. Restricted to internal network in production (enforced via reverse proxy).

### Observability
- `GET /metrics` — Exposes Prometheus metrics (HTTP request durations, active WebSockets, message throughput, cache hit ratios, and connection pool status). Restricted to internal cluster/Prometheus network via reverse proxy (Nginx).

### Authentication
- `POST /api/v1/auth/register` — Register a new account (`email`, `password`, `display_name`).
- `POST /api/v1/auth/login` — Authenticate credentials; returns access token in JSON body and refresh token in an `httpOnly` secure cookie.
- `POST /api/v1/auth/refresh` — Rotate refresh token cookie and issue a new access token.
- `POST /api/v1/auth/logout` — Revoke active session and clear authentication cookie.
- `POST /api/v1/auth/ws-ticket` — Generate a single-use 30-second ticket for authenticating WebSocket connections.

### Spatial Areas
- `GET /api/v1/areas` — Query polygons within a bounding box (`bounds=minLng,minLat,maxLng,maxLat`, `zoom`, `limit`). Requires Bearer authentication. Employs PostGIS GiST index and Redis L2 tile caching.
- `GET /api/v1/areas/{id}` — Retrieve a single area by UUID.
- `POST /api/v1/areas` — Create a new polygon. Validates geometry topology (`ST_IsValid`) and calculates geodesic area (`ST_Area`).
- `PUT /api/v1/areas/{id}` — Update area geometry or name using Optimistic Concurrency Control (`version` check).
- `DELETE /api/v1/areas/{id}` — Soft-delete an area (`deleted_at` timestamp).
- `GET /api/v1/areas/{id}/history` — Retrieve full historical audit versions for the area.

### Real-Time WebSocket
- `GET /ws?ticket=<ticket>&lastEventId=<id>` — Upgrade to collaborative WebSocket stream.
  - Inbound frames: `CURSOR_MOVE`, `DRAW_START`, `DRAW_UPDATE`, `DRAW_COMMIT`, `DRAW_CANCEL`.
  - Outbound frames: Micro-batched JSON array with cursor updates, user presence notifications, and durable area sync events.

---

## Running Tests & Benchmarks

### Test Suite Execution

Run all unit and integration tests:

```bash
pytest backend/tests/ -v
```

Run specific test suites:

```bash
# Unit tests
pytest backend/tests/unit/ -v

# Integration tests (requires Docker Postgres & Redis)
pytest backend/tests/integration/ -v
```

### Seeding & Spatial Benchmarks

Seed realistic polygons across Israel and execute `EXPLAIN (ANALYZE, BUFFERS)` benchmarks:

```bash
# Seed 10,000 polygons and run viewport benchmark
python scripts/seed_db.py --polygons 10000 --benchmark

# Seed 100,000 polygons
python scripts/seed_db.py --polygons 100000 --benchmark
```

### WebSocket Collaborative Load Testing

Run multi-client load testing:

```bash
# Python multi-client benchmark (50, 100, 200 virtual users)
python scripts/loadtest_collab.py --port 8000

# k6 load test script
k6 run loadtest/ws_collab.js
```

Full benchmark details, latency percentiles, and query execution plans are documented in [`docs/performance.md`](../docs/performance.md).

---

## Architecture Decisions Summary

- **ADR-001: PostGIS for Spatial Computation and Storage**  
  Uses PostgreSQL with PostGIS to compute spherical geodesics (`WGS84`, SRID 4326) and index geometries with GiST R-trees (`areas_geom_gist`), delivering sub-10 ms bounding-box queries even at 100,000 polygons.
- **ADR-002: Hybrid Redis Pub/Sub & Streams Architecture**  
  Ephemeral real-time events (such as 10 Hz cursor movements) stream through lightweight Redis Pub/Sub channels. Durable state changes (`AREA_CREATED`, `AREA_UPDATED`, `AREA_DELETED`) persist to Redis Streams (`areas:events`), allowing clients to resume missed events with `lastEventId`.
- **ADR-003: Optimistic Concurrency Control (OCC)**  
  Area records enforce an integer `version` field. Concurrent edits conflict with HTTP 409 (`CONFLICT`), returning the latest remote entity for 3-way client resolution rather than overwriting updates.
- **ADR-004: Projections & Satellite Basemap Source**  
  Esri World Imagery serves as the primary high-resolution satellite basemap in Web Mercator (EPSG:3857), with GovMap Israel vector tiles serving as automatic fallback upon tile load failures.
