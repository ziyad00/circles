"""
Integration tests for Error Handling and Edge Cases
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestAssertions


class ErrorHandlingTest(BaseTest):
    """Test error handling and edge cases"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

    async def test_invalid_authentication(self) -> Optional[Dict[str, Any]]:
        """Test invalid authentication scenarios"""
        # Test with invalid token
        invalid_headers = {
            "Authorization": "Bearer invalid_token", "Content-Type": "application/json"}
        response = APIResponse(await self.client.get("/collections/", headers=invalid_headers))

        if response.status_code == 401:
            return {"unauthorized": True}
        return None

    async def test_missing_authentication(self) -> Optional[Dict[str, Any]]:
        """Test missing authentication"""
        response = APIResponse(await self.client.get("/collections/"))

        if response.status_code == 401:
            return {"unauthorized": True}
        return None

    async def test_invalid_json_payload(self) -> Optional[Dict[str, Any]]:
        """Test invalid JSON payload"""
        response = APIResponse(await self.client.post(
            "/collections/",
            data="invalid json",
            headers=self.get_headers()
        ))

        if response.status_code == 422:
            return {"validation_error": True}
        return None

    async def test_missing_required_fields(self) -> Optional[Dict[str, Any]]:
        """Test missing required fields"""
        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={},  # Empty payload
            headers=self.get_headers()
        ))

        if response.status_code == 422:
            return {"validation_error": True}
        return None

    async def test_invalid_data_types(self) -> Optional[Dict[str, Any]]:
        """Test invalid data types"""
        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": 123,  # Should be string
                "description": True,  # Should be string
                "is_public": "yes"  # Should be boolean
            },
            headers=self.get_headers()
        ))

        if response.status_code == 422:
            return {"validation_error": True}
        return None

    async def test_nonexistent_resource(self) -> Optional[Dict[str, Any]]:
        """Test accessing nonexistent resources"""
        response = APIResponse(await self.client.get(
            "/collections/99999",  # Non-existent collection
            headers=self.get_headers()
        ))

        if response.status_code == 404:
            return {"not_found": True}
        return None

    async def test_invalid_place_coordinates(self) -> Optional[Dict[str, Any]]:
        """Test invalid place coordinates"""
        response = APIResponse(await self.client.post(
            "/places/",
            json_data={
                "name": "Test Place",
                "latitude": 999,  # Invalid latitude
                "longitude": 999,  # Invalid longitude
                "categories": "test"
            },
            headers=self.get_headers()
        ))

        if response.status_code == 422:
            return {"validation_error": True}
        return None

    async def test_duplicate_collection_name(self) -> Optional[Dict[str, Any]]:
        """Test duplicate collection name"""
        # Create first collection
        response1 = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": "Duplicate Test Collection",
                "description": "First collection",
                "is_public": True
            },
            headers=self.get_headers()
        ))

        if response1.is_success():
            # Try to create second collection with same name
            response2 = APIResponse(await self.client.post(
                "/collections/",
                json_data={
                    "name": "Duplicate Test Collection",
                    "description": "Second collection",
                    "is_public": True
                },
                headers=self.get_headers()
            ))

            # Should either succeed (if duplicates allowed) or fail with appropriate error
            if response2.status_code in [200, 409, 422]:
                return {"duplicate_handled": True}

        return None

    async def test_large_payload(self) -> Optional[Dict[str, Any]]:
        """Test large payload handling"""
        large_description = "A" * 10000  # 10KB description

        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": "Large Collection",
                "description": large_description,
                "is_public": True
            },
            headers=self.get_headers()
        ))

        # Should either succeed or fail gracefully
        if response.status_code in [200, 413, 422]:
            return {"large_payload_handled": True}
        return None

    async def test_sql_injection_attempt(self) -> Optional[Dict[str, Any]]:
        """Test SQL injection attempt"""
        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": "'; DROP TABLE users; --",
                "description": "SQL injection attempt",
                "is_public": True
            },
            headers=self.get_headers()
        ))

        # Should be handled safely (either succeed as normal text or fail gracefully)
        if response.status_code in [200, 422]:
            return {"sql_injection_safe": True}
        return None

    async def test_xss_attempt(self) -> Optional[Dict[str, Any]]:
        """Test XSS attempt"""
        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": "<script>alert('xss')</script>",
                "description": "XSS attempt",
                "is_public": True
            },
            headers=self.get_headers()
        ))

        # Should be handled safely
        if response.status_code in [200, 422]:
            return {"xss_safe": True}
        return None

    async def test_rate_limiting(self) -> Optional[Dict[str, Any]]:
        """Test rate limiting (if implemented)"""
        responses = []

        # Make multiple rapid requests
        for i in range(10):
            response = APIResponse(await self.client.get("/health"))
            responses.append(response.status_code)

        # All should succeed (no rate limiting implemented yet)
        if all(status == 200 for status in responses):
            return {"rate_limiting": "not_implemented"}
        elif any(status == 429 for status in responses):
            return {"rate_limiting": "implemented"}

        return None

    async def test_concurrent_requests(self) -> Optional[Dict[str, Any]]:
        """Test concurrent request handling"""
        import asyncio

        async def make_request():
            return APIResponse(await self.client.get("/health"))

        # Make 5 concurrent requests
        tasks = [make_request() for _ in range(5)]
        responses = await asyncio.gather(*tasks)

        # All should succeed
        if all(response.status_code == 200 for response in responses):
            return {"concurrent_requests": "handled"}

        return None

    async def test_malformed_url(self) -> Optional[Dict[str, Any]]:
        """Test malformed URL handling"""
        try:
            response = APIResponse(await self.client.get("/collections/%20invalid%20url"))
            # Should either return 404 or handle gracefully
            if response.status_code in [404, 400]:
                return {"malformed_url_handled": True}
        except Exception:
            # Exception is also acceptable for malformed URLs
            return {"malformed_url_exception": True}

        return None

    async def test_unicode_handling(self) -> Optional[Dict[str, Any]]:
        """Test Unicode character handling"""
        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": "测试集合 🎉",
                "description": "Unicode test: émojis and 中文",
                "is_public": True
            },
            headers=self.get_headers()
        ))

        if response.is_success():
            data = response.json
            assert data["name"] == "测试集合 🎉"
            assert data["description"] == "Unicode test: émojis and 中文"
            return {"unicode_handled": True}

        return None

    async def run_tests(self):
        """Run all error handling tests"""
        self._log("🛡️ Testing Error Handling and Edge Cases...")

        # Authentication tests
        await self.run_test("Invalid Authentication", self.test_invalid_authentication)
        await self.run_test("Missing Authentication", self.test_missing_authentication)

        # Validation tests
        await self.run_test("Invalid JSON Payload", self.test_invalid_json_payload)
        await self.run_test("Missing Required Fields", self.test_missing_required_fields)
        await self.run_test("Invalid Data Types", self.test_invalid_data_types)
        await self.run_test("Invalid Place Coordinates", self.test_invalid_place_coordinates)

        # Resource tests
        await self.run_test("Nonexistent Resource", self.test_nonexistent_resource)
        await self.run_test("Duplicate Collection Name", self.test_duplicate_collection_name)

        # Security tests
        await self.run_test("SQL Injection Attempt", self.test_sql_injection_attempt)
        await self.run_test("XSS Attempt", self.test_xss_attempt)

        # Performance tests
        await self.run_test("Large Payload", self.test_large_payload)
        await self.run_test("Rate Limiting", self.test_rate_limiting)
        await self.run_test("Concurrent Requests", self.test_concurrent_requests)

        # Edge cases
        await self.run_test("Malformed URL", self.test_malformed_url)
        await self.run_test("Unicode Handling", self.test_unicode_handling)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = ErrorHandlingTest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
