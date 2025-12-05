# 11. Error Handling Strategy

## 11.1 General Approach

- **Error Model:** Custom exception hierarchy with AWS error translation
- **Exception Hierarchy:** `GeuseMakerError` → `AWSError`, `ValidationError`, `StateError`
- **Error Propagation:** Catch at service layer, translate to user-friendly errors, display with emojis

## 11.2 Exception Hierarchy

```python
"""geusemaker/errors.py - Exception hierarchy with emoji support."""

from geusemaker.cli.branding import EMOJI

class GeuseMakerError(Exception):
    """Base exception for all GeuseMaker errors."""
    emoji = EMOJI["error"]

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(f"{self.emoji} {message}")

class AWSError(GeuseMakerError):
    """AWS API call failures."""
    emoji = EMOJI["cloud"]

    def __init__(self, service: str, operation: str, error_code: str, message: str):
        self.service = service
        self.operation = operation
        self.error_code = error_code
        super().__init__(
            f"AWS {service}.{operation} failed: [{error_code}] {message}",
            details={"service": service, "operation": operation, "error_code": error_code}
        )

class ValidationError(GeuseMakerError):
    """Input validation failures."""
    emoji = EMOJI["warning"]

class StateError(GeuseMakerError):
    """State file corruption or inconsistency."""
    emoji = EMOJI["database"]

class DeploymentError(GeuseMakerError):
    """Deployment workflow failures."""
    emoji = EMOJI["rocket"]

class HealthCheckError(GeuseMakerError):
    """Service health check failures."""
    emoji = EMOJI["heart"]

class RollbackError(GeuseMakerError):
    """Rollback operation failures."""
    emoji = EMOJI["rollback"]

class SpotInterruptionError(GeuseMakerError):
    """Spot instance interruption."""
    emoji = EMOJI["lightning"]
```

## 11.3 Logging Standards

- **Library:** `structlog` 24.1.0 (structured JSON logging)
- **Format:** JSON in production, colored console in development
- **Levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL

```python
"""geusemaker/infra/logging.py - Structured logging setup."""

import structlog
from rich.logging import RichHandler

def setup_logging(debug: bool = False) -> None:
    """Configure structured logging with emoji prefixes."""

    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if debug:
        # Rich console output for development
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        # JSON for production
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
