# Snapland

Snapland is a collaborative, real-time GIS web application where multiple users can simultaneously draw, edit, and analyze geographic polygons on an interactive map.

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Node.js (v20+)

### Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Start the services using Docker Compose:
   ```bash
   cd infra
   docker-compose up -d --build
   ```

3. The application will be available at:
   - Frontend: http://localhost
   - API: http://localhost/api
   - WebSocket: ws://localhost/ws
   - Grafana: http://localhost:3000

## Architecture

Please refer to the [High-Level Design (HLD)](docs/hld.md) document for a detailed architectural overview.

### Features
- Multi-user real-time collaboration (live cursors, drawing previews).
- Dual map layers (OpenStreetMap + Satellite imagery).
- Persistent polygon storage with versioning and edit history.
- Live in-browser area calculations.
- Viewport-aware spatial queries.
- Observability with Prometheus and Grafana.

## Running Tests

### Backend
```bash
cd backend
pip install -e .[dev]
pytest
```

### Frontend
```bash
cd frontend
npm install
npm test
```
