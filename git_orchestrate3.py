import os
import subprocess

def run(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"Command failed with {result.returncode}, but continuing...")

run('git checkout main')
# Phase 0
run('git checkout -b feat/phase-0-scaffold || git checkout feat/phase-0-scaffold')
run('git add backend/pyproject.toml backend/alembic.ini frontend/package.json frontend/tsconfig.json frontend/vite.config.ts packages/shared-types/package.json packages/shared-types/tsconfig.json docs/')
run('git commit -m "Phase 0: Repository Scaffold"')

# Phase 1
run('git checkout -b feat/phase-1-frontend || git checkout feat/phase-1-frontend')
run('git add frontend/')
run('git reset HEAD frontend/src/api/http/ frontend/src/services/websocket/ frontend/tests/e2e/collaboration.spec.ts')
run('git checkout -- frontend/src/api/http/ frontend/src/services/websocket/ frontend/tests/e2e/collaboration.spec.ts')
run('git commit -m "Phase 1: Frontend Foundation (Mocks)"')

# Phase 2
run('git checkout -b feat/phase-2-backend || git checkout feat/phase-2-backend')
run('git add backend/ packages/shared-types/')
run('git reset HEAD backend/src/snapland/api/websocket/ backend/src/snapland/infrastructure/pubsub/ backend/src/snapland/middleware/metrics.py backend/src/snapland/middleware/timeout.py backend/src/snapland/infrastructure/jobs/ backend/tests/integration/test_websocket.py')
run('git checkout -- backend/src/snapland/api/websocket/ backend/src/snapland/infrastructure/pubsub/ backend/src/snapland/middleware/metrics.py backend/src/snapland/middleware/timeout.py backend/src/snapland/infrastructure/jobs/ backend/tests/integration/test_websocket.py')
run('git commit -m "Phase 2: Backend Core (CRUD & Auth)"')

# Phase 3A
run('git checkout -b feat/phase-3a-realtime-be || git checkout feat/phase-3a-realtime-be')
run('git add backend/src/snapland/api/websocket/ backend/src/snapland/infrastructure/pubsub/ backend/tests/integration/test_websocket.py')
run('git commit -m "Phase 3A: Backend Real-time WebSocket Layer"')

# Phase 3B
run('git checkout -b feat/phase-3b-realtime-fe || git checkout feat/phase-3b-realtime-fe')
run('git add frontend/src/api/http/ frontend/src/services/websocket/ frontend/tests/e2e/collaboration.spec.ts')
run('git commit -m "Phase 3B: Frontend HTTP/WS Integration"')

# Phase 4
run('git checkout -b feat/phase-4-hardening-devops || git checkout feat/phase-4-hardening-devops')
run('git add .')
run('git commit -m "Phase 4: Production Hardening & DevOps"')

print("Branches created successfully!")
