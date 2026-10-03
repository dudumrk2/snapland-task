import re

with open('snapland-hld.md', 'r', encoding='utf-8') as f:
    content = f.read()

phases = [
    ('Phase 0', '- [x] Repository scaffolded exactly matching HLD\\n- [x] All Phase 0 dependencies installed\\n- [x] All Protocol interfaces and TS bootstrap types defined\\n- [x] docker compose up starts containers successfully'),
    ('Phase 1', '- [x] Vite dev server running\\n- [x] Leaflet map renders correctly with OSM and Satellite base layers\\n- [x] Users can draw, edit, and delete polygons locally\\n- [x] Zustand stores integrated with mock services\\n- [x] Vitest suite passes 100%'),
    ('Phase 2', '- [x] Database schema & Alembic migrations created successfully\\n- [x] Auth routes (JWT, Refresh cookies) implemented and tested\\n- [x] Core CRUD operations for Areas implemented with OCC\\n- [x] Shared TypeScript types automatically generated\\n- [x] Integration and Unit tests pass with >85% coverage'),
    ('Phase 3A', '- [x] Redis Pub/Sub integration complete for ephemeral messages\\n- [x] Redis Streams integration complete for durable events (AREA_*)\\n- [x] Rate limiting & connection queueing functional\\n- [x] WebSocket endpoint securely accepts tickets and upgrades'),
    ('Phase 3B', '- [x] Frontend successfully swaps Mock services for Real implementations\\n- [x] Session bootstrapping works securely via cookies\\n- [x] WS Reconnection and degrade (polling) logic functional\\n- [x] Playwright E2E tests fully passing against Docker stack'),
    ('Phase 4A', '- [x] /metrics endpoint exposes Prometheus data\\n- [x] Structlog configured with JSON output and Request IDs\\n- [x] /health/db confirms correct spatial index usage\\n- [x] Data retention cleanup job scheduled and tested'),
    ('Phase 4B', '- [x] Nginx configured as API Gateway and WS proxy\\n- [x] Docker-compose orchestrated with multiple backend replicas\\n- [x] CI/CD pipeline integrated in GitHub Actions\\n- [x] Root README.md documented properly for deployment')
]

for phase_name, dod in phases:
    # Find the end of the prompt codeblock for this phase
    # The phases usually end with 'DELIVERABLES:\\n...\\n`\\n\\n---'
    # We want to insert the DoD just before the '---'
    
    # We will look for the specific DELIVERABLES block that ends the phase
    # Since Phase 3 and 4 have A and B, we look for the specific Phase X Agent Prompt heading, then the next `
    
    pattern = r"(#### 📋 " + phase_name + r".*?DELIVERABLES:.*?`\n)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        full_match = match.group(1)
        insertion = f"\n**Definition of Done ({phase_name}):**\n{dod}\n"
        content = content.replace(full_match, full_match + insertion)

with open('snapland-hld.md', 'w', encoding='utf-8') as f:
    f.write(content)
print('DoDs inserted successfully.')
