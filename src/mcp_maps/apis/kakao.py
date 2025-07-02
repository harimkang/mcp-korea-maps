import os
import httpx
import logging
import asyncio
import json
from typing import Dict, Optional, Any, List, Union, ClassVar, Literal, cast
from cachetools import TTLCache
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from ratelimit import limits, sleep_and_retry


class KakaoApiError(Exception):
    """Base exception for Kakao API errors"""

    def __init__(
        self,
        message: str,
        response: Optional[httpx.Response] = None,
        request: Optional[httpx.Request] = None,
    ):
        super().__init__(message)
        self.message = message
        self.response = response
        self.request = request

    def __str__(self) -> str:
        base_str = super().__str__()
        if self.response:
            base_str += f" (Status Code: {self.response.status_code})"
        if self.request:
            base_str += f" (Request URL: {self.request.url})"
        return base_str


class KakaoApiConnectionError(KakaoApiError):
    """Connection error with Kakao API"""

    def __init__(self, message: str, request: Optional[httpx.Request] = None):
        super().__init__(message, response=None, request=request)


class KakaoApiClientError(KakaoApiError):
    """Client-side error with Kakao API requests (4xx)"""

    pass


class KakaoApiServerError(KakaoApiError):
    """Server-side error with Kakao API operations (5xx)"""

    pass


