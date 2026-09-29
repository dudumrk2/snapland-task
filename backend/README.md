# Snapland Backend

Backend service for the Snapland application, providing REST API and WebSocket real-time collaboration.

## Architecture

- **Language:** Python 3.12
- **Framework:** FastAPI
- **Database:** PostgreSQL 16 + PostGIS 3.4
- **ORM:** SQLAlchemy (async) + GeoAlchemy2
- **Cache/PubSub:** Redis 7

## Local Development Setup

1. Copy `.env.example` to `.env`
2. Start infrastructure: `docker compose up postgres redis migrate -d`
3. Install dependencies: `pip install -e .[dev]`
4. Run server: `uvicorn main:app --reload`

### Docker Setup

```bash
docker compose up -d
```

## Environment Variables

- `ENVIRONMENT`
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `INSTANCE_ID`
- `WS_ALLOWED_ORIGINS`
- `MAX_AREA_KM2`
- `MAX_POLYGON_VERTICES`

## Running Tests

```bash
pytest tests/ -v
```

## Architecture Decisions

See `/docs/adr/` for architecture decision records (ADRs).
- ADR-001: PostGIS Choice
- ADR-002: Redis PubSub and Streams
- ADR-003: OCC Conflict Strategy
- ADR-004: Projections and Satellite Source

## API Documentation

Swagger UI is available at `/docs` when the server is running.
Prometheus metrics available at `/metrics` (internal).
Health endpoints: `/health/live`, `/health/ready`, `/health/db`.
