#!/bin/bash

# Docker setup script for Korea Maps MCP Server
# This script helps with common Docker operations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env file exists
check_env_file() {
    if [ ! -f .env ]; then
        print_warning ".env file not found. Creating from .env.example..."
        if [ -f .env.example ]; then
            cp .env.example .env
            print_info "Created .env file from .env.example"
            print_warning "Please edit .env file and add your KAKAO_REST_API_KEY"
            return 1
        else
            print_error ".env.example file not found!"
            return 1
        fi
    fi

    # Check if API key is set
    if ! grep -q "^KAKAO_REST_API_KEY=.*[^=]" .env; then
        print_warning "KAKAO_REST_API_KEY is not set in .env file"
        print_warning "Please edit .env file and add your API key"
        return 1
    fi

    return 0
}

# Build Docker image
build_image() {
    print_info "Building Korea Maps MCP Server Docker image..."
    docker build -t korea-maps-mcp .
    print_info "Docker image built successfully!"
}

# Run different services
run_http() {
    print_info "Starting HTTP transport service on port 8000..."
    docker-compose up mcp-maps-http
}

run_sse() {
    print_info "Starting SSE transport service on port 8080..."
    docker-compose --profile sse up mcp-maps-sse
}

run_stdio() {
    print_info "Starting STDIO transport service..."
    docker-compose --profile stdio up mcp-maps-stdio
}

run_dev() {
    print_info "Starting development service on port 3000..."
    docker-compose --profile dev up mcp-maps-dev
}

# Test health endpoint
test_health() {
    local port=${1:-8000}
    print_info "Testing health endpoint on port $port..."

    # Start service in background
    docker-compose up -d mcp-maps-http

    # Wait for service to be ready
    sleep 5

    # Test health endpoint
    if curl -f http://localhost:$port/health > /dev/null 2>&1; then
        print_info "Health check passed!"
        curl http://localhost:$port/health | python -m json.tool
    else
        print_error "Health check failed!"
        docker-compose logs mcp-maps-http
        return 1
    fi

    # Stop service
    docker-compose down
}

# Show help
show_help() {
    cat << EOF
Korea Maps MCP Server Docker Setup Script

Usage: $0 [command]

Commands:
    build       Build the Docker image
    http        Run HTTP transport service (port 8000)
    sse         Run SSE transport service (port 8080)
    stdio       Run STDIO transport service
    dev         Run development service (port 3000)
    test        Test health endpoint
    logs        Show logs for all services
    stop        Stop all services
    clean       Stop and remove all containers and images
    help        Show this help message

Examples:
    $0 build
    $0 http
    $0 test
    $0 logs
    $0 clean

Environment:
    Make sure to set your KAKAO_REST_API_KEY in .env file
EOF
}

# Show logs
show_logs() {
    print_info "Showing logs for all services..."
    docker-compose logs -f
}

# Stop services
stop_services() {
    print_info "Stopping all services..."
    docker-compose down
    print_info "All services stopped!"
}

# Clean up
clean_up() {
    print_info "Cleaning up Docker containers and images..."
    docker-compose down --rmi all --volumes --remove-orphans
    print_info "Cleanup completed!"
}

# Main script logic
case "${1:-help}" in
    build)
        check_env_file || exit 1
        build_image
        ;;
    http)
        check_env_file || exit 1
        run_http
        ;;
    sse)
        check_env_file || exit 1
        run_sse
        ;;
    stdio)
        check_env_file || exit 1
        run_stdio
        ;;
    dev)
        check_env_file || exit 1
        run_dev
        ;;
    test)
        check_env_file || exit 1
        test_health
        ;;
    logs)
        show_logs
        ;;
    stop)
        stop_services
        ;;
    clean)
        clean_up
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