class KakaoMapsApiClient:
    """
    Client for Kakao Maps and Kakao Mobility APIs with caching and rate limiting.

    Features:
    - Geocoding (address to coordinates)
    - Address search by place name
    - Direction search by address or coordinates
    - Future direction search with departure time
    - Multi-destination route optimization
    - Response caching with TTL
    - Rate limiting to respect API quotas
    - Automatic retries for transient errors
    - Connection pooling
    """

    # Base URLs for different services
    KAKAO_LOCAL_API_BASE_URL = "https://dapi.kakao.com/v2/local"
    KAKAO_MOBILITY_API_BASE_URL = "https://apis-navi.kakaomobility.com/v1"

    # --- API Endpoints ---
    GEOCODE_ENDPOINT = "/search/address"
    KEYWORD_SEARCH_ENDPOINT = "/search/keyword"
    DIRECTIONS_ENDPOINT = "/directions"
    FUTURE_DIRECTIONS_ENDPOINT = "/future/directions"
    MULTI_DESTINATION_DIRECTIONS_ENDPOINT = "/destinations/directions"

    # Class-level connection pool and semaphore for concurrency control
    _shared_client: ClassVar[Optional[httpx.AsyncClient]] = None
    _client_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(
        self,
        api_key: str,
        cache_ttl: int = 3600,  # 1 hour cache
        rate_limit_calls: int = 10,
        rate_limit_period: int = 1,
        concurrency_limit: int = 5,
    ):
        """
        Initialize with API key and optional configurations.

        Args:
            api_key: The Kakao REST API key.
            cache_ttl: Time-to-live for cached responses in seconds.
            rate_limit_calls: Maximum number of API calls allowed.
            rate_limit_period: Time period (in seconds) for the rate limit.
            concurrency_limit: Maximum number of concurrent API requests.
        """
        self.api_key = api_key
        if not self.api_key or self.api_key == "missing_api_key":
            raise ValueError("Kakao API key is required")

        self._logger_name = "kakao_maps_api_client"

        # Store configuration parameters
        self._cache_ttl = cache_ttl
        self._rate_limit_calls = rate_limit_calls
        self._rate_limit_period = rate_limit_period
        self._concurrency_limit = concurrency_limit

        # Lazy initialization flags/placeholders
        self._is_fully_initialized = False
        self._cache: Optional[TTLCache] = None
        self._request_semaphore: Optional[asyncio.Semaphore] = None
        self.logger: Optional[logging.Logger] = None

    def _ensure_full_initialization(self):
        """Ensure all initialization tasks are completed before first API request"""
        if self._is_fully_initialized:
            return

        # Get logger first
        self.logger = logging.getLogger(self._logger_name)
        if not self.logger.hasHandlers():
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # Validate API key presence here before proceeding
        if not self.api_key or self.api_key == "missing_api_key":
            raise ValueError("Kakao API key is required")

        # Initialize cache with configured TTL
        self._cache = TTLCache(maxsize=1000, ttl=self._cache_ttl)

        # Initialize semaphore with configured concurrency limit
        self._request_semaphore = asyncio.Semaphore(self._concurrency_limit)

        self._is_fully_initialized = True

    @property
    def cache(self) -> TTLCache:
        self._ensure_full_initialization()
        if self._cache is None:
            raise RuntimeError("Cache not initialized")
        return self._cache

    @classmethod
    async def get_shared_client(cls) -> httpx.AsyncClient:
        """Get or create a shared HTTP client with connection pooling"""
        async with cls._client_lock:
            if cls._shared_client is None or cls._shared_client.is_closed:
                cls._shared_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0),
                    limits=httpx.Limits(
                        max_keepalive_connections=20, max_connections=100
                    ),
                )
        return cls._shared_client

    @classmethod
    async def close_all_connections(cls):
        """Close all shared connections"""
        async with cls._client_lock:
            if cls._shared_client is not None and not cls._shared_client.is_closed:
                await cls._shared_client.aclose()
                cls._shared_client = None

    def _process_response_error(self, response: httpx.Response):
        """Process HTTP errors and raise appropriate exceptions"""
        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_message = error_data.get("errorMessage", "Unknown error")
                # Log the full error response for debugging (only if logger is available)
                if self.logger is not None:
                    self.logger.error(f"API Error Response: {error_data}")
            except (json.JSONDecodeError, ValueError):
                error_message = f"HTTP {response.status_code}: {response.text}"

            if 400 <= response.status_code < 500:
                raise KakaoApiClientError(error_message, response=response)
            elif 500 <= response.status_code < 600:
                raise KakaoApiServerError(error_message, response=response)
            else:
                raise KakaoApiError(error_message, response=response)

    def _get_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Generate a unique cache key for an API request."""
        sorted_params = sorted(params.items())
        param_str = "&".join([f"{k}={v}" for k, v in sorted_params])
        return f"{endpoint}?{param_str}"

    @sleep_and_retry
    @limits(calls=10, period=1)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (httpx.ConnectTimeout, httpx.ConnectError, KakaoApiServerError)
        ),
        reraise=True,
    )
    async def _make_request(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Make an API request with caching, rate limiting, and error handling."""
        self._ensure_full_initialization()

        # Ensure logger and semaphore are initialized
        if self.logger is None or self._request_semaphore is None:
            raise RuntimeError("Client not properly initialized")

        # Generate cache key
        cache_key = None
        if use_cache and method.upper() == "GET":
            cache_key = self._get_cache_key(endpoint, params or {})
            cached_response = self.cache.get(cache_key)
            if cached_response is not None:
                self.logger.debug(f"Cache hit for {cache_key}")
                return cached_response

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"KakaoAK {self.api_key}",
        }

        url = f"{base_url}{endpoint}"

        async with self._request_semaphore:
            try:
                client = await self.get_shared_client()

                if method.upper() == "GET":
                    response = await client.get(url, params=params, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(url, json=json_data, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                self._process_response_error(response)
                result = response.json()

                # Cache successful GET responses
                if use_cache and method.upper() == "GET" and cache_key:
                    self.cache[cache_key] = result
                    self.logger.debug(f"Cached response for {cache_key}")

                return result

            except httpx.ConnectError as e:
                self.logger.error(f"Connection error: {e}")
                raise KakaoApiConnectionError(f"Failed to connect to Kakao API: {e}")
            except httpx.TimeoutException as e:
                self.logger.error(f"Request timeout: {e}")
                raise KakaoApiConnectionError(f"Request to Kakao API timed out: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                raise

    async def geocode(self, place_name: str) -> Dict[str, Any]:
        """
        Convert address or place name to coordinates using Kakao Local API.

        Args:
            place_name: Address or place name to geocode

        Returns:
            Dict containing geocoding results with coordinates
        """
        params = {"query": place_name}

        return cast(
            Dict[str, Any],
            await self._make_request(
                method="GET",
                base_url=self.KAKAO_LOCAL_API_BASE_URL,
                endpoint=self.GEOCODE_ENDPOINT,
                params=params,
            ),
        )

    async def search_by_keyword(self, keyword: str) -> Dict[str, Any]:
        """
        Search for places by keyword using Kakao Local API.

        Args:
            keyword: Search keyword

        Returns:
            Dict containing search results
        """
        params = {"query": keyword}

        return cast(
            Dict[str, Any],
            await self._make_request(
                method="GET",
                base_url=self.KAKAO_LOCAL_API_BASE_URL,
                endpoint=self.KEYWORD_SEARCH_ENDPOINT,
                params=params,
            ),
        )

    async def direction_search_by_coordinates(
        self,
        origin_longitude: float,
        origin_latitude: float,
        dest_longitude: float,
        dest_latitude: float,
    ) -> Dict[str, Any]:
        """
        Search for directions between two coordinate points using Kakao Mobility API.

        Args:
            origin_longitude: Origin longitude (x coordinate)
            origin_latitude: Origin latitude (y coordinate)
            dest_longitude: Destination longitude (x coordinate)
            dest_latitude: Destination latitude (y coordinate)

        Returns:
            Dict containing route information
        """
        params = {
            "origin": f"{origin_longitude},{origin_latitude}",
            "destination": f"{dest_longitude},{dest_latitude}",
        }

        return cast(
            Dict[str, Any],
            await self._make_request(
                method="GET",
                base_url=self.KAKAO_MOBILITY_API_BASE_URL,
                endpoint=self.DIRECTIONS_ENDPOINT,
                params=params,
            ),
        )

    async def direction_search_by_address(
        self, origin_address: str, dest_address: str
    ) -> Dict[str, Any]:
        """
        Search for directions between two addresses.
        First geocodes the addresses, then finds the route.
        If geocoding fails, fallback to keyword search.

        Args:
            origin_address: Origin address
            dest_address: Destination address

        Returns:
            Dict containing route information
        """

        async def get_coordinates_for_address(address: str) -> tuple:
            """Get coordinates for an address using geocoding or keyword search as fallback"""
            # Try geocoding first
            geocode_result = await self.geocode(address)

            if (
                geocode_result.get("documents")
                and geocode_result["documents"][0].get("x")
                and geocode_result["documents"][0].get("y")
            ):
                doc = geocode_result["documents"][0]
                return float(doc["x"]), float(doc["y"])

            # Fallback to keyword search
            keyword_result = await self.search_by_keyword(address)

            if (
                keyword_result.get("documents")
                and keyword_result["documents"][0].get("x")
                and keyword_result["documents"][0].get("y")
            ):
                doc = keyword_result["documents"][0]
                return float(doc["x"]), float(doc["y"])

            raise KakaoApiClientError(
                f"Could not find coordinates for address: {address}"
            )

        # Get coordinates for both addresses
        try:
            origin_coords, dest_coords = await asyncio.gather(
                get_coordinates_for_address(origin_address),
                get_coordinates_for_address(dest_address),
            )
        except Exception as e:
            raise KakaoApiClientError(
                f"Failed to get coordinates for one or both locations: {str(e)}"
            )

        origin_longitude, origin_latitude = origin_coords
        dest_longitude, dest_latitude = dest_coords

        return await self.direction_search_by_coordinates(
            origin_longitude, origin_latitude, dest_longitude, dest_latitude
        )

    async def future_direction_search_by_coordinates(
        self,
        origin_longitude: float,
        origin_latitude: float,
        destination_longitude: float,
        destination_latitude: float,
        departure_time: str,
        waypoints: Optional[str] = None,
        priority: Optional[Literal["RECOMMEND", "TIME", "DISTANCE"]] = None,
        avoid: Optional[str] = None,
        road_event: Optional[int] = None,
        alternatives: Optional[bool] = None,
        road_details: Optional[bool] = None,
        car_type: Optional[int] = None,
        car_fuel: Optional[Literal["GASOLINE", "DIESEL", "LPG"]] = None,
        car_hipass: Optional[bool] = None,
        summary: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Search for future directions with departure time using Kakao Mobility API.

        Args:
            origin_longitude: Origin longitude
            origin_latitude: Origin latitude
            destination_longitude: Destination longitude
            destination_latitude: Destination latitude
            departure_time: Departure time in ISO format
            waypoints: Waypoints coordinates
            priority: Route priority (RECOMMEND, TIME, DISTANCE)
            avoid: Roads to avoid
            road_event: Road event option (0-2)
            alternatives: Whether to return alternative routes
            road_details: Whether to include road details
            car_type: Car type (0-7)
            car_fuel: Fuel type
            car_hipass: Whether car has hipass
            summary: Whether to return summary only

        Returns:
            Dict containing future route information
        """
        params = {
            "origin": f"{origin_longitude},{origin_latitude}",
            "destination": f"{destination_longitude},{destination_latitude}",
            "departure_time": departure_time,
        }

        # Add optional parameters (converting non-string values)
        if waypoints is not None:
            params["waypoints"] = waypoints
        if priority is not None:
            params["priority"] = priority
        if avoid is not None:
            params["avoid"] = avoid
        if road_event is not None:
            params["roadevent"] = str(road_event)
        if alternatives is not None:
            params["alternatives"] = str(alternatives).lower()
        if road_details is not None:
            params["road_details"] = str(road_details).lower()
        if car_type is not None:
            params["car_type"] = str(car_type)
        if car_fuel is not None:
            params["car_fuel"] = car_fuel
        if car_hipass is not None:
            params["car_hipass"] = str(car_hipass).lower()
        if summary is not None:
            params["summary"] = str(summary).lower()

        return cast(
            Dict[str, Any],
            await self._make_request(
                method="GET",
                base_url=self.KAKAO_MOBILITY_API_BASE_URL,
                endpoint=self.FUTURE_DIRECTIONS_ENDPOINT,
                params=params,
            ),
        )

    async def multi_destination_direction_search(
        self,
        origin: Dict[str, Union[str, float]],
        destinations: List[Dict[str, Union[str, float]]],
        radius: int,
        priority: Optional[Literal["TIME", "DISTANCE"]] = None,
        avoid: Optional[List[str]] = None,
        roadevent: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Search for optimized routes to multiple destinations using Kakao Mobility API.

        Args:
            origin: Origin point with name (optional), x, y coordinates
            destinations: List of destination points with key, x, y coordinates (max 30)
            radius: Search radius in meters (max 10000)
            priority: Route priority (TIME or DISTANCE)
            avoid: List of road types to avoid
            roadevent: Road event option (0-2)

        Returns:
            Dict containing multi-destination route information
        """
        if len(destinations) > 30:
            raise KakaoApiClientError("Maximum 30 destinations allowed")

        if radius > 10000:
            raise KakaoApiClientError("Maximum radius is 10000 meters")

        request_body: Dict[str, Any] = {
            "origin": origin,
            "destinations": destinations,
            "radius": radius,
        }

        # Add optional parameters
        if priority is not None:
            request_body["priority"] = priority
        if avoid is not None:
            request_body["avoid"] = avoid
        if roadevent is not None:
            request_body["roadevent"] = roadevent

        return cast(
            Dict[str, Any],
            await self._make_request(
                method="POST",
                base_url=self.KAKAO_MOBILITY_API_BASE_URL,
                endpoint=self.MULTI_DESTINATION_DIRECTIONS_ENDPOINT,
                json_data=request_body,
                use_cache=False,  # POST requests are not cached
            ),
        )


# Convenience function for quick testing
async def main():
    """Example usage of the KakaoMapsApiClient"""
    api_key = os.environ.get("KAKAO_REST_API_KEY")
    if not api_key:
        print("Please set KAKAO_REST_API_KEY environment variable")
        return

    client = KakaoMapsApiClient(api_key=api_key)

    try:
        # Test geocoding
        result = await client.geocode("서울시 강남구 테헤란로 152")
        print("Geocoding result:", json.dumps(result, indent=2, ensure_ascii=False))

        # Test keyword search
        result = await client.search_by_keyword("카카오")
        print(
            "Keyword search result:", json.dumps(result, indent=2, ensure_ascii=False)
        )

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await KakaoMapsApiClient.close_all_connections()


if __name__ == "__main__":
    asyncio.run(main())
