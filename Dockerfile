# Generated Dockerfile for Korea Maps MCP Server
# syntax=docker/dockerfile:1

# Use the Python version confirmed from pyproject.toml
FROM python:3.12-slim

# Install uv and curl for health checks
# --no-cache-dir reduces image size
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir uv

# Set the working directory in the container
WORKDIR /app

# Copy dependency files first to leverage Docker cache
COPY pyproject.toml ./

# Generate requirements.txt from pyproject.toml dependencies section directly
# This avoids trying to find the local project and only focuses on external dependencies
RUN python -c "import tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; print('\n'.join(deps))" > requirements.txt

# Install dependencies using pip from the requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application source code (including the src directory)
COPY . .

# Install the project itself from the src directory
# This makes the mcp_maps package available to the Python interpreter
# --no-deps prevents reinstalling already synced dependencies
# --system is required because we are not in a virtual environment
RUN uv pip install . --no-deps --system

# Build arguments for configuration (can be set during docker build)
ARG MCP_TRANSPORT=stdio
ARG MCP_HOST=0.0.0.0
ARG MCP_PORT=8000
ARG MCP_PATH=/mcp
ARG MCP_LOG_LEVEL=INFO

# Set environment variables from build args (these can be overridden at runtime)
ENV MCP_TRANSPORT=${MCP_TRANSPORT}
ENV MCP_HOST=${MCP_HOST}
ENV MCP_PORT=${MCP_PORT}
ENV MCP_PATH=${MCP_PATH}
ENV MCP_LOG_LEVEL=${MCP_LOG_LEVEL}

# Set the API key as an environment variable
# IMPORTANT: It's strongly recommended to pass the API key securely at runtime using -e.
# Example runtime command: docker run -e KAKAO_REST_API_KEY="YOUR_ACTUAL_API_KEY" ...
# ENV KAKAO_REST_API_KEY="YOUR_ACTUAL_API_KEY" # Avoid hardcoding if possible

# Expose common ports (8000 is default, but can be changed at runtime)
EXPOSE 8000 8080 3000

# Create a health check for HTTP transports
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD if [ "$MCP_TRANSPORT" = "stdio" ]; then \
            echo "stdio transport - health check passed"; \
        else \
            curl -f http://localhost:${MCP_PORT}/health || exit 1; \
        fi

# Command to run the application
# Use python -m directly instead of uv run to avoid creating a virtual env at runtime
CMD ["python", "-m", "src.mcp_maps.server"]
