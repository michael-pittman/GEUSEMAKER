"""Tests for UserData script generation."""

from __future__ import annotations

import pytest

from geusemaker.models.userdata import UserDataConfig
from geusemaker.services.userdata import UserDataGenerator

# ruff: noqa: S106 - Test fixtures use hardcoded passwords for testing only


@pytest.fixture
def base_config() -> UserDataConfig:
    """Create a base UserDataConfig for testing."""
    return UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier="dev",
        stack_name="test-stack",
        region="us-east-1",
        postgres_password="test-password-123",
    )


def test_generator_creates_valid_script(base_config: UserDataConfig) -> None:
    """Test that generator creates a valid bash script."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert script.startswith("#!/bin/bash")
    assert "set -euo pipefail" in script
    assert len(script) > 0


def test_script_includes_shebang_and_error_handling(base_config: UserDataConfig) -> None:
    """Test script includes shebang and set -e for error handling."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert script.startswith("#!/bin/bash")
    assert "set -euo pipefail" in script
    assert "handle_error" in script
    assert "trap 'handle_error $LINENO' ERR" in script


def test_docker_installation_commands_present(base_config: UserDataConfig) -> None:
    """Test Docker installation commands are present."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Check for Docker official repository setup (Debian/Ubuntu)
    assert "download.docker.com" in script
    assert "docker-ce" in script or "amazon-linux-extras install docker" in script
    assert "docker compose" in script or "docker-compose" in script
    assert "systemctl start docker" in script
    assert "systemctl enable docker" in script
    assert "usermod -aG docker" in script


def test_efs_mount_command_with_correct_id(base_config: UserDataConfig) -> None:
    """Test EFS mount command uses correct EFS ID with IAM authentication."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Verify EFS mount with IAM authentication
    assert 'MOUNT_OPTS="tls,iam,addr=${EFS_MOUNT_ADDR}"' in script
    assert "mount -t efs -o" in script
    assert "fs-12345678:/ /mnt/efs" in script
    assert "amazon-efs-utils" in script
    assert "mkdir -p /mnt/efs" in script
    assert "/etc/fstab" in script


def test_docker_compose_file_generated(base_config: UserDataConfig) -> None:
    """Test Docker Compose file is generated."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert "docker-compose.yml" in script
    assert 'version: "3.8"' in script
    assert "services:" in script


def test_all_services_included_in_compose(base_config: UserDataConfig) -> None:
    """Test all required services are in Docker Compose."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Check all services are present
    assert "n8n:" in script
    assert "image: n8nio/n8n:latest" in script

    assert "ollama:" in script
    assert "image: ollama/ollama:latest" in script

    assert "qdrant:" in script
    assert "image: qdrant/qdrant:latest" in script

    assert "crawl4ai:" in script
    assert "image: unclecode/crawl4ai:latest" in script

    assert "postgres:" in script
    assert "image: postgres:15" in script


def test_environment_variables_set(base_config: UserDataConfig) -> None:
    """Test environment variables are configured."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Check n8n environment
    assert "N8N_HOST=0.0.0.0" in script
    assert "N8N_PORT=5678" in script

    # Check PostgreSQL environment
    assert "POSTGRES_PASSWORD=test-password-123" in script
    assert "POSTGRES_USER=geusemaker" in script
    assert "POSTGRES_DB=geusemaker" in script


def test_tier_dev_configuration(base_config: UserDataConfig) -> None:
    """Test tier 1 (dev) specific configuration."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Dev tier should NOT have NVIDIA runtime
    assert "DOCKER_RUNTIME=nvidia" not in script
    assert "N8N_METRICS=true" not in script


def test_tier_automation_configuration() -> None:
    """Test tier 2 (automation) ALB health check configuration."""
    config = UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier="automation",
        stack_name="test-stack",
        region="us-east-1",
        postgres_password="test-password-123",
    )
    gen = UserDataGenerator()
    script = gen.generate(config)

    # Automation tier should have metrics enabled
    assert "N8N_METRICS=true" in script


def test_tier_gpu_nvidia_runtime() -> None:
    """Test tier 3 (GPU) configures NVIDIA runtime."""
    config = UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier="gpu",
        stack_name="test-stack",
        region="us-east-1",
        postgres_password="test-password-123",
    )
    gen = UserDataGenerator()
    script = gen.generate(config)

    # GPU tier should configure NVIDIA runtime
    assert "nvidia-container-toolkit" in script
    assert "DOCKER_RUNTIME=nvidia" in script
    assert "NVIDIA_VISIBLE_DEVICES=all" in script


def test_idempotency_checks_included(base_config: UserDataConfig) -> None:
    """Test idempotency guard files are used."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Check for guard files
    assert "GUARD_FILE" in script
    assert "userdata-complete" in script
    assert "docker-installed" in script
    assert "efs-mounted" in script
    assert "services-started" in script

    # Check for idempotency checks
    assert 'if [ -f "$GUARD_FILE' in script or 'if [ -f "$GUARD_FILE' in script


def test_logging_configuration(base_config: UserDataConfig) -> None:
    """Test logging is configured properly."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert "/var/log/geusemaker-userdata.log" in script
    assert "exec 1> >(tee -a" in script
    assert "exec 2>&1" in script


