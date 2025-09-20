"""
HTTP client utilities for testing
"""
import httpx
from typing import Dict, Any, Optional, Union
import json


class TestHTTPClient:
    """HTTP client for API testing"""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint"""
        endpoint = endpoint.lstrip('/')
        return f"{self.base_url}/{endpoint}"

    async def get(self, endpoint: str, headers: Optional[Dict[str, str]] = None,
                  params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Make GET request"""
        url = self._build_url(endpoint)
        return await self.client.get(url, headers=headers, params=params)

    async def post(self, endpoint: str, data: Optional[Dict[str, Any]] = None,
                   json_data: Optional[Dict[str, Any]] = None,
                   files: Optional[Dict[str, Any]] = None,
                   headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        """Make POST request"""
        url = self._build_url(endpoint)
        if files:
            return await self.client.post(url, files=files, headers=headers)
        elif json_data:
            return await self.client.post(url, json=json_data, headers=headers)
        else:
            return await self.client.post(url, data=data, headers=headers)

    async def put(self, endpoint: str, data: Optional[Dict[str, Any]] = None,
                  json_data: Optional[Dict[str, Any]] = None,
                  headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        """Make PUT request"""
        url = self._build_url(endpoint)
        if json_data:
            return await self.client.put(url, json=json_data, headers=headers)
        else:
            return await self.client.put(url, data=data, headers=headers)

    async def delete(self, endpoint: str, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        """Make DELETE request"""
        url = self._build_url(endpoint)
        return await self.client.delete(url, headers=headers)

    async def patch(self, endpoint: str, data: Optional[Dict[str, Any]] = None,
                    json_data: Optional[Dict[str, Any]] = None,
                    headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        """Make PATCH request"""
        url = self._build_url(endpoint)
        if json_data:
            return await self.client.patch(url, json=json_data, headers=headers)
        else:
            return await self.client.patch(url, data=data, headers=headers)


class APIResponse:
    """Wrapper for API responses with helper methods"""

    def __init__(self, response: httpx.Response):
        self.response = response
        self._json_data = None

    @property
    def status_code(self) -> int:
        """Get status code"""
        return self.response.status_code

    @property
    def text(self) -> str:
        """Get response text"""
        return self.response.text

    @property
    def json(self) -> Dict[str, Any]:
        """Get JSON data (cached)"""
        if self._json_data is None:
            try:
                self._json_data = self.response.json()
            except json.JSONDecodeError:
                self._json_data = {}
        return self._json_data

    def is_success(self) -> bool:
        """Check if response is successful (2xx)"""
        return 200 <= self.status_code < 300

    def is_client_error(self) -> bool:
        """Check if response is client error (4xx)"""
        return 400 <= self.status_code < 500

    def is_server_error(self) -> bool:
        """Check if response is server error (5xx)"""
        return 500 <= self.status_code < 600

    def get_error_message(self) -> str:
        """Get error message from response"""
        if self.is_success():
            return ""

        try:
            data = self.json
            if isinstance(data, dict):
                return data.get('detail', data.get('message', self.text))
            return self.text
        except:
            return self.text
