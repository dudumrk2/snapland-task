#!/usr/bin/env bash
# ==============================================================================
# Snapland – One-Command Setup & Bootstrap Script
# ==============================================================================
# Usage:
#   ./scripts/setup.sh               # Bootstrap and start production Docker stack
#   ./scripts/setup.sh --docker      # Start full Docker stack with 2 backend replicas
#   ./scripts/setup.sh --local       # Bootstrap local virtualenv & Node dependencies
#   ./scripts/setup.sh --seed 10000  # Seed database with realistic polygons
#   ./scripts/setup.sh --down        # Stop and remove containers and volumes
#   ./scripts/setup.sh --help        # Show usage help
# ==============================================================================

set -euo pipefail

# Text styling
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info() {
    echo -e "${CYAN}${BOLD}[INFO]${RESET} $1"
}

success() {
    echo -e "${GREEN}${BOLD}[SUCCESS]${RESET} $1"
}

warn() {
    echo -e "${YELLOW}${BOLD}[WARN]${RESET} $1"
}

error() {
    echo -e "${RED}${BOLD}[ERROR]${RESET} $1" >&2
}

# Determine repository root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "============================================================"
    echo "  SNAPLAND – Real-Time Collaborative GIS Setup              "
    echo "============================================================"
    echo -e "${RESET}"
}

print_help() {
    echo "Usage: ./scripts/setup.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --docker        Start the full containerized stack via Docker Compose (default)"
    echo "  --local         Set up local development environment (venv + npm packages)"
    echo "  --seed [COUNT]  Seed the database with realistic polygons (default: 1000)"
    echo "  --down          Tear down Docker Compose containers and volumes"
    echo "  -h, --help      Display this help message"
    echo ""
}

ensure_env_file() {
    if [ ! -f "$REPO_ROOT/.env" ]; then
        if [ -f "$REPO_ROOT/.env.example" ]; then
            info "Creating .env from .env.example..."
            cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
            success ".env configuration created."
        else
            warn "No .env.example found; skipping .env creation."
        fi
    else
        info "Existing .env file detected."
    fi
}

check_docker() {
    info "Checking Docker and Docker Compose prerequisites..."
    if ! command -v docker &>/dev/null; then
        error "Docker is not installed or not in PATH. Please install Docker Engine: https://docs.docker.com/get-docker/"
        exit 1
    fi

    if docker compose version &>/dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &>/dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        error "Docker Compose (v2 or v1) is not installed."
        exit 1
    fi
    success "Docker environment detected: $($COMPOSE_CMD version)"
}

start_docker_stack() {
    check_docker
    ensure_env_file

    info "Building and starting Snapland containers with 2 backend replicas..."
    $COMPOSE_CMD -f infra/docker-compose.yml up -d --build --scale backend=2

    info "Waiting for Snapland stack to pass readiness health check..."
    local attempts=0
    local max_attempts=45
    local ready=0

    while [ $attempts -lt $max_attempts ]; do
        if curl -s -f http://localhost/health/ready &>/dev/null; then
            ready=1
            break
        fi
        attempts=$((attempts + 1))
        echo -n "."
        sleep 2
    done
    echo ""

    if [ $ready -eq 1 ]; then
        success "Snapland is healthy and ready!"
        print_endpoints
    else
        warn "Readiness probe did not pass within 90 seconds. Checking container status:"
        $COMPOSE_CMD -f infra/docker-compose.yml ps
        echo ""
        info "Inspect logs with: $COMPOSE_CMD -f infra/docker-compose.yml logs -f"
    fi
}

stop_docker_stack() {
    check_docker
    info "Stopping and removing Snapland containers and volumes..."
    $COMPOSE_CMD -f infra/docker-compose.yml down -v
    success "Snapland stack stopped and volumes removed."
}

setup_local() {
    ensure_env_file
    info "Setting up local Python virtual environment and dependencies..."

    PYTHON_CMD=""
    for cmd in python3.12 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" &>/dev/null; then
                PYTHON_CMD="$cmd"
                break
            fi
        fi
    done

    if [ -z "$PYTHON_CMD" ]; then
        error "Python 3.12+ is required. Please install Python 3.12 or newer."
        exit 1
    fi

    info "Using Python interpreter: $($PYTHON_CMD --version)"

    if [ ! -d ".venv" ]; then
        info "Creating virtual environment in .venv..."
        $PYTHON_CMD -m venv .venv
    fi

    # Activate venv depending on platform
    if [ -f ".venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source .venv/bin/activate
    elif [ -f ".venv/Scripts/activate" ]; then
        # shellcheck disable=SC1091
        source .venv/Scripts/activate
    fi

    info "Installing backend dependencies..."
    pip install --upgrade pip
    pip install hatchling
    pip install -e "backend/[dev]"

    info "Setting up frontend dependencies..."
    if ! command -v npm &>/dev/null; then
        error "Node.js / npm is required for frontend setup. Please install Node.js 20+."
        exit 1
    fi

    info "Installing shared-types..."
    (cd packages/shared-types && npm install)

    info "Installing frontend packages..."
    (cd frontend && npm install)

    success "Local development environment successfully bootstrapped!"
    echo ""
    echo -e "${BOLD}Next steps for local dev:${RESET}"
    echo "  1. Start Postgres & Redis: docker compose -f infra/docker-compose.yml up -d postgres redis"
    echo "  2. Run migrations:         cd backend && alembic upgrade head"
    echo "  3. Start backend:          uvicorn main:app --reload --port 8000"
    echo "  4. Start frontend:         cd frontend && npm run dev"
    echo ""
}

seed_database() {
    local count="${1:-1000}"
    info "Seeding database with $count polygons..."

    if [ -f ".venv/bin/python" ]; then
        .venv/bin/python scripts/seed_db.py --polygons "$count"
    elif [ -f ".venv/Scripts/python.exe" ]; then
        .venv/Scripts/python.exe scripts/seed_db.py --polygons "$count"
    elif command -v python3 &>/dev/null; then
        python3 scripts/seed_db.py --polygons "$count"
    elif command -v python &>/dev/null; then
        python scripts/seed_db.py --polygons "$count"
    else
        error "Python interpreter not found to execute seed script."
        exit 1
    fi
    success "Database seeding completed."
}

print_endpoints() {
    echo ""
    echo -e "${BOLD}Service Endpoints:${RESET}"
    echo -e "  Web Application:   ${CYAN}http://localhost${RESET}"
    echo -e "  API Documentation: ${CYAN}http://localhost/docs${RESET}"
    echo -e "  Health Check:      ${CYAN}http://localhost/health/ready${RESET}"
    echo -e "  Prometheus:        ${CYAN}http://localhost:9090${RESET}"
    echo -e "  Grafana:           ${CYAN}http://localhost:3000${RESET} (admin / admin)"
    echo ""
}

# Main routing
print_banner

MODE="${1:---docker}"

case "$MODE" in
    --docker)
        start_docker_stack
        ;;
    --local)
        setup_local
        ;;
    --seed)
        COUNT="${2:-1000}"
        seed_database "$COUNT"
        ;;
    --down)
        stop_docker_stack
        ;;
    -h|--help)
        print_help
        ;;
    *)
        error "Unknown option: $MODE"
        print_help
        exit 1
        ;;
esac
