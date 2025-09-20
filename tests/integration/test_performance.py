"""
Integration tests for Performance and Load Testing
"""
import asyncio
import time
from typing import Dict, Any, Optional, List

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse


class PerformanceTest(BaseTest):
    """Test performance and load handling"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)
        self.performance_results = {}

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

    async def test_response_times(self) -> Optional[Dict[str, Any]]:
        """Test response times for various endpoints"""
        endpoints = [
            ("/health", "GET", None),
            ("/places/nearby?lat=40.7128&lng=-74.0060&radius_m=1000&limit=10", "GET", None),
            ("/collections/", "GET", self.get_headers()),
            ("/dms/unread-count", "GET", self.get_headers()),
        ]

        response_times = {}

        for endpoint, method, headers in endpoints:
            start_time = time.time()

            if method == "GET":
                response = APIResponse(await self.client.get(endpoint, headers=headers))
            else:
                response = APIResponse(await self.client.post(endpoint, headers=headers))

            end_time = time.time()
            response_time = end_time - start_time

            response_times[endpoint] = {
                "time": response_time,
                "status": response.status_code,
                "success": response.is_success()
            }

        # Check if all endpoints respond within reasonable time (5 seconds)
        all_fast = all(rt["time"] < 5.0 for rt in response_times.values())

        if all_fast:
            return {"response_times": response_times, "all_fast": True}

        return None

    async def test_concurrent_requests(self) -> Optional[Dict[str, Any]]:
        """Test concurrent request handling"""
        async def make_request():
            start_time = time.time()
            response = APIResponse(await self.client.get("/health"))
            end_time = time.time()
            return {
                "status": response.status_code,
                "time": end_time - start_time,
                "success": response.is_success()
            }

        # Make 10 concurrent requests
        start_time = time.time()
        tasks = [make_request() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Analyze results
        successful_requests = sum(1 for r in results if r["success"])
        avg_response_time = sum(r["time"] for r in results) / len(results)
        max_response_time = max(r["time"] for r in results)

        if successful_requests == len(results):
            return {
                "concurrent_requests": len(results),
                "successful_requests": successful_requests,
                "total_time": total_time,
                "avg_response_time": avg_response_time,
                "max_response_time": max_response_time
            }

        return None

    async def test_database_performance(self) -> Optional[Dict[str, Any]]:
        """Test database performance with multiple operations"""
        # Create multiple collections
        start_time = time.time()

        collection_ids = []
        for i in range(5):
            response = APIResponse(await self.client.post(
                "/collections/",
                json_data={
                    "name": f"Performance Test Collection {i}",
                    "description": f"Collection {i} for performance testing",
                    "is_public": True
                },
                headers=self.get_headers()
            ))

            if response.is_success():
                collection_ids.append(response.json.get("id"))

        # Read all collections
        response = APIResponse(await self.client.get("/collections/", headers=self.get_headers()))

        # Clean up created collections
        for collection_id in collection_ids:
            await self.client.delete(f"/collections/{collection_id}", headers=self.get_headers())

        end_time = time.time()
        total_time = end_time - start_time

        if response.is_success():
            return {
                # +1 for read operation
                "operations_completed": len(collection_ids) + 1,
                "total_time": total_time,
                "avg_operation_time": total_time / (len(collection_ids) + 1)
            }

        return None

    async def test_memory_usage(self) -> Optional[Dict[str, Any]]:
        """Test memory usage with large datasets"""
        # Create a collection with a large description
        large_description = "A" * 50000  # 50KB description

        start_time = time.time()
        response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": "Large Memory Test Collection",
                "description": large_description,
                "is_public": True
            },
            headers=self.get_headers()
        ))
        end_time = time.time()

        if response.is_success():
            collection_id = response.json.get("id")

            # Read it back
            read_response = APIResponse(await self.client.get(
                f"/collections/{collection_id}",
                headers=self.get_headers()
            ))

            # Clean up
            await self.client.delete(f"/collections/{collection_id}", headers=self.get_headers())

            if read_response.is_success():
                return {
                    "large_data_handled": True,
                    "write_time": end_time - start_time,
                    "data_size": len(large_description)
                }

        return None

    async def test_search_performance(self) -> Optional[Dict[str, Any]]:
        """Test search performance"""
        search_queries = [
            "coffee",
            "restaurant",
            "cafe",
            "bar",
            "shop"
        ]

        search_times = []

        for query in search_queries:
            start_time = time.time()
            response = APIResponse(await self.client.post(
                "/places/search/advanced",
                json_data={
                    "query": query,
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "radius_km": 5,
                    "limit": 10
                },
                headers=self.get_headers()
            ))
            end_time = time.time()

            if response.is_success():
                search_times.append(end_time - start_time)

        if search_times:
            avg_search_time = sum(search_times) / len(search_times)
            max_search_time = max(search_times)

            return {
                "search_queries": len(search_queries),
                "avg_search_time": avg_search_time,
                "max_search_time": max_search_time,
                "all_searches_successful": len(search_times) == len(search_queries)
            }

        return None

    async def test_api_rate_limits(self) -> Optional[Dict[str, Any]]:
        """Test API rate limiting"""
        # Make rapid requests to test rate limiting
        requests_made = 0
        successful_requests = 0
        rate_limited_requests = 0

        start_time = time.time()

        # Make 20 rapid requests
        for i in range(20):
            response = APIResponse(await self.client.get("/health"))
            requests_made += 1

            if response.is_success():
                successful_requests += 1
            elif response.status_code == 429:
                rate_limited_requests += 1

            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.1)

        total_time = time.time() - start_time

        return {
            "requests_made": requests_made,
            "successful_requests": successful_requests,
            "rate_limited_requests": rate_limited_requests,
            "total_time": total_time,
            "requests_per_second": requests_made / total_time
        }

    async def test_error_recovery(self) -> Optional[Dict[str, Any]]:
        """Test error recovery and resilience"""
        # Test with invalid requests followed by valid ones
        error_scenarios = [
            # Non-existent resource
            ("/collections/99999", "GET", self.get_headers()),
            ("/collections/", "POST", self.get_headers()),  # Missing payload
        ]

        recovery_successful = True

        for endpoint, method, headers in error_scenarios:
            # Make invalid request
            if method == "GET":
                response = APIResponse(await self.client.get(endpoint, headers=headers))
            else:
                response = APIResponse(await self.client.post(endpoint, headers=headers))

            # Should get an error
            if not response.is_success():
                # Now make a valid request to test recovery
                valid_response = APIResponse(await self.client.get("/health"))
                if not valid_response.is_success():
                    recovery_successful = False
                    break

        if recovery_successful:
            return {"error_recovery": "successful"}

        return None

    async def test_data_consistency(self) -> Optional[Dict[str, Any]]:
        """Test data consistency under load"""
        # Create a collection
        create_response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": "Consistency Test Collection",
                "description": "Test data consistency",
                "is_public": True
            },
            headers=self.get_headers()
        ))

        if create_response.is_success():
            collection_id = create_response.json.get("id")

            # Make multiple concurrent reads
            async def read_collection():
                return APIResponse(await self.client.get(
                    f"/collections/{collection_id}",
                    headers=self.get_headers()
                ))

            # Make 5 concurrent reads
            tasks = [read_collection() for _ in range(5)]
            responses = await asyncio.gather(*tasks)

            # Check consistency
            all_successful = all(r.is_success() for r in responses)
            if all_successful:
                # Check that all responses have the same data
                first_data = responses[0].json
                consistent = all(
                    r.json.get("id") == first_data.get("id") and
                    r.json.get("name") == first_data.get("name")
                    for r in responses
                )

                # Clean up
                await self.client.delete(f"/collections/{collection_id}", headers=self.get_headers())

                if consistent:
                    return {"data_consistency": "maintained"}

        return None

    async def run_tests(self):
        """Run all performance tests"""
        self._log("⚡ Testing Performance and Load Handling...")

        # Basic performance tests
        await self.run_test("Response Times", self.test_response_times)
        await self.run_test("Concurrent Requests", self.test_concurrent_requests)
        await self.run_test("Database Performance", self.test_database_performance)

        # Advanced performance tests
        await self.run_test("Memory Usage", self.test_memory_usage)
        await self.run_test("Search Performance", self.test_search_performance)
        await self.run_test("API Rate Limits", self.test_api_rate_limits)

        # Resilience tests
        await self.run_test("Error Recovery", self.test_error_recovery)
        await self.run_test("Data Consistency", self.test_data_consistency)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = PerformanceTest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
