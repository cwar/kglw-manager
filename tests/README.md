# KGLW Manager Test Suite

This directory contains a comprehensive pytest-based test suite for the KGLW Manager project.

## Test Structure

```
tests/
├── conftest.py                 # Shared fixtures and test configuration
├── unit/                       # Unit tests for individual components
│   ├── test_kglw_api.py       # KGLW.net API integration tests
│   ├── test_collection_upgrade_logic.py  # Collection upgrade logic tests
│   └── test_naming.py         # Naming and filename generation tests
├── integration/                # Integration tests
│   └── test_collection_management.py  # Full workflow integration tests
├── fixtures/                   # Test data and fixtures
└── test_runner.py             # Convenient test runner script
```

## Running Tests

### Basic Usage

```bash
# Run all tests
uv run python -m pytest

# Run only unit tests
uv run python -m pytest -m unit

# Run only integration tests  
uv run python -m pytest -m integration

# Run with coverage report
uv run python -m pytest --cov=kglw_manager --cov-report=html

# Run specific test file
uv run python -m pytest tests/unit/test_kglw_api.py
```

### Using the Test Runner

```bash
# Run unit tests only
python tests/test_runner.py --unit

# Run integration tests only
python tests/test_runner.py --integration

# Run with coverage reporting
python tests/test_runner.py --coverage

# Run tests that require network access
python tests/test_runner.py --api

# Run in verbose mode
python tests/test_runner.py --verbose
```

## Test Categories

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Tests that involve multiple components
- `@pytest.mark.api` - Tests that require network/API access
- `@pytest.mark.slow` - Slow-running tests (can be skipped)
- `@pytest.mark.requires_collection` - Tests that need real collection data
- `@pytest.mark.requires_network` - Tests that need internet connectivity

## Fixtures

Key fixtures available in `conftest.py`:

- `temp_collection_dir` - Temporary directory for test collections
- `sample_show_info` - Sample show information for testing
- `sample_video_candidates` - Sample video candidates for upgrade testing
- `mock_kglw_api` - Mocked KGLW API for testing without network calls
- `collection_manager_with_temp_dir` - Collection manager with temporary directory

## Coverage

Generate coverage reports:

```bash
# HTML coverage report (recommended)
uv run python -m pytest --cov=kglw_manager --cov-report=html
# Open htmlcov/index.html in browser

# Terminal coverage report
uv run python -m pytest --cov=kglw_manager --cov-report=term

# Coverage with missing lines
uv run python -m pytest --cov=kglw_manager --cov-report=term-missing
```

## Adding New Tests

1. **Unit Tests**: Add to `tests/unit/test_[component].py`
2. **Integration Tests**: Add to `tests/integration/test_[workflow].py`
3. **Use Appropriate Markers**: Mark tests with `@pytest.mark.unit`, `@pytest.mark.integration`, etc.
4. **Mock External Dependencies**: Use fixtures from `conftest.py` or create new mocks
5. **Follow Naming Convention**: Test methods should start with `test_`

## Example Test

```python
import pytest
from kglw_manager.collection import CollectionManager

class TestCollectionBasics:
    
    @pytest.mark.unit
    def test_collection_initialization(self, temp_collection_dir):
        """Test that collection manager initializes correctly."""
        manager = CollectionManager(str(temp_collection_dir))
        assert manager.collection_path == temp_collection_dir
        assert manager.mode == "movie"
    
    @pytest.mark.integration 
    def test_scan_collection_workflow(self, sample_collection_with_shows):
        """Test the complete collection scanning workflow."""
        manager = CollectionManager(str(sample_collection_with_shows))
        result = manager.scan_collection()
        assert isinstance(result, dict)
        assert 'tours' in result
```

## CI Integration

The test suite is designed to work in CI environments:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    uv run python -m pytest \
      -m "not (api or requires_collection or requires_network)" \
      --cov=kglw_manager \
      --cov-report=xml
```

## Notes

- Tests avoid real network calls by default (use mocks)
- Tests avoid requiring the actual KGLW collection directory
- Temporary directories are automatically cleaned up
- Test isolation is maintained between test runs
- All tests should be deterministic and repeatable