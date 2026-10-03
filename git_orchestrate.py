import os
import subprocess

def run(cmd):
    print(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=True)

# Start fresh
run('git checkout main || git checkout -b main')
run('git reset --hard HEAD || echo "No commits yet"')

# Base branch (main)
run('git rm -rf . || echo "already clean"')
run('git add assignment_text.txt "Snapland-Home Assignment-R&D Team Lead.pdf" snapland-hld.md')
run('git commit -m "Initial commit: Assignment requirements and HLD" || echo "already committed"')

# Phase 0
run('git checkout -b feat/phase-0-scaffold')
run('git add .env.example scaffold.py scaffold.ps1 packages/shared-types/package.json packages/shared-types/tsconfig.json docs/')
# Add backend and frontend config files only (not src)
run('git add backend/pyproject.toml backend/alembic.ini backend/pytest.ini frontend/package.json frontend/tsconfig.json frontend/vite.config.ts')
run('git commit -m "Phase 0: Repository Scaffold"')

# Phase 1
run('git checkout -b feat/phase-1-frontend')
# Add frontend src, but EXCLUDE Phase 3B stuff
run('git add frontend/')
run('git reset HEAD frontend/src/api/http/ frontend/src/services/websocket/ frontend/tests/e2e/collaboration.spec.ts')
run('git checkout -- frontend/src/api/http/ frontend/src/services/websocket/ frontend/tests/e2e/collaboration.spec.ts || echo "not in index yet"')
run('git commit -m "Phase 1: Frontend Foundation (Mocks)"')

# Phase 2
run('git checkout -b feat/phase-2-backend')
# Add backend src and packages, EXCLUDE Phase 3A and 4A stuff
run('git add backend/ packages/shared-types/')
run('git reset HEAD backend/src/snapland/api/websocket/ backend/src/snapland/infrastructure/pubsub/ backend/src/snapland/middleware/metrics.py backend/src/snapland/middleware/timeout.py backend/src/snapland/infrastructure/jobs/')
run('git checkout -- backend/src/snapland/api/websocket/ backend/src/snapland/infrastructure/pubsub/ backend/src/snapland/middleware/metrics.py backend/src/snapland/middleware/timeout.py backend/src/snapland/infrastructure/jobs/ || echo "not in index yet"')
run('git commit -m "Phase 2: Backend Core (CRUD & Auth)"')

# Phase 3A
run('git checkout -b feat/phase-3a-realtime-be')
run('git add backend/src/snapland/api/websocket/ backend/src/snapland/infrastructure/pubsub/ backend/tests/integration/test_websocket.py')
run('git commit -m "Phase 3A: Backend Real-time WebSocket Layer"')

# Phase 3B
run('git checkout -b feat/phase-3b-realtime-fe')
run('git add frontend/src/api/http/ frontend/src/services/websocket/ frontend/tests/e2e/collaboration.spec.ts')
run('git commit -m "Phase 3B: Frontend HTTP/WS Integration"')

# Phase 4
run('git checkout -b feat/phase-4-hardening-devops')
run('git add .') # Add everything else (metrics, jobs, docker-compose, github actions, README)
run('git commit -m "Phase 4: Production Hardening & DevOps"')

print("Branches created successfully!")
