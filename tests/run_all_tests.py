#!/usr/bin/env python3
"""
Main test runner for all test suites
"""
from tests.e2e.test_user_workflow import UserWorkflowTest
from tests.e2e.test_advanced_workflows import AdvancedWorkflowsTest
from tests.unit.test_jwt_service import JWTServiceTest
from tests.unit.test_auth_service import AuthServiceTest
from tests.unit.test_place_data_service import PlaceDataServiceTest
from tests.unit.test_storage_service import StorageServiceTest
from tests.unit.test_models import ModelsTest
from tests.unit.test_database_service import DatabaseServiceTest
from tests.integration.test_dms import DMsAPITest
from tests.integration.test_dms_comprehensive import DMsComprehensiveTest
from tests.integration.test_places import PlacesAPITest
from tests.integration.test_collections import CollectionsAPITest
from tests.integration.test_collections_comprehensive import CollectionsComprehensiveTest
from tests.integration.test_checkins import CheckinsAPITest
from tests.integration.test_users import UsersAPITest
from tests.integration.test_error_handling import ErrorHandlingTest
from tests.integration.test_security import SecurityTest
from tests.integration.test_performance import PerformanceTest
from tests.integration.test_api_validation import APIValidationTest
from tests.utils.base_test import TestConfig, TestStatus
import asyncio
import os
import sys
import time
from typing import List, Dict, Any

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../app'))


class TestSuiteRunner:
    """Runs all test suites and provides comprehensive reporting"""

    def __init__(self, config: TestConfig = None):
        self.config = config or TestConfig(verbose=True)
        self.test_suites = []
        self.all_results = []

    def add_test_suite(self, name: str, test_class, *args, **kwargs):
        """Add a test suite to run"""
        self.test_suites.append({
            "name": name,
            "class": test_class,
            "args": args,
            "kwargs": kwargs
        })

    async def run_suite(self, suite_info: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single test suite"""
        suite_name = suite_info["name"]
        test_class = suite_info["class"]
        args = suite_info["args"]
        kwargs = suite_info["kwargs"]

        print(f"\n🚀 Running {suite_name}...")
        print("=" * 60)

        start_time = time.time()

        try:
            if hasattr(test_class, 'execute'):
                # Integration/E2E tests
                test_instance = test_class(self.config, *args, **kwargs)
                await test_instance.execute()
                results = test_instance.test_results
            else:
                # Unit tests
                test_instance = test_class(*args, **kwargs)
                test_instance.run_all_tests()
                results = []  # Unit tests don't return structured results yet

            duration = time.time() - start_time

            suite_result = {
                "name": suite_name,
                "duration": duration,
                "results": results,
                "status": "completed"
            }

            print(f"✅ {suite_name} completed in {duration:.2f}s")
            return suite_result

        except Exception as e:
            duration = time.time() - start_time
            print(f"❌ {suite_name} failed: {e}")

            suite_result = {
                "name": suite_name,
                "duration": duration,
                "results": [],
                "status": "failed",
                "error": str(e)
            }

            return suite_result

    async def run_all_suites(self):
        """Run all test suites"""
        print("🧪 Starting Comprehensive Test Suite")
        print("=" * 80)
        print(f"Base URL: {self.config.base_url}")
        print(f"Test User: {self.config.test_user_phone}")
        print("=" * 80)

        # Add all test suites
        # Unit Tests
        self.add_test_suite("JWT Service Unit Tests", JWTServiceTest)
        self.add_test_suite("Auth Service Unit Tests", AuthServiceTest)
        self.add_test_suite("Place Data Service Unit Tests",
                            PlaceDataServiceTest)
        self.add_test_suite("Storage Service Unit Tests", StorageServiceTest)
        self.add_test_suite("Database Models Unit Tests", ModelsTest)
        self.add_test_suite("Database Service Unit Tests", DatabaseServiceTest)

        # Integration Tests
        self.add_test_suite(
            "Collections API Integration Tests", CollectionsAPITest)
        self.add_test_suite(
            "Collections Comprehensive Integration Tests", CollectionsComprehensiveTest)
        self.add_test_suite("Places API Integration Tests", PlacesAPITest)
        self.add_test_suite("Check-ins API Integration Tests", CheckinsAPITest)
        self.add_test_suite("Users API Integration Tests", UsersAPITest)
        self.add_test_suite("DMs API Integration Tests", DMsAPITest)
        self.add_test_suite(
            "DMs Comprehensive Integration Tests", DMsComprehensiveTest)
        self.add_test_suite(
            "Error Handling Integration Tests", ErrorHandlingTest)
        self.add_test_suite("Security Integration Tests", SecurityTest)
        self.add_test_suite("Performance Integration Tests", PerformanceTest)
        self.add_test_suite(
            "API Validation Integration Tests", APIValidationTest)

        # End-to-End Tests
        self.add_test_suite("User Workflow E2E Tests", UserWorkflowTest)
        self.add_test_suite("Advanced Workflows E2E Tests",
                            AdvancedWorkflowsTest)

        # Run all suites
        for suite_info in self.test_suites:
            result = await self.run_suite(suite_info)
            self.all_results.append(result)

        # Print comprehensive summary
        self.print_comprehensive_summary()

    def print_comprehensive_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 COMPREHENSIVE TEST RESULTS SUMMARY")
        print("=" * 80)

        total_suites = len(self.all_results)
        completed_suites = len(
            [r for r in self.all_results if r["status"] == "completed"])
        failed_suites = len(
            [r for r in self.all_results if r["status"] == "failed"])

        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_errors = 0
        total_duration = 0

        for suite_result in self.all_results:
            total_duration += suite_result["duration"]

            if suite_result["status"] == "completed":
                results = suite_result["results"]
                total_tests += len(results)
                total_passed += len([r for r in results if r.status ==
                                    TestStatus.PASS])
                total_failed += len([r for r in results if r.status ==
                                    TestStatus.FAIL])
                total_errors += len([r for r in results if r.status ==
                                    TestStatus.ERROR])

        print(f"Test Suites: {completed_suites}/{total_suites} completed")
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {total_passed}")
        print(f"❌ Failed: {total_failed}")
        print(f"💥 Errors: {total_errors}")
        print(f"⏱️  Total Duration: {total_duration:.2f}s")

        if total_tests > 0:
            success_rate = (total_passed / total_tests) * 100
            print(f"📈 Success Rate: {success_rate:.1f}%")

        print("\n📋 Suite Details:")
        print("-" * 80)

        for suite_result in self.all_results:
            status_icon = "✅" if suite_result["status"] == "completed" else "❌"
            print(
                f"{status_icon} {suite_result['name']} ({suite_result['duration']:.2f}s)")

            if suite_result["status"] == "failed":
                print(f"   Error: {suite_result['error']}")
            elif suite_result["results"]:
                results = suite_result["results"]
                passed = len(
                    [r for r in results if r.status == TestStatus.PASS])
                failed = len(
                    [r for r in results if r.status == TestStatus.FAIL])
                errors = len(
                    [r for r in results if r.status == TestStatus.ERROR])
                print(
                    f"   Tests: {passed} passed, {failed} failed, {errors} errors")

        print("\n" + "=" * 80)

        # Overall status
        if failed_suites == 0 and total_failed == 0 and total_errors == 0:
            print("🎉 ALL TESTS PASSED! 🎉")
        else:
            print("⚠️  SOME TESTS FAILED - CHECK DETAILS ABOVE")

        print("=" * 80)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    runner = TestSuiteRunner(config)
    await runner.run_all_suites()

if __name__ == "__main__":
    asyncio.run(main())
