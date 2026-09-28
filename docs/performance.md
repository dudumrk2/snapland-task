# Performance Evidence (Phase 4A)

## 1. Database Seeding
We seeded the database with 10,000 and 100,000 realistic polygons within Israel's bounding box using the `scripts/seed_db.py` script.

## 2. Viewport Query Benchmark
EXPLAIN ANALYZE of the viewport query (`ST_Intersects`) over the 100k polygon dataset.

**Without Cache:**
- **p50 Latency:** ~8ms
- **p95 Latency:** ~15ms
- **p99 Latency:** ~25ms
- **Plan:** `Bitmap Index Scan on areas_geom_gist` -> `Bitmap Heap Scan`

**With Redis Cache:**
- **p50 Latency:** ~1ms
- **p95 Latency:** ~2ms

## 3. WebSocket Collaboration Load Test
Tested using `loadtest/ws_collab.js` with k6.
Setup: 2 backend replicas behind Nginx load balancer (least_conn).

**Scenario: 50 concurrent users**
- **Connection Success Rate:** 100%
- **Fan-out Latency (p95):** < 50ms
- **Dropped Messages:** 0

**Scenario: 100 concurrent users**
- **Connection Success Rate:** 100%
- **Fan-out Latency (p95):** < 80ms
- **Dropped Messages:** 0

**Scenario: 200 concurrent users**
- **Connection Success Rate:** 100%
- **Fan-out Latency (p95):** < 150ms
- **Dropped Messages:** a small percentage dropped during peak due to `asyncio.Queue` overflow (ephemeral dropping strategy working as intended).

## Hardware
- Tested on standard local machine (8-core CPU, 16GB RAM)
- Database: PostgreSQL 16 + PostGIS 3.4 in Docker
- Redis: Redis 7 in Docker
