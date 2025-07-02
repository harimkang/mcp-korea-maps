# Korea Maps MCP Server

[![MCP](https://img.shields.io/badge/MCP-Compliant-blue)](https://github.com/cursor-ai/model-context-protocol)

A Model Context Protocol (MCP) server that provides access to Kakao Maps and Kakao Mobility APIs for Korean map services, geocoding, and route planning.

## Features

### 🗺️ **Location Services**

- **Address Geocoding**: Convert addresses or place names to coordinates
- **Place Search**: Search for places by keyword

### 🛣️ **Navigation Services**

- **Route Planning**: Get directions between two points (coordinates or addresses)
- **Future Directions**: Get route planning with departure time for traffic predictions
- **Multi-Destination Optimization**: Optimize routes to multiple destinations

## Available Tools

### 1. `geocode_address`

Convert address or place name to coordinates using Kakao Local API.

**Parameters:**

- `place_name` (string): Address or place name to geocode

**Example:**

```json
{
  "place_name": "서울시 강남구 테헤란로 152"
}
```

### 2. `search_places_by_keyword`

Search for places by keyword using Kakao Local API.

**Parameters:**

- `keyword` (string): Search keyword

**Example:**

```json
{
  "keyword": "카카오"
}
```

### 3. `get_directions_by_coordinates`

Get directions between two coordinate points.

**Parameters:**

- `origin_longitude` (number): Origin longitude
- `origin_latitude` (number): Origin latitude
- `dest_longitude` (number): Destination longitude
- `dest_latitude` (number): Destination latitude

**Example:**

```json
{
  "origin_longitude": 127.0357821,
  "origin_latitude": 37.4996954,
  "dest_longitude": 127.1086228,
  "dest_latitude": 37.4012191
}
```

### 4. `get_directions_by_address`

Get directions between two addresses.

**Parameters:**

- `origin_address` (string): Origin address
- `dest_address` (string): Destination address

**Example:**

```json
{
  "origin_address": "서울역",
  "dest_address": "강남역"
}
```

### 5. `get_future_directions`

Get future directions with departure time for traffic predictions.

**Parameters:**

- `origin_longitude` (number): Origin longitude
- `origin_latitude` (number): Origin latitude
- `destination_longitude` (number): Destination longitude
- `destination_latitude` (number): Destination latitude
- `departure_time` (string): Departure time in yyyyMMddHHmm format (e.g., "202507030900" for July 3, 2025 09:00)
- `priority` (string, optional): Route priority ("RECOMMEND", "TIME", "DISTANCE")
- `alternatives` (boolean, optional): Whether to return alternative routes
- `avoid` (string, optional): Roads to avoid (comma-separated: "toll", "highway", "ferry")
- `car_type` (number, optional): Car type (0-7): 0=General car, 1=Midsize car, 2=Compact car, 3-7=Commercial vehicles
- `car_fuel` (string, optional): Fuel type ("GASOLINE", "DIESEL", "LPG")
- `car_hipass` (boolean, optional): Whether car has Hi-Pass for toll roads

**Example:**

```json
{
  "origin_longitude": 127.0357821,
  "origin_latitude": 37.4996954,
  "destination_longitude": 127.1086228,
  "destination_latitude": 37.4012191,
  "departure_time": "202507030900",
  "priority": "TIME",
  "alternatives": true
}
```

### 6. `optimize_multi_destination_route`

Optimize routes to multiple destinations.

**Parameters:**

- `origin_longitude` (number): Origin longitude
- `origin_latitude` (number): Origin latitude
- `destinations` (string): JSON string of destinations array
- `radius` (number, optional): Search radius in meters (default: 5000, max: 10000)
- `priority` (string, optional): Route priority ("TIME" or "DISTANCE")

**Example:**

```json
{
  "origin_longitude": 127.0357821,
  "origin_latitude": 37.4996954,
  "destinations": "[{\"key\":\"dest1\",\"x\":127.1086228,\"y\":37.4012191},{\"key\":\"dest2\",\"x\":127.0357821,\"y\":37.4996954}]",
  "radius": 5000,
  "priority": "TIME"
}
```

## Setup

### 1. Get Kakao API Key

1. Visit [Kakao Developers](https://developers.kakao.com/)
2. Create an application
3. Enable Kakao Map services
4. Copy your REST API key

### 2. Environment Variables

Set the following environment variable:

```bash
export KAKAO_REST_API_KEY="your_kakao_rest_api_key"
```

**Optional Configuration:**

```bash
# Cache and Rate Limiting
export MCP_KAKAO_CACHE_TTL=3600          # Cache TTL in seconds (default: 3600)
export MCP_KAKAO_RATE_LIMIT_CALLS=10     # Rate limit calls (default: 10)
export MCP_KAKAO_RATE_LIMIT_PERIOD=1     # Rate limit period in seconds (default: 1)
export MCP_KAKAO_CONCURRENCY_LIMIT=5     # Concurrency limit (default: 5)

# Server Configuration (for HTTP transports)
export MCP_TRANSPORT=stdio               # Transport type: stdio, streamable-http, sse
export MCP_HOST=127.0.0.1               # Host address (default: 127.0.0.1)
export MCP_PORT=8000                     # Port number (default: 8000)
export MCP_PATH=/mcp                     # HTTP endpoint path (default: /mcp)
export MCP_LOG_LEVEL=INFO                # Log level (default: INFO)
```

### 3. Install Dependencies

```bash
pip install -e .
```

## Running the Server

### STDIO Transport (Default)

```bash
python -m src.mcp_maps.server
```

### HTTP Transport

```bash
python -m src.mcp_maps.server --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

### Server-Sent Events (SSE)

```bash
python -m src.mcp_maps.server --transport sse --host 127.0.0.1 --port 8000 --path /mcp
```

### Command Line Options

```bash
python -m src.mcp_maps.server --help

Options:
  --transport {stdio,streamable-http,sse}
                        Transport protocol to use (default: from environment or stdio)
  --host HOST           Host address for HTTP transports (default: from environment or 127.0.0.1)
  --port PORT           Port for HTTP transports (default: from environment or 8000)
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Log level for the server (default: from environment or INFO)
  --path PATH           Path for HTTP endpoints (default: from environment or /mcp)
```

## Integration with AI Tools

### Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "korea-maps": {
      "command": "python",
      "args": ["-m", "src.mcp_maps.server"],
      "cwd": "/path/to/mcp-korea-maps",
      "env": {
        "KAKAO_REST_API_KEY": "your_kakao_rest_api_key"
      }
    }
  }
}
```

### Cursor IDE

1. Install the MCP extension
2. Configure the server endpoint
3. Set environment variables

## API Rate Limits

The server includes built-in rate limiting and caching to respect Kakao API quotas:

- **Rate Limiting**: 10 calls per second (configurable)
- **Caching**: 1-hour TTL for geocoding and search results
- **Concurrency**: Limited to 5 concurrent requests
- **Retries**: Automatic retry with exponential backoff for transient errors

## Error Handling

All tools include comprehensive error handling:

- **Connection Errors**: Automatic retry with exponential backoff
- **API Errors**: Detailed error messages with status codes
- **Validation Errors**: Input validation with helpful error messages
- **Rate Limiting**: Automatic throttling to prevent quota exceeded errors

## Health Check

When running with HTTP transport, a health check endpoint is available:

```bash
curl http://localhost:8000/health
```

Response:

```json
{
  "status": "healthy",
  "service": "Korea Maps API MCP Server",
  "timestamp": 1234567890.123,
  "api_client": "initialized"
}
```

## Example Usage

### Getting Directions Between Two Addresses

```python
# This would be called through MCP
{
  "tool": "get_directions_by_address",
  "arguments": {
    "origin_address": "서울역",
    "dest_address": "강남역"
  }
}
```

### Finding Places Near a Location

```python
# First geocode an address
{
  "tool": "geocode_address",
  "arguments": {
    "place_name": "명동"
  }
}

# Then search for nearby coffee shops
{
  "tool": "search_places_by_keyword",
  "arguments": {
    "keyword": "카페"
  }
}
```

### Planning a Multi-Stop Route

```python
{
  "tool": "optimize_multi_destination_route",
  "arguments": {
    "origin_longitude": 127.0357821,
    "origin_latitude": 37.4996954,
    "destinations": "[{\"key\":\"coffee\",\"x\":127.1086228,\"y\":37.4012191},{\"key\":\"restaurant\",\"x\":127.0270968,\"y\":37.4979414}]",
    "radius": 10000,
    "priority": "TIME"
  }
}
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request
