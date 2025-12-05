# 13. Test Strategy and Standards

## 13.1 Testing Philosophy

- **Approach:** Test-after development with emphasis on service/integration coverage
- **Coverage Goals:** 80% unit, 60% integration, critical paths 100%
- **Test Pyramid:** Unit (70%) → Integration (20%) → E2E (10%)

## 13.2 Test Types and Organization

### 13.2.1 Unit Tests

- **Framework:** pytest 8.0+
- **File Convention:** `tests/unit/test_<module>.py`
- **Location:** `tests/unit/`
- **Mocking Library:** `pytest-mock` + `moto` (AWS mocking)
- **Coverage Requirement:** 80% minimum

**AI Agent Requirements:**
- Generate tests for all public methods
- Cover edge cases and error conditions
- Follow AAA pattern (Arrange, Act, Assert)
- Mock all AWS API calls using `moto`

```python