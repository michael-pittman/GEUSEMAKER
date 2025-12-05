# AMI Selection and Validation Review

**Date**: 2025-12-02
**Scope**: EC2Service AMI validation against AWS best practices

## Executive Summary

Analysis of GeuseMaker's AMI selection implementation against AWS official documentation and best practices. The current implementation is functional but has opportunities for improvement in error handling, validation thoroughness, and alignment with AWS-recommended patterns.

## Current Implementation

### Location
- **File**: `geusemaker/services/ec2.py`
- **Methods**: `validate_ami()`, `get_latest_dlami()`
- **Lines**: 43-121

### Current Flow

```python
# 1. Direct AMI lookup (AL2023 base images only)
if os_type == "amazon-linux-2023" and ami_type == "base":
    ami_id = AL2023_BASE_AMIS[region][architecture]
    if validate_ami(ami_id):
        return ami_id

# 2. Pattern-based fallback
images = describe_images(
    Owners=["amazon"],
    Filters=[
        {"Name": "name", "Values": [pattern]},
        {"Name": "state", "Values": ["available"]},
        {"Name": "architecture", "Values": [architecture]},
    ]
)
```

### Current Validation Method

```python
def validate_ami(self, ami_id: str) -> bool:
    try:
        images = self._ec2.describe_images(
            ImageIds=[ami_id],
            Filters=[{"Name": "state", "Values": ["available"]}],
        ).get("Images", [])
        return len(images) > 0
    except Exception:
        return False
```

## AWS Best Practices Analysis

### 1. AMI Validation ✅ GOOD

**Current approach**: Using `describe_images` with `state=available` filter

**AWS Documentation**:
> "The state filter with value 'available' ensures the AMI is ready for use"
>
> Source: https://docs.aws.amazon.com/cli/v1/reference/ec2/describe-images.html

**Status**: ✅ **Aligned with AWS best practices**

### 2. Eventual Consistency ⚠️ CONSIDERATION

**AWS Warning**:
> "The Amazon EC2 API follows an eventual consistency model. Recently deregistered images appear in the returned results for a short interval."
>
> Source: AWS EC2 API Documentation

**Current handling**: None - we assume immediate consistency

**Recommendation**:
- For production deployments, consider adding retry logic with exponential backoff
- Document that newly registered AMIs may take time to appear
- Current implementation is acceptable for Deep Learning AMIs (stable, long-lived)

**Impact**: Low (DL AMIs are stable and rarely change)

### 3. Exception Handling ⚠️ NEEDS IMPROVEMENT

**Current approach**: Catching bare `Exception`

```python
except Exception:
    return False
```

**Issue**: Violates GeuseMaker coding standards

**CLAUDE.md Rule #3**:
> "NEVER catch bare Exception - Catch specific exceptions (ClientError, ValidationError)"

**AWS Error Types**:
- `InvalidAMIID.NotFound` - AMI doesn't exist
- `InvalidAMIID.Malformed` - Invalid AMI ID format
- `InvalidAMIID.Unavailable` - AMI exists but not available
- `UnauthorizedOperation` - No permission to describe AMI

**Recommendation**:
```python
from botocore.exceptions import ClientError

def validate_ami(self, ami_id: str) -> bool:
    def _call() -> bool:
        try:
            images = self._ec2.describe_images(
                ImageIds=[ami_id],
                Filters=[{"Name": "state", "Values": ["available"]}],
            ).get("Images", [])
            return len(images) > 0
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("InvalidAMIID.NotFound", "InvalidAMIID.Malformed"):
                return False
            # Re-raise for unexpected errors (permissions, API issues)
            raise

    return self._safe_call(_call)
```

### 4. Advanced Validation Option 💡 ENHANCEMENT

**AWS Best Practice**:
> "Test your launch template with the run-instances command using the --dry-run option"
>
> Source: https://docs.aws.amazon.com/autoscaling/ec2/userguide/ts-as-launch-template.html

**Benefits of `run-instances --dry-run`**:
- Validates AMI can actually launch instances (not just exists)
- Checks IAM permissions
- Verifies AMI is compatible with instance type
- Validates all launch parameters together

**Example**:
```python
def validate_ami_for_launch(self, ami_id: str, instance_type: str) -> bool:
    """Validate AMI can be used to launch the specified instance type."""
    try:
        self._ec2.run_instances(
            ImageId=ami_id,
            InstanceType=instance_type,
            MinCount=1,
            MaxCount=1,
            DryRun=True  # Don't actually launch
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "DryRunOperation":
            return True  # Validation passed
        return False  # Validation failed
```

**Use Case**: When reusing VPC/subnet/SG where AMI compatibility matters