def test_stack_name_in_script(base_config: UserDataConfig) -> None:
    """Test stack name is included in script."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert "test-stack" in script
    assert "Stack:" in script


def test_custom_environment_variables() -> None:
    """Test custom environment variables are injected."""
    config = UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier="dev",
        stack_name="test-stack",
        region="us-east-1",
        postgres_password="test-password-123",
        custom_env={
            "N8N_BASIC_AUTH_ACTIVE": "true",
            "N8N_BASIC_AUTH_USER": "admin",
            "CUSTOM_VAR": "value",
        },
    )
    gen = UserDataGenerator()
    script = gen.generate(config)

    # N8N_ prefixed vars should be included
    assert "N8N_BASIC_AUTH_ACTIVE=true" in script
    assert "N8N_BASIC_AUTH_USER=admin" in script
    # Non N8N vars should also be written to runtime env file
    assert "CUSTOM_VAR=value" in script


def test_custom_ports() -> None:
    """Test custom port configuration."""
    config = UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier="dev",
        stack_name="test-stack",
        region="us-east-1",
        n8n_port=8080,
        ollama_port=8081,
        qdrant_port=8082,
        crawl4ai_port=8083,
        postgres_password="test-password-123",
    )
    gen = UserDataGenerator()
    script = gen.generate(config)

    assert "N8N_PORT=8080" in script  # n8n port mapping set via env
    assert "OLLAMA_PORT=8081" in script  # ollama port mapping
    assert "QDRANT_PORT=8082" in script  # qdrant port mapping
    assert "CRAWL4AI_PORT=8083" in script  # crawl4ai port mapping


def test_health_checks_included(base_config: UserDataConfig) -> None:
    """Test health check commands are included."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert "healthcheck:" in script
    assert "check_service" in script or "health" in script.lower()


def test_efs_data_directories_created(base_config: UserDataConfig) -> None:
    """Test EFS data directories are created."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert "mkdir -p /mnt/efs/n8n" in script
    assert "mkdir -p /mnt/efs/ollama" in script
    assert "mkdir -p /mnt/efs/qdrant" in script
    assert "mkdir -p /mnt/efs/postgres" in script
    # Docker stays on local EBS - NOT on EFS
    assert "mkdir -p /mnt/efs/docker" not in script


def test_volume_mounts_configured(base_config: UserDataConfig) -> None:
    """Test Docker volume mounts are configured to EFS."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert "/mnt/efs/n8n:/home/node/.n8n" in script
    assert "/mnt/efs/ollama:/root/.ollama" in script
    assert "/mnt/efs/qdrant:/qdrant/storage" in script
    assert "/mnt/efs/postgres:/var/lib/postgresql/data" in script


def test_docker_compose_up_command(base_config: UserDataConfig) -> None:
    """Test docker-compose up command is present."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert "run_compose up -d" in script


def test_efs_runs_before_docker(base_config: UserDataConfig) -> None:
    """EFS setup should run before Docker installation."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    efs_index = script.find("EFS Mount Configuration")
    docker_index = script.find("Docker Installation")
    assert efs_index != -1 and docker_index != -1
    assert efs_index < docker_index


def test_docker_data_root_stays_on_local_ebs(base_config: UserDataConfig) -> None:
    """Docker data should stay on local EBS, NOT on EFS.

    EFS doesn't support all filesystem features needed by Docker's overlay2 driver.
    Application data uses EFS via bind mounts defined in docker-compose.yml.
    """
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Verify Docker stays on local EBS (no EFS symlink)
    # Note: Comment-only lines are stripped by _trim_script() to reduce UserData size
    assert "/mnt/efs/docker" not in script

    # Verify application data uses EFS bind mounts
    assert "/mnt/efs/n8n:/home/node/.n8n" in script
    assert "/mnt/efs/ollama:/root/.ollama" in script


def test_services_pre_pull_images(base_config: UserDataConfig) -> None:
    """Services template should pre-pull images before startup."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    assert "run_compose pull" in script


def test_runtime_bundle_block_included_when_enabled(base_config: UserDataConfig) -> None:
    """Runtime bundle base64 payload should be embedded when requested."""
    config = base_config.model_copy(update={"use_runtime_bundle": True})
    gen = UserDataGenerator()
    script = gen.generate(config)

    assert "runtime-bundle.tar.gz" in script
    assert 'base64 -d > "$RUNTIME_BUNDLE_FILE"' in script
    assert 'tar -xzf "$RUNTIME_BUNDLE_FILE"' in script


def test_container_startup_retry_logic(base_config: UserDataConfig) -> None:
    """Test container startup includes retry logic instead of fixed sleep."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Verify retry functions are defined
    assert "wait_for_containers_running()" in script
    assert "verify_docker_network()" in script

    # Verify retry logic checks all expected containers
    assert '"n8n" "ollama" "qdrant" "crawl4ai" "postgres"' in script

    # Verify exponential backoff is implemented
    assert "max_attempts=" in script
    assert "delay=" in script

    # Verify Docker network hostname resolution checks
    assert "getent hosts postgres" in script
    assert "getent hosts ollama" in script

    # Verify old fixed sleep is removed
    assert "sleep 10" not in script or script.count("sleep") > 1  # If sleep 10 exists, should have other sleeps too

    # Verify error handling on failure
    assert "Container startup failed" in script
    assert "network verification failed" in script


def test_docker_network_diagnostics_on_failure(base_config: UserDataConfig) -> None:
    """Test Docker network diagnostics are collected on failure."""
    gen = UserDataGenerator()
    script = gen.generate(base_config)

    # Verify network diagnostics commands
    assert "docker network ls" in script
    assert "docker network inspect" in script

    # Verify error messages are informative
    assert "Docker network hostname resolution failed" in script
    assert "DNS resolution not ready" in script
