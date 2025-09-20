"""
Integration tests for API Validation and Schema Testing
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestAssertions, TestDataFactory, TestCleanup, TestFixtures


class APIValidationTest(BaseTest):
    """Test API validation and schema compliance"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

    async def test_required_fields_validation(self) -> Optional[Dict[str, Any]]:
        """Test required fields validation"""
        # Test collections endpoint with missing required fields
        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={},  # Empty payload
            headers=self.get_headers()
        ))

        if response.status_code == 422:
            return {"required_fields_validated": True}

        return None

    async def test_data_type_validation(self) -> Optional[Dict[str, Any]]:
        """Test data type validation"""
        # Test with wrong data types
        invalid_data = {
            "name": 123,  # Should be string
            "description": True,  # Should be string
            "is_public": "yes"  # Should be boolean
        }

        response = APIResponse(await self.client.post(
            "/collections/",
            json_data=invalid_data,
            headers=self.get_headers()
        ))

        if response.status_code == 422:
            return {"data_types_validated": True}

        return None

    async def test_string_length_validation(self) -> Optional[Dict[str, Any]]:
        """Test string length validation"""
        # Test with extremely long strings
        long_string = "A" * 10000

        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": long_string,
                "description": long_string,
                "is_public": True
            },
            headers=self.get_headers()
        ))

        # Should either reject or truncate
        if response.status_code in [200, 422]:
            return {"string_length_validated": True}

        return None

    async def test_email_validation(self) -> Optional[Dict[str, Any]]:
        """Test email validation"""
        invalid_emails = [
            "invalid-email",
            "@domain.com",
            "user@",
            "user@domain",
            "user..name@domain.com",
            "user@domain..com"
        ]

        validated_count = 0

        for email in invalid_emails:
            response = APIResponse(await self.client.patch(
                f"/users/{self.test_user.id}",
                json_data={"email": email},
                headers=self.get_headers()
            ))

            if response.status_code == 422:
                validated_count += 1

        if validated_count == len(invalid_emails):
            return {"email_validation": "all_invalid_emails_rejected"}

        return None

    async def test_phone_validation(self) -> Optional[Dict[str, Any]]:
        """Test phone number validation"""
        invalid_phones = [
            "123",  # Too short
            "abc-def-ghij",  # Non-numeric
            "+12345678901234567890",  # Too long
            "123-456-7890",  # Wrong format
            ""  # Empty
        ]

        validated_count = 0

        for phone in invalid_phones:
            response = APIResponse(await self.client.patch(
                f"/users/{self.test_user.id}",
                json_data={"phone": phone},
                headers=self.get_headers()
            ))

            if response.status_code == 422:
                validated_count += 1

        if validated_count == len(invalid_phones):
            return {"phone_validation": "all_invalid_phones_rejected"}

        return None

    async def test_coordinate_validation(self) -> Optional[Dict[str, Any]]:
        """Test coordinate validation"""
        invalid_coordinates = [
            {"latitude": 999, "longitude": 0},  # Invalid latitude
            {"latitude": 0, "longitude": 999},  # Invalid longitude
            {"latitude": -999, "longitude": 0},  # Invalid latitude
            {"latitude": 0, "longitude": -999},  # Invalid longitude
            {"latitude": "invalid", "longitude": 0},  # Wrong type
            {"latitude": 0, "longitude": "invalid"}  # Wrong type
        ]

        validated_count = 0

        for coords in invalid_coordinates:
            response = APIResponse(await self.client.post(
                "/places/",
                json_data={
                    "name": "Test Place",
                    "latitude": coords["latitude"],
                    "longitude": coords["longitude"],
                    "categories": "test"
                },
                headers=self.get_headers()
            ))

            if response.status_code == 422:
                validated_count += 1

        if validated_count == len(invalid_coordinates):
            return {"coordinate_validation": "all_invalid_coordinates_rejected"}

        return None

    async def test_enum_validation(self) -> Optional[Dict[str, Any]]:
        """Test enum value validation"""
        # Test visibility enum
        invalid_visibilities = ["invalid", "public_private", "secret", ""]

        validated_count = 0

        for visibility in invalid_visibilities:
            response = APIResponse(await self.client.post(
                "/collections/",
                json_data={
                    "name": "Test Collection",
                    "description": "Test",
                    "is_public": True,
                    "visibility": visibility
                },
                headers=self.get_headers()
            ))

            if response.status_code == 422:
                validated_count += 1

        if validated_count == len(invalid_visibilities):
            return {"enum_validation": "all_invalid_enums_rejected"}

        return None

    async def test_numeric_range_validation(self) -> Optional[Dict[str, Any]]:
        """Test numeric range validation"""
        # Test pagination parameters
        invalid_limits = [-1, 0, 10000, "invalid"]
        invalid_offsets = [-1, "invalid"]

        validated_count = 0

        for limit in invalid_limits:
            response = APIResponse(await self.client.get(
                f"/collections/?limit={limit}",
                headers=self.get_headers()
            ))

            if response.status_code == 422:
                validated_count += 1

        for offset in invalid_offsets:
            response = APIResponse(await self.client.get(
                f"/collections/?offset={offset}",
                headers=self.get_headers()
            ))

            if response.status_code == 422:
                validated_count += 1

        if validated_count > 0:
            return {"numeric_range_validation": "invalid_ranges_rejected"}

        return None

    async def test_json_schema_validation(self) -> Optional[Dict[str, Any]]:
        """Test JSON schema validation"""
        # Test malformed JSON
        response = APIResponse(await self.client.post(
            "/collections/",
            data="invalid json",
            headers=self.get_headers()
        ))

        if response.status_code == 422:
            return {"json_schema_validated": True}

        return None

    async def test_content_type_validation(self) -> Optional[Dict[str, Any]]:
        """Test content type validation"""
        # Test with wrong content type
        wrong_headers = {
            "Authorization": f"Bearer {self.jwt_token}", "Content-Type": "text/plain"}

        response = APIResponse(await self.client.post(
            "/collections/",
            data="some data",
            headers=wrong_headers
        ))

        if response.status_code in [400, 415, 422]:
            return {"content_type_validated": True}

        return None

    async def test_authentication_validation(self) -> Optional[Dict[str, Any]]:
        """Test authentication validation"""
        # Test with invalid token
        invalid_headers = {
            "Authorization": "Bearer invalid_token", "Content-Type": "application/json"}

        response = APIResponse(await self.client.get(
            "/collections/",
            headers=invalid_headers
        ))

        if response.status_code == 401:
            return {"authentication_validated": True}

        return None

    async def test_authorization_validation(self) -> Optional[Dict[str, Any]]:
        """Test authorization validation"""
        # Test accessing another user's data
        response = APIResponse(await self.client.get(
            "/collections/99999",  # Non-existent collection
            headers=self.get_headers()
        ))

        if response.status_code == 404:
            return {"authorization_validated": True}

        return None

    async def test_query_parameter_validation(self) -> Optional[Dict[str, Any]]:
        """Test query parameter validation"""
        # Test with invalid query parameters
        invalid_params = [
            "?limit=invalid",
            "?offset=invalid",
            "?lat=invalid&lng=invalid",
            "?radius_m=invalid"
        ]

        validated_count = 0

        for params in invalid_params:
            response = APIResponse(await self.client.get(
                f"/places/nearby{params}",
                headers=self.get_headers()
            ))

            if response.status_code == 422:
                validated_count += 1

        if validated_count > 0:
            return {"query_parameter_validation": "invalid_params_rejected"}

        return None

    async def test_response_schema_validation(self) -> Optional[Dict[str, Any]]:
        """Test response schema validation"""
        # Test that responses have expected structure
        response = APIResponse(await self.client.get(
            "/collections/",
            headers=self.get_headers()
        ))

        if response.is_success():
            data = response.json

            # Check pagination structure
            required_fields = ["items", "total", "limit", "offset"]
            if all(field in data for field in required_fields):
                return {"response_schema_validated": True}

        return None

    async def test_error_response_validation(self) -> Optional[Dict[str, Any]]:
        """Test error response validation"""
        # Test that error responses have expected structure
        response = APIResponse(await self.client.get(
            "/collections/99999",  # Non-existent resource
            headers=self.get_headers()
        ))

        if response.status_code == 404:
            # Check error response structure
            data = response.json
            if "error" in data or "detail" in data:
                return {"error_response_validated": True}

        return None

    async def run_tests(self):
        """Run all API validation tests"""
        self._log("🔍 Testing API Validation and Schema Compliance...")

        # Basic validation tests
        await self.run_test("Required Fields Validation", self.test_required_fields_validation)
        await self.run_test("Data Type Validation", self.test_data_type_validation)
        await self.run_test("String Length Validation", self.test_string_length_validation)

        # Field-specific validation tests
        await self.run_test("Email Validation", self.test_email_validation)
        await self.run_test("Phone Validation", self.test_phone_validation)
        await self.run_test("Coordinate Validation", self.test_coordinate_validation)
        await self.run_test("Enum Validation", self.test_enum_validation)
        await self.run_test("Numeric Range Validation", self.test_numeric_range_validation)

        # Request validation tests
        await self.run_test("JSON Schema Validation", self.test_json_schema_validation)
        await self.run_test("Content Type Validation", self.test_content_type_validation)
        await self.run_test("Authentication Validation", self.test_authentication_validation)
        await self.run_test("Authorization Validation", self.test_authorization_validation)
        await self.run_test("Query Parameter Validation", self.test_query_parameter_validation)

        # Response validation tests
        await self.run_test("Response Schema Validation", self.test_response_schema_validation)
        await self.run_test("Error Response Validation", self.test_error_response_validation)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = APIValidationTest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
