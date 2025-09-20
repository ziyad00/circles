# Circles API Testing Framework

A comprehensive testing framework for the Circles API with proper architecture, separation of concerns, and reusable components.

## Architecture

```
tests/
├── __init__.py
├── README.md
├── run_all_tests.py          # Main test runner
├── unit/                     # Unit tests for individual components
│   ├── __init__.py
│   └── test_jwt_service.py   # JWT service unit tests
├── integration/              # Integration tests for API endpoints
│   ├── __init__.py
│   ├── test_collections.py   # Collections API tests
│   ├── test_places.py        # Places API tests
│   └── test_dms.py           # Direct Messages API tests
├── e2e/                      # End-to-end workflow tests
│   ├── __init__.py
│   └── test_user_workflow.py # Complete user workflow tests
├── utils/                    # Testing utilities and helpers
│   ├── __init__.py
│   ├── base_test.py          # Base test class with common functionality
│   ├── http_client.py        # HTTP client utilities
│   └── test_helpers.py       # Test helpers, assertions, and fixtures
└── fixtures/                 # Test data fixtures
    └── (future test data files)
```

## Features

### 🏗️ **Proper Architecture**

- **Separation of Concerns**: Unit, Integration, and E2E tests are clearly separated
- **Base Classes**: Common functionality in `BaseTest` class
- **Reusable Components**: HTTP client, assertions, and test helpers
- **Configuration**: Centralized test configuration

### 🧪 **Test Types**

#### Unit Tests (`tests/unit/`)

- Test individual components in isolation
- Fast execution, no external dependencies
- Example: JWT service functionality

#### Integration Tests (`tests/integration/`)

- Test API endpoints with real database
- Test authentication and authorization
- Test data persistence and retrieval

#### End-to-End Tests (`tests/e2e/`)

- Test complete user workflows
- Test cross-component interactions
- Test real-world usage scenarios

### 🛠️ **Utilities**

#### BaseTest Class

- Common setup/teardown functionality
- Test user creation and JWT token generation
- Test result tracking and reporting
- Configurable test settings

#### HTTP Client

- Async HTTP client with proper error handling
- Response wrapper with helper methods
- Support for all HTTP methods (GET, POST, PUT, DELETE, PATCH)

#### Test Helpers

- Test data factory for creating test data
- Assertion helpers for common validations
- Test fixtures with sample data
- Cleanup utilities

## Usage

### Run All Tests

```bash
cd /Users/ziyad/Documents/GitHub/circles
source .venv/bin/activate
python tests/run_all_tests.py
```

### Run Individual Test Suites

```bash
# Collections API tests
python tests/integration/test_collections.py

# Places API tests
python tests/integration/test_places.py

# DMs API tests
python tests/integration/test_dms.py

# JWT Service unit tests
python tests/unit/test_jwt_service.py

# User workflow E2E tests
python tests/e2e/test_user_workflow.py
```

### Run Specific Test Categories

```bash
# Only unit tests
python -m pytest tests/unit/

# Only integration tests
python -m pytest tests/integration/

# Only E2E tests
python -m pytest tests/e2e/
```

## Test Configuration

The `TestConfig` class allows you to customize test behavior:

```python
from tests.utils.base_test import TestConfig

config = TestConfig(
    base_url="http://127.0.0.1:8000",
    test_user_phone="+1234567890",
    test_user_username="testuser",
    test_user_name="Test User",
    timeout=30,
    verbose=True
)
```

## Writing New Tests

### 1. Unit Tests

```python
from tests.utils.base_test import BaseTest

class MyComponentTest:
    def test_my_function(self):
        # Test individual function
        result = my_function(input)
        assert result == expected_output
```

### 2. Integration Tests

```python
from tests.utils.base_test import BaseTest
from tests.utils.http_client import TestHTTPClient, APIResponse

class MyAPITest(BaseTest):
    async def test_my_endpoint(self) -> Optional[Dict[str, Any]]:
        response = APIResponse(await self.client.get("/my-endpoint"))
        if response.is_success():
            return response.json
        return None

    async def run_tests(self):
        await self.run_test("My Endpoint", self.test_my_endpoint)
```

### 3. E2E Tests

```python
from tests.utils.base_test import BaseTest

class MyWorkflowTest(BaseTest):
    async def test_complete_workflow(self) -> Optional[Dict[str, Any]]:
        # Test complete user workflow
        # Step 1: Do something
        # Step 2: Do something else
        # Step 3: Verify results
        return workflow_results
```

## Test Data Management

### Creating Test Data

```python
from tests.utils.test_helpers import TestDataFactory

# Create test places
places = await TestDataFactory.create_test_places(5)

# Create test collection
collection = await TestDataFactory.create_test_collection(user_id, "My Collection")

# Add places to collection
await TestDataFactory.add_places_to_collection(collection.id, [place.id for place in places])
```

### Using Test Fixtures

```python
from tests.utils.test_helpers import TestFixtures

# Get sample place data
place_data = TestFixtures.get_sample_place_data(variation=1)

# Get sample collection data
collection_data = TestFixtures.get_sample_collection_data(variation=1)
```

### Cleanup

```python
from tests.utils.test_helpers import TestCleanup

# Clean up all test data
await TestCleanup.cleanup_test_data()
```

## Assertions

The framework provides helpful assertion methods:

```python
from tests.utils.test_helpers import TestAssertions

# Assert response is successful
TestAssertions.assert_response_success(response, 200)

# Assert response is an error
TestAssertions.assert_response_error(response, 404)

# Assert JSON contains key and value
TestAssertions.assert_json_contains(response, "user_id", 123)

# Assert JSON has expected structure
TestAssertions.assert_json_structure(response, ["id", "name", "created_at"])

# Assert pagination structure
TestAssertions.assert_pagination(response)
```

## Best Practices

1. **Use the Base Class**: Inherit from `BaseTest` for integration and E2E tests
2. **Async/Await**: Use async methods for database and HTTP operations
3. **Error Handling**: Always handle exceptions and return `None` on failure
4. **Test Isolation**: Each test should be independent and clean up after itself
5. **Descriptive Names**: Use clear, descriptive test names
6. **Assertions**: Use the provided assertion helpers for consistency
7. **Data Management**: Use the test data factory and fixtures
8. **Configuration**: Use the `TestConfig` class for customization

## Continuous Integration

The test framework is designed to work with CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Tests
  run: |
    source .venv/bin/activate
    python tests/run_all_tests.py
```

## Troubleshooting

### Common Issues

1. **Database Connection**: Ensure the database is running and accessible
2. **Authentication**: Check that JWT tokens are being generated correctly
3. **Test Data**: Verify test data is being created and cleaned up properly
4. **Async Issues**: Make sure all async operations are properly awaited

### Debug Mode

Enable verbose logging by setting `verbose=True` in `TestConfig`:

```python
config = TestConfig(verbose=True)
```

This will show detailed logs for each test execution, including timing and error details.
