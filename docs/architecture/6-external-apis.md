# 6. External APIs

## 6.1 AWS APIs (via Boto3)

GeuseMaker interacts with AWS services through Boto3 SDK calls. All API interactions include retry logic with exponential backoff.

### 6.1.1 EC2 API

| Operation | Boto3 Method | Purpose | Rate Limit |
|-----------|--------------|---------|------------|
| **Launch Instance** | `run_instances()` | Create EC2 spot/on-demand | 5 req/sec |
| **Describe Instances** | `describe_instances()` | Get instance status | 100 req/sec |
| **Terminate Instance** | `terminate_instances()` | Destroy instance | 5 req/sec |
| **Request Spot** | `request_spot_instances()` | Request spot capacity | 5 req/sec |
| **Describe Spot Price** | `describe_spot_price_history()` | Get current spot prices | 100 req/sec |
| **Get Console Output** | `get_console_output()` | Retrieve boot logs | 100 req/sec |

```python