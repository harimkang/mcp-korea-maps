import pytest
import httpx
from unittest.mock import MagicMock
from mcp_maps.apis.kakao import KakaoMapsApiClient


@pytest.fixture
def mock_api_key():
    """Provide a mock API key for testing."""
    return "test_kakao_api_key"


@pytest.fixture
def kakao_client(mock_api_key):
    """Create a KakaoMapsApiClient instance with mock API key."""
    return KakaoMapsApiClient(
        api_key=mock_api_key,
        cache_ttl=60,  # Short cache for testing
        rate_limit_calls=100,  # High limit for testing
        rate_limit_period=1,
        concurrency_limit=10,
    )


@pytest.fixture
def mock_httpx_response():
    """Create a mock httpx Response object."""

    def _create_response(json_data, status_code=200):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = json_data
        response.text = str(json_data)
        return response

    return _create_response


@pytest.fixture
def mock_geocode_response():
    """Mock response for geocoding API."""
    return {
        "meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
        "documents": [
            {
                "address_name": "서울 강남구 테헤란로 152",
                "y": "37.4996954",
                "x": "127.0357821",
                "address_type": "ROAD_ADDR",
                "address": {
                    "address_name": "서울 강남구 역삼동 833",
                    "region_1depth_name": "서울",
                    "region_2depth_name": "강남구",
                    "region_3depth_name": "역삼동",
                    "mountain_yn": "N",
                    "main_address_no": "833",
                    "sub_address_no": "",
                    "zip_code": "06236",
                },
                "road_address": {
                    "address_name": "서울 강남구 테헤란로 152",
                    "region_1depth_name": "서울",
                    "region_2depth_name": "강남구",
                    "region_3depth_name": "역삼동",
                    "road_name": "테헤란로",
                    "underground_yn": "N",
                    "main_building_no": "152",
                    "sub_building_no": "",
                    "building_name": "강남파이낸스센터",
                    "zone_no": "06236",
                },
            }
        ],
    }


@pytest.fixture
def mock_keyword_search_response():
    """Mock response for keyword search API."""
    return {
        "meta": {
            "total_count": 1,
            "pageable_count": 1,
            "is_end": True,
            "same_name": {"region": [], "keyword": "카카오", "selected_region": ""},
        },
        "documents": [
            {
                "place_name": "카카오 판교아지트",
                "distance": "",
                "place_url": "http://place.map.kakao.com/26338954",
                "category_name": "서비스,산업 > 인터넷,IT > 소프트웨어 개발",
                "address_name": "경기 성남시 분당구 정자일로 235",
                "road_address_name": "경기 성남시 분당구 정자일로 235",
                "id": "26338954",
                "phone": "1577-3754",
                "category_group_code": "",
                "category_group_name": "",
                "x": "127.1086228",
                "y": "37.4012191",
            }
        ],
    }


@pytest.fixture
def mock_directions_response():
    """Mock response for directions API."""
    return {
        "trans_id": "12345",
        "routes": [
            {
                "result_code": 0,
                "result_msg": "",
                "summary": {
                    "origin": {"name": "출발지", "x": 127.0357821, "y": 37.4996954},
                    "destination": {
                        "name": "목적지",
                        "x": 127.1086228,
                        "y": 37.4012191,
                    },
                    "waypoints": [],
                    "priority": "RECOMMEND",
                    "bound": {
                        "min_x": 127.0357821,
                        "min_y": 37.4012191,
                        "max_x": 127.1086228,
                        "max_y": 37.4996954,
                    },
                    "fare": {"taxi": 8100, "toll": 0},
                    "distance": 7889,
                    "duration": 1200,
                },
                "sections": [
                    {
                        "distance": 7889,
                        "duration": 1200,
                        "bound": {
                            "min_x": 127.0357821,
                            "min_y": 37.4012191,
                            "max_x": 127.1086228,
                            "max_y": 37.4996954,
                        },
                        "roads": [],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def mock_multi_destination_response():
    """Mock response for multi-destination directions API."""
    return {
        "trans_id": "67890",
        "routes": [
            {
                "result_code": 0,
                "result_msg": "",
                "summary": {
                    "origin": {"name": "출발지", "x": 127.0357821, "y": 37.4996954},
                    "destinations": [
                        {"key": "dest1", "x": 127.1086228, "y": 37.4012191}
                    ],
                    "distance": 7889,
                    "duration": 1200,
                },
            }
        ],
    }


@pytest.fixture
def mock_error_response():
    """Mock error response."""
    return {"errorType": "InvalidArgument", "message": "Invalid request"}
