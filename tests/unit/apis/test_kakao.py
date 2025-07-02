import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from mcp_maps.apis.kakao import (
    KakaoMapsApiClient,
    KakaoApiError,
    KakaoApiClientError,
    KakaoApiServerError,
    KakaoApiConnectionError,
)


class TestKakaoMapsApiClient:
    """Test cases for KakaoMapsApiClient."""

    def test_init_with_valid_api_key(self, mock_api_key):
        """Test successful initialization with valid API key."""
        client = KakaoMapsApiClient(api_key=mock_api_key)
        assert client.api_key == mock_api_key
        assert client._cache_ttl == 3600  # Default value
        assert client._rate_limit_calls == 10  # Default value
        assert not client._is_fully_initialized

    def test_init_with_invalid_api_key(self):
        """Test initialization fails with invalid API key."""
        with pytest.raises(ValueError, match="Kakao API key is required"):
            KakaoMapsApiClient(api_key="")

        with pytest.raises(ValueError, match="Kakao API key is required"):
            KakaoMapsApiClient(api_key="missing_api_key")

    def test_init_with_custom_parameters(self, mock_api_key):
        """Test initialization with custom parameters."""
        client = KakaoMapsApiClient(
            api_key=mock_api_key,
            cache_ttl=1800,
            rate_limit_calls=20,
            rate_limit_period=2,
            concurrency_limit=15,
        )
        assert client._cache_ttl == 1800
        assert client._rate_limit_calls == 20
        assert client._rate_limit_period == 2
        assert client._concurrency_limit == 15

    def test_ensure_full_initialization(self, kakao_client):
        """Test lazy initialization."""
        assert not kakao_client._is_fully_initialized

        # Trigger initialization
        kakao_client._ensure_full_initialization()

        assert kakao_client._is_fully_initialized
        assert kakao_client._cache is not None
        assert kakao_client._request_semaphore is not None
        assert kakao_client.logger is not None

    def test_cache_property(self, kakao_client):
        """Test cache property triggers initialization."""
        cache = kakao_client.cache
        assert kakao_client._is_fully_initialized
        assert cache is not None

    @pytest.mark.asyncio
    async def test_get_shared_client(self):
        """Test shared HTTP client creation."""
        client1 = await KakaoMapsApiClient.get_shared_client()
        client2 = await KakaoMapsApiClient.get_shared_client()

        assert client1 is client2  # Should be the same instance
        assert isinstance(client1, httpx.AsyncClient)

        # Cleanup
        await KakaoMapsApiClient.close_all_connections()

    @pytest.mark.asyncio
    async def test_close_all_connections(self):
        """Test closing all connections."""
        client = await KakaoMapsApiClient.get_shared_client()
        assert not client.is_closed

        await KakaoMapsApiClient.close_all_connections()
        assert client.is_closed

    def test_get_cache_key(self, kakao_client):
        """Test cache key generation."""
        endpoint = "/test"
        params = {"query": "test", "page": 1}

        cache_key = kakao_client._get_cache_key(endpoint, params)
        expected = "/test?page=1&query=test"  # Sorted params
        assert cache_key == expected

    def test_process_response_error_400(self, kakao_client, mock_httpx_response):
        """Test 4xx error handling."""
        error_data = {"errorMessage": "Bad Request"}
        response = mock_httpx_response(error_data, 400)

        with pytest.raises(KakaoApiClientError, match="Bad Request"):
            kakao_client._process_response_error(response)

    def test_process_response_error_500(self, kakao_client, mock_httpx_response):
        """Test 5xx error handling."""
        error_data = {"errorMessage": "Internal Server Error"}
        response = mock_httpx_response(error_data, 500)

        with pytest.raises(KakaoApiServerError, match="Internal Server Error"):
            kakao_client._process_response_error(response)

    def test_process_response_error_without_json(self, kakao_client):
        """Test error handling when response has no JSON."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        response.json.side_effect = json.JSONDecodeError("test", "test", 0)
        response.text = "Bad Request"

        with pytest.raises(KakaoApiClientError, match="HTTP 400: Bad Request"):
            kakao_client._process_response_error(response)

    @pytest.mark.asyncio
    async def test_make_request_get_success(self, kakao_client, mock_geocode_response):
        """Test successful GET request."""
        with patch.object(kakao_client, "get_shared_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_geocode_response
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await kakao_client._make_request(
                method="GET",
                base_url="https://dapi.kakao.com/v2/local",
                endpoint="/search/address",
                params={"query": "test"},
            )

            assert result == mock_geocode_response
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_post_success(
        self, kakao_client, mock_multi_destination_response
    ):
        """Test successful POST request."""
        with patch.object(kakao_client, "get_shared_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_multi_destination_response
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            json_data = {"origin": {"x": 127.0, "y": 37.0}}
            result = await kakao_client._make_request(
                method="POST",
                base_url="https://apis-navi.kakaomobility.com/v1",
                endpoint="/destinations/directions",
                json_data=json_data,
            )

            assert result == mock_multi_destination_response
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_with_cache(self, kakao_client, mock_geocode_response):
        """Test request caching functionality."""
        with patch.object(kakao_client, "get_shared_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_geocode_response
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            # First request - should hit API
            result1 = await kakao_client._make_request(
                method="GET",
                base_url="https://dapi.kakao.com/v2/local",
                endpoint="/search/address",
                params={"query": "test"},
            )

            # Second request - should hit cache
            result2 = await kakao_client._make_request(
                method="GET",
                base_url="https://dapi.kakao.com/v2/local",
                endpoint="/search/address",
                params={"query": "test"},
            )

            assert result1 == result2 == mock_geocode_response
            # API should only be called once due to caching
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_connection_error(self, kakao_client):
        """Test connection error handling."""
        with patch.object(kakao_client, "get_shared_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(
                KakaoApiConnectionError, match="Failed to connect to Kakao API"
            ):
                await kakao_client._make_request(
                    method="GET",
                    base_url="https://dapi.kakao.com/v2/local",
                    endpoint="/search/address",
                    params={"query": "test"},
                )

    @pytest.mark.asyncio
    async def test_make_request_timeout_error(self, kakao_client):
        """Test timeout error handling."""
        with patch.object(kakao_client, "get_shared_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("Request timed out")
            mock_get_client.return_value = mock_client

            with pytest.raises(
                KakaoApiConnectionError, match="Request to Kakao API timed out"
            ):
                await kakao_client._make_request(
                    method="GET",
                    base_url="https://dapi.kakao.com/v2/local",
                    endpoint="/search/address",
                    params={"query": "test"},
                )

    @pytest.mark.asyncio
    async def test_geocode(self, kakao_client, mock_geocode_response):
        """Test geocode method."""
        with patch.object(
            kakao_client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=mock_geocode_response,
        ) as mock_request:
            result = await kakao_client.geocode("서울시 강남구 테헤란로 152")

            assert result == mock_geocode_response
            mock_request.assert_called_once_with(
                method="GET",
                base_url=kakao_client.KAKAO_LOCAL_API_BASE_URL,
                endpoint=kakao_client.GEOCODE_ENDPOINT,
                params={"query": "서울시 강남구 테헤란로 152"},
            )

    @pytest.mark.asyncio
    async def test_search_by_keyword(self, kakao_client, mock_keyword_search_response):
        """Test search_by_keyword method."""
        with patch.object(
            kakao_client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=mock_keyword_search_response,
        ) as mock_request:
            result = await kakao_client.search_by_keyword("카카오")

            assert result == mock_keyword_search_response
            mock_request.assert_called_once_with(
                method="GET",
                base_url=kakao_client.KAKAO_LOCAL_API_BASE_URL,
                endpoint=kakao_client.KEYWORD_SEARCH_ENDPOINT,
                params={"query": "카카오"},
            )

    @pytest.mark.asyncio
    async def test_direction_search_by_coordinates(
        self, kakao_client, mock_directions_response
    ):
        """Test direction_search_by_coordinates method."""
        with patch.object(
            kakao_client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=mock_directions_response,
        ) as mock_request:
            result = await kakao_client.direction_search_by_coordinates(
                origin_longitude=127.0357821,
                origin_latitude=37.4996954,
                dest_longitude=127.1086228,
                dest_latitude=37.4012191,
            )

            assert result == mock_directions_response
            mock_request.assert_called_once_with(
                method="GET",
                base_url=kakao_client.KAKAO_MOBILITY_API_BASE_URL,
                endpoint=kakao_client.DIRECTIONS_ENDPOINT,
                params={
                    "origin": "127.0357821,37.4996954",
                    "destination": "127.1086228,37.4012191",
                },
            )

    @pytest.mark.asyncio
    async def test_direction_search_by_address(
        self, kakao_client, mock_geocode_response, mock_directions_response
    ):
        """Test direction_search_by_address method."""
        with (
            patch.object(
                kakao_client, "geocode", return_value=mock_geocode_response
            ) as mock_geocode,
            patch.object(
                kakao_client,
                "direction_search_by_coordinates",
                return_value=mock_directions_response,
            ) as mock_directions,
        ):
            result = await kakao_client.direction_search_by_address("출발지", "목적지")

            assert result == mock_directions_response
            assert (
                mock_geocode.call_count == 2
            )  # Called for both origin and destination
            mock_directions.assert_called_once()

    @pytest.mark.asyncio
    async def test_direction_search_by_address_geocode_failure(self, kakao_client):
        """Test direction_search_by_address with geocoding failure."""
        failed_geocode_response = {"documents": []}
        failed_keyword_response = {"documents": []}

        with (
            patch.object(kakao_client, "geocode", return_value=failed_geocode_response),
            patch.object(
                kakao_client, "search_by_keyword", return_value=failed_keyword_response
            ),
        ):
            with pytest.raises(
                KakaoApiClientError, match="Could not find coordinates for address"
            ):
                await kakao_client.direction_search_by_address("출발지", "목적지")

    @pytest.mark.asyncio
    async def test_future_direction_search_by_coordinates(
        self, kakao_client, mock_directions_response
    ):
        """Test future_direction_search_by_coordinates method."""
        with patch.object(
            kakao_client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=mock_directions_response,
        ) as mock_request:
            result = await kakao_client.future_direction_search_by_coordinates(
                origin_longitude=127.0357821,
                origin_latitude=37.4996954,
                destination_longitude=127.1086228,
                destination_latitude=37.4012191,
                departure_time="2024-01-01T09:00:00",
                priority="TIME",
                alternatives=True,
            )

            assert result == mock_directions_response
            expected_params = {
                "origin": "127.0357821,37.4996954",
                "destination": "127.1086228,37.4012191",
                "departure_time": "2024-01-01T09:00:00",
                "priority": "TIME",
                "alternatives": "true",  # Boolean converted to lowercase string
            }
            mock_request.assert_called_once_with(
                method="GET",
                base_url=kakao_client.KAKAO_MOBILITY_API_BASE_URL,
                endpoint=kakao_client.FUTURE_DIRECTIONS_ENDPOINT,
                params=expected_params,
            )

    @pytest.mark.asyncio
    async def test_multi_destination_direction_search(
        self, kakao_client, mock_multi_destination_response
    ):
        """Test multi_destination_direction_search method."""
        origin = {"name": "출발지", "x": 127.0357821, "y": 37.4996954}
        destinations = [{"key": "dest1", "x": 127.1086228, "y": 37.4012191}]
        radius = 5000

        with patch.object(
            kakao_client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=mock_multi_destination_response,
        ) as mock_request:
            result = await kakao_client.multi_destination_direction_search(
                origin=origin, destinations=destinations, radius=radius, priority="TIME"
            )

            assert result == mock_multi_destination_response
            expected_json_data = {
                "origin": origin,
                "destinations": destinations,
                "radius": radius,
                "priority": "TIME",
            }
            mock_request.assert_called_once_with(
                method="POST",
                base_url=kakao_client.KAKAO_MOBILITY_API_BASE_URL,
                endpoint=kakao_client.MULTI_DESTINATION_DIRECTIONS_ENDPOINT,
                json_data=expected_json_data,
                use_cache=False,
            )

    @pytest.mark.asyncio
    async def test_multi_destination_direction_search_too_many_destinations(
        self, kakao_client
    ):
        """Test multi_destination_direction_search with too many destinations."""
        origin = {"x": 127.0, "y": 37.0}
        destinations = [
            {"key": f"dest{i}", "x": 127.0, "y": 37.0} for i in range(31)
        ]  # 31 destinations

        with pytest.raises(
            KakaoApiClientError, match="Maximum 30 destinations allowed"
        ):
            await kakao_client.multi_destination_direction_search(
                origin=origin, destinations=destinations, radius=5000
            )

    @pytest.mark.asyncio
    async def test_multi_destination_direction_search_radius_too_large(
        self, kakao_client
    ):
        """Test multi_destination_direction_search with radius too large."""
        origin = {"x": 127.0, "y": 37.0}
        destinations = [{"key": "dest1", "x": 127.0, "y": 37.0}]

        with pytest.raises(KakaoApiClientError, match="Maximum radius is 10000 meters"):
            await kakao_client.multi_destination_direction_search(
                origin=origin,
                destinations=destinations,
                radius=15000,  # Too large
            )

    def test_unsupported_http_method(self, kakao_client):
        """Test unsupported HTTP method."""
        with patch.object(kakao_client, "get_shared_client"):
            with pytest.raises(ValueError, match="Unsupported HTTP method"):
                asyncio.run(
                    kakao_client._make_request(
                        method="DELETE",
                        base_url="https://dapi.kakao.com/v2/local",
                        endpoint="/test",
                    )
                )


class TestKakaoApiExceptions:
    """Test cases for Kakao API exception classes."""

    def test_kakao_api_error(self):
        """Test KakaoApiError."""
        error = KakaoApiError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"

    def test_kakao_api_error_with_response(self):
        """Test KakaoApiError with response."""
        response = MagicMock()
        response.status_code = 400

        error = KakaoApiError("Test error", response=response)
        assert "Status Code: 400" in str(error)

    def test_kakao_api_error_with_request(self):
        """Test KakaoApiError with request."""
        request = MagicMock()
        request.url = "https://api.example.com/test"

        error = KakaoApiError("Test error", request=request)
        assert "Request URL:" in str(error)

    def test_kakao_api_connection_error(self):
        """Test KakaoApiConnectionError."""
        error = KakaoApiConnectionError("Connection failed")
        assert str(error) == "Connection failed"
        assert error.response is None

    def test_kakao_api_client_error(self):
        """Test KakaoApiClientError."""
        error = KakaoApiClientError("Client error")
        assert str(error) == "Client error"

    def test_kakao_api_server_error(self):
        """Test KakaoApiServerError."""
        error = KakaoApiServerError("Server error")
        assert str(error) == "Server error"