**Implementation Priority**: Optional enhancement (current validation is sufficient)

### 5. Owner Verification ⚠️ CONSIDERATION

**Current approach**:
- Direct lookup: Hardcoded AMI IDs (implicitly trusted)
- Pattern search: `Owners=["amazon"]` filter ✅

**Recommendation**: Add owner verification to `validate_ami()` for defense-in-depth:

```python
images = self._ec2.describe_images(
    ImageIds=[ami_id],
    Owners=["amazon"],  # Only accept official AWS AMIs
    Filters=[{"Name": "state", "Values": ["available"]}],
).get("Images", [])
```

**Security benefit**: Prevents accidental use of community AMIs if AMI ID mappings are compromised

**Impact**: Low (hardcoded AMI IDs are already trusted)

### 6. Pagination ⚠️ NOT NEEDED

**AWS Warning**:
> "We strongly recommend using only paginated requests. Unpaginated requests are susceptible to throttling and timeouts."

**Current approach**: No pagination on `describe_images`

**Analysis**:
- ✅ Direct lookup: Single AMI by ID (no pagination needed)
- ✅ Pattern search: Sorted by creation date, takes most recent (pagination not needed)
- ✅ Our queries are highly specific (name pattern + state + architecture)

**Status**: Current approach is acceptable (targeted queries, not listing all AMIs)

## Comparison with Run-Instances Implementation

**Current run_instances call** (tier1.py:127-177):
```python
ec2_resp = self.ec2_service.run_instance(
    ami_id=ami_id,
    instance_type=config.instance_type,
    # ... other params
    TagSpecifications=[
        {"ResourceType": "instance", "Tags": [...]},
        {"ResourceType": "network-interface", "Tags": [...]},
    ],
)
```

**Validation alignment**: ✅ AMI ID passed to run_instances is already validated

## Recommendations

### Priority 1: Fix Exception Handling (Code Standards Violation)

**Change**: Replace bare `except Exception` with specific `ClientError` handling

**Rationale**:
- Violates CLAUDE.md coding standards
- Masks real errors (permissions, API failures)
- Makes debugging harder

**Files**: `geusemaker/services/ec2.py:61`

### Priority 2: Add Owner Verification (Defense in Depth)

**Change**: Add `Owners=["amazon"]` filter to `validate_ami()`

**Rationale**:
- Extra security layer
- Aligns with pattern search behavior
- Minimal performance impact

### Priority 3: Document Eventual Consistency (Documentation)

**Change**: Add note to docstring about eventual consistency

**Rationale**:
- User awareness for edge cases
- No code change needed
- Follows AWS documentation guidance

### Optional: Advanced Validation Method

**Change**: Add `validate_ami_for_launch()` method using `run-instances --dry-run`

**Rationale**:
- AWS-recommended best practice
- Useful for interactive deployment mode
- More comprehensive validation

**When to use**:
- Interactive deployment wizard
- When reusing existing VPC/subnet/SG
- User-provided AMI IDs (future feature)

## Testing Implications

**Current tests** (test_ec2.py:116-272):
- ✅ Test direct lookup with valid AMI
- ✅ Test validation returns True for available AMI
- ✅ Test validation returns False for nonexistent AMI
- ✅ Test validation returns False for invalid AMI ID
- ✅ Test fallback when mapped AMI unavailable

**Required test updates for Priority 1**:
- Update test to expect specific error handling (not bare except)
- Add test for ClientError with UnauthorizedOperation
- Add test for ClientError with unexpected error code

## Conclusion

### Current Implementation Status: **FUNCTIONAL** ✅

The current AMI selection implementation works correctly and follows the core AWS best practices:
- ✅ Uses `describe_images` with `state=available` filter
- ✅ Validates AMI exists before use
- ✅ Two-tier strategy (direct + fallback) for performance
- ✅ Proper owner filtering in pattern search

### Recommended Improvements:

1. **Fix exception handling** to align with coding standards (Priority 1)
2. **Add owner verification** to validation for security (Priority 2)
3. **Document eventual consistency** in docstrings (Priority 3)
4. **Consider dry-run validation** for advanced use cases (Optional)

### No Breaking Changes Required

All improvements are backward-compatible enhancements that strengthen the existing implementation.

## References

1. AWS EC2 describe-images API: https://docs.aws.amazon.com/cli/v1/reference/ec2/describe-images.html
2. AWS Launch Template Troubleshooting: https://docs.aws.amazon.com/autoscaling/ec2/userguide/ts-as-launch-template.html
3. GeuseMaker Coding Standards: docs/architecture/12-coding-standards.md
4. CLAUDE.md Critical Coding Rules (Rule #3)
