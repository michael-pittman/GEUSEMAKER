"""UserData generation configuration models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UserDataConfig(BaseModel):
    """Configuration for EC2 UserData script generation."""

    efs_id: str = Field(..., description="EFS file system ID (e.g., fs-12345678)")
    efs_dns: str = Field(..., description="EFS DNS name (e.g., fs-12345678.efs.us-east-1.amazonaws.com)")
    tier: Literal["dev", "automation", "gpu"] = Field(..., description="Deployment tier affecting configuration")
    stack_name: str = Field(..., description="Stack name for resource tagging")
    region: str = Field(..., description="AWS region (e.g., us-east-1)")
    n8n_port: int = Field(default=5678, description="n8n web interface port")
    ollama_port: int = Field(default=11434, description="Ollama API port")
    qdrant_port: int = Field(default=6333, description="Qdrant API port")
    crawl4ai_port: int = Field(default=11235, description="Crawl4AI API port")
    postgres_password: str = Field(..., description="PostgreSQL database password")
    custom_env: dict[str, str] = Field(default_factory=dict, description="Custom environment variables")
    use_runtime_bundle: bool = Field(
        default=False,
        description="When true, embed the packaged runtime bundle to reduce on-instance downloads.",
    )
    runtime_bundle_b64: str | None = Field(
        default=None,
        description="Base64-encoded runtime bundle tarball (populated automatically when use_runtime_bundle is true).",
    )
    runtime_bundle_path: str | None = Field(
        default=None,
        description="Optional path to a prebuilt runtime bundle tar.gz to embed instead of packaged assets.",
    )
    runtime_bundle_filename: str = Field(
        default="runtime-bundle.tar.gz",
        description="Filename used when unpacking the runtime bundle on the instance.",
    )
