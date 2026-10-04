# ADR 002: Hybrid Real-Time Transport Architecture with Redis Pub/Sub and Streams

## Status
Accepted

## Context
Snapland requires a real-time collaboration layer that supports concurrent users drawing, editing, and inspecting polygons simultaneously across multiple load-balanced FastAPI backend replicas.

The real-time workload exhibits two fundamentally distinct traffic characteristics:
1. **Ephemeral, High-Frequency Telemetry**:
   - Cursor positions (`CURSOR_MOVE`) stream at 10 Hz per active user.
   - Live drawing vertex previews (`DRAW_START`, `DRAW_UPDATE`, `DRAW_CANCEL`) stream continuously while a user manipulates vertices.
   - Characteristics: High volume, strict latency requirements (<100ms end-to-end), loss-tolerant (a dropped cursor coordinate is immediately superseded by the next one), and non-persistent (should never be written to relational tables).
2. **Durable, Critical Mutations**:
   - Committed polygon creations, edits, and deletions (`AREA_CREATED`, `AREA_UPDATED`, `AREA_DELETED`).
   - Characteristics: Low frequency, strictly ordered, non-loss-tolerant, and require replay capability so clients recovering from transient network drops can synchronize missed events without slamming PostgreSQL with full viewport re-fetches.

## Alternatives Considered

### 1. In-Memory Local Broadcasting (Single-Node Starlette / FastAPI)
- *Pros*: Zero external infrastructure dependencies; ultra-fast local memory fan-out.
- *Cons*: Fails completely when scaling horizontally to multiple backend replicas. Users connected to Replica A cannot see cursors or edits performed by users connected to Replica B.

### 2. PostgreSQL `LISTEN` / `NOTIFY`
- *Pros*: Built into PostgreSQL; transactions and notifications commit together.
- *Cons*: 8,000-byte payload limit; notifications are ephemeral (no replay); high-frequency cursor storms (hundreds of messages/sec) exhaust PostgreSQL worker processes and saturate database connection pools.

### 3. Redis Pub/Sub Only
- *Pros*: Extremely lightweight, sub-millisecond in-memory fan-out across multiple cluster nodes.
- *Cons*: Strictly ephemeral fire-and-forget. If a user loses Wi-Fi for 3 seconds, they permanently miss any `AREA_UPDATED` or `AREA_DELETED` events that occurred in the interim.

### 4. Redis Streams Only
- *Pros*: Append-only log with persistent ordered entries and consumer groups.
- *Cons*: Persisting 10 Hz cursor movements and intermediate mouse draft updates produces severe memory footprint growth and excessive stream trimming overhead for data that has zero value milliseconds after transmission.

### 5. Dedicated Broker (Apache Kafka / RabbitMQ)
- *Pros*: Robust partitioning and stream retention guarantees.
- *Cons*: Massive operational overhead, heavy JVM / Erlang resource usage, complex consumer group balancing, and unjustified infrastructure footprint for v1.

## Decision

We adopt a **Hybrid Real-Time Transport Architecture** built on **Redis 7**:

```
                       ┌─────────────────────────────────────────┐
                       │           Web Clients (Browsers)        │
                       └───────────────────▲─────────────────────┘
                                           │ WebSocket (WSS)
                       ┌───────────────────▼─────────────────────┐
                       │   FastAPI Replicas (Stateless Workers)  │
                       └───────────▲─────────────────▲───────────┘
                                   │                 │
              Ephemeral Telemetry  │                 │  Durable Mutations
              (Pub/Sub Fan-out)    │                 │  (Append & XREAD)
                                   ▼                 ▼
             ┌───────────────────────────┐     ┌───────────────────────────┐
             │ Redis Pub/Sub             │     │ Redis Streams             │
             │ Channel:                  │     │ Stream: areas:events      │
             │ snapland:events:ephemeral │     │ ID: <timestamp>-<seq>     │
             └───────────────────────────┘     └───────────────────────────┘
```

### 1. Ephemeral Transport: Redis Pub/Sub
- Ephemeral events (`CURSOR_MOVE`, `REMOTE_DRAW`) publish to Redis channel `snapland:events:ephemeral`.
- Each FastAPI replica runs a background subscription task that deserializes envelopes and fans them out to local WebSocket connections.
- **Echo Suppression**: Envelopes include an `origin` instance identifier; replicas ignore messages originating from themselves to prevent local broadcast echoes.
- **Micro-Batching & Coalescing**: Outbound WebSocket writers buffer messages up to 50ms, coalescing cursor positions (latest position per user wins) and concatenating contiguous vertex deltas into a single JSON array frame.

### 2. Durable Mutation Transport: Redis Streams
- On database transaction commit (`AreaService.create_area`, `update_area`, `delete_area`), the mutation is appended to Redis Stream `areas:events` via `XADD`.
- Each stream entry receives a monotonic ID (e.g. `1728000000000-0`).
- A background stream follower task on each backend replica reads new events (`XREAD BLOCK 1000`) and enqueues them for delivery to connected WebSocket clients.
- Durable events immediately flush client outbound queues, bypassing the 50ms ephemeral buffer.

### 3. Catch-Up & Reconnection Protocol
- When clients connect or reconnect (`GET /ws?ticket=<token>&lastEventId=<id>`), the backend reads missed stream events via `XREAD STREAMS areas:events <lastEventId>`.
- Replayed events are streamed immediately to the client in chronological order.
- If `lastEventId` is too old and has been trimmed from the stream buffer (or is invalid), the server emits `RESYNC_REQUIRED`, instructing the client to invalidate local cache and re-query its current viewport from the REST API.

### 4. Distributed Presence via Redis Sorted Sets (ZSET)
- Active user presence is tracked in Redis ZSET `presence:heartbeats` with epoch millisecond timestamps.
- WebSockets pulse heartbeats every 10 seconds.
- A cluster-wide reaper runs every 15 seconds (guarded by an atomic `SET NX PX` distributed lock), identifying expired users, purging them, and broadcasting `USER_LEFT` events.

## Consequences

### Positive:
- **Zero Sticky Sessions**: Backend replicas remain completely stateless. Any client can connect to any backend replica and experience seamless real-time collaboration.
- **Controlled Resource Consumption**: High-frequency cursor noise is handled purely in RAM and never touches disk or relational tables.
- **Network Resilience**: Clients survive network hiccups without losing polygon state updates.
- **Client Protection**: 50ms batching and cursor coalescing reduce client browser message handling overhead by over 90% during intense multi-user collaboration.

### Negative / Trade-offs:
- Requires dual event dispatch logic in the application tier (publishing to Pub/Sub vs. Streams).
- Stream retention must be bounded (using `MAXLEN ~ 10000`) to prevent unbounded memory growth over prolonged runtimes.
