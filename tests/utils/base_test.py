"""
Base test class with common functionality
"""
from sqlalchemy import select
from app.services.jwt_service import JWTService
from app.models import User
from app.database import AsyncSessionLocal
import asyncio
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List, Union
import json

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../app'))


# Set database URL for testing
os.environ['DATABASE_URL'] = 'sqlite:///./circles.db'


class TestStatus(Enum):
    """Test execution status"""
    PASS = "✅ PASS"
    FAIL = "❌ FAIL"
    SKIP = "⏭️ SKIP"
    ERROR = "💥 ERROR"


@dataclass
class TestResult:
    """Test result data structure"""
    test_name: str
    status: TestStatus
    message: str
    duration: float
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class TestConfig:
    """Test configuration"""
    base_url: str = "http://127.0.0.1:8000"
    test_user_phone: str = "+1234567890"
    test_user_username: str = "testuser"
    test_user_name: str = "Test User"
    timeout: int = 30
    verbose: bool = True


class BaseTest(ABC):
    """Base test class with common functionality"""

    def __init__(self, config: TestConfig = None):
        self.config = config or TestConfig()
        self.test_user: Optional[User] = None
        self.jwt_token: Optional[str] = None
        self.test_results: List[TestResult] = []
        self.session = None

    async def setup(self):
        """Setup test environment"""
        await self._create_test_user()
        await self._setup_test_data()

    async def teardown(self):
        """Cleanup after tests"""
        if self.session:
            await self.session.close()

    async def _create_test_user(self):
        """Create or get test user"""
        async with AsyncSessionLocal() as db:
            try:
                # Check if test user already exists
                result = await db.execute(
                    select(User).where(User.phone ==
                                       self.config.test_user_phone)
                )
                user = result.scalar_one_or_none()

                if not user:
                    # Create test user
                    user = User(
                        phone=self.config.test_user_phone,
                        username=self.config.test_user_username,
                        name=self.config.test_user_name,
                        is_verified=True
                    )
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    self._log(f"Created test user: {user.id}")
                else:
                    self._log(f"Using existing test user: {user.id}")

                self.test_user = user

                # Generate JWT token
                jwt_service = JWTService()
                self.jwt_token = jwt_service.create_token(user.id)
                self._log(f"JWT token generated: {self.jwt_token[:20]}...")

            except Exception as e:
                self._log(f"Error creating test user: {e}", level="ERROR")
                raise

    async def _setup_test_data(self):
        """Setup test data - override in subclasses"""
        pass

    def get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with JWT token"""
        return {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json"
        }

    async def run_test(self, test_name: str, test_func, *args, **kwargs) -> TestResult:
        """Run a single test and record results"""
        start_time = time.time()
        try:
            result = await test_func(*args, **kwargs)
            duration = time.time() - start_time

            if result is not None:
                test_result = TestResult(
                    test_name=test_name,
                    status=TestStatus.PASS,
                    message="Test passed",
                    duration=duration,
                    data=result
                )
            else:
                test_result = TestResult(
                    test_name=test_name,
                    status=TestStatus.FAIL,
                    message="Test failed - no result returned",
                    duration=duration
                )

        except Exception as e:
            duration = time.time() - start_time
            test_result = TestResult(
                test_name=test_name,
                status=TestStatus.ERROR,
                message=f"Test error: {str(e)}",
                duration=duration,
                error=str(e)
            )

        self.test_results.append(test_result)
        self._log_test_result(test_result)
        return test_result

    def _log(self, message: str, level: str = "INFO"):
        """Log message with timestamp"""
        if self.config.verbose:
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] {level}: {message}")

    def _log_test_result(self, result: TestResult):
        """Log test result"""
        self._log(
            f"{result.status.value} {result.test_name} ({result.duration:.3f}s)")
        if result.message:
            self._log(f"  Message: {result.message}")
        if result.error:
            self._log(f"  Error: {result.error}", level="ERROR")

    def print_summary(self):
        """Print test results summary"""
        total_tests = len(self.test_results)
        passed = len(
            [r for r in self.test_results if r.status == TestStatus.PASS])
        failed = len(
            [r for r in self.test_results if r.status == TestStatus.FAIL])
        errors = len(
            [r for r in self.test_results if r.status == TestStatus.ERROR])

        print(f"\n📊 Test Results Summary")
        print(f"=" * 50)
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"💥 Errors: {errors}")
        print(f"Success Rate: {(passed/total_tests)*100:.1f}%")

        if self.config.verbose:
            print(f"\n📋 Detailed Results:")
            print(f"-" * 50)
            for result in self.test_results:
                print(f"{result.status.value} {result.test_name}")
                print(f"   Duration: {result.duration:.3f}s")
                print(f"   Message: {result.message}")
                if result.data:
                    print(f"   Data: {json.dumps(result.data, indent=2)}")
                print()

    @abstractmethod
    async def run_tests(self):
        """Run all tests - implement in subclasses"""
        pass

    async def execute(self):
        """Execute the test suite"""
        try:
            await self.setup()
            await self.run_tests()
        finally:
            await self.teardown()
        self.print_summary()
