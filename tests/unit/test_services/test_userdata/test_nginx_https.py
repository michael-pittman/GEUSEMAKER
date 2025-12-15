"""Tests for NGINX HTTPS configuration in UserData templates."""

from geusemaker.models.userdata import UserDataConfig
from geusemaker.services.userdata import UserDataGenerator

# ruff: noqa: S106 - Test fixtures use hardcoded passwords for testing only


def test_userdata_includes_nginx_ssl_setup_when_https_enabled() -> None:
    """Test that UserData includes NGINX SSL setup when HTTPS is enabled for Tier 1."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
        public_ip="203.0.113.42",
    )

    script = generator.generate(config)

    # Verify HTTPS setup is included (check actual code, not comments which are trimmed)
    assert "Setting up HTTPS with self-signed certificate" in script
    assert "openssl req -x509" in script
    assert "/etc/nginx/ssl/selfsigned.key" in script
    assert "/etc/nginx/ssl/selfsigned.crt" in script
    assert "CN=$PUBLIC_IP" in script  # Certificate CN uses PUBLIC_IP variable


def test_userdata_skips_nginx_ssl_when_https_disabled() -> None:
    """Test that UserData skips NGINX SSL setup when HTTPS is disabled."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=False,
    )

    script = generator.generate(config)

    # Verify HTTPS setup is NOT included
    assert "Setting up HTTPS with self-signed certificate" not in script
    assert "openssl req -x509" not in script
    assert "selfsigned.crt" not in script


def test_userdata_nginx_config_deployment() -> None:
    """Test that NGINX configuration is deployed in UserData."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
    )

    script = generator.generate(config)

    # Verify NGINX config deployment happens early (before Docker services)
    assert "/etc/nginx/conf.d/default.conf" in script
    assert "cat > /etc/nginx/conf.d/default.conf" in script

    # Verify explanation that nginx will be started later
    assert "NGINX will be installed and started after Docker services are running" in script


def test_userdata_openssl_installation() -> None:
    """Test that openssl is installed for certificate generation."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
    )

    script = generator.generate(config)

    # Verify openssl installation logic
    assert "pkg_install openssl" in script or "yum install -y openssl" in script


def test_userdata_certificate_permissions() -> None:
    """Test that certificate files have correct permissions."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
    )

    script = generator.generate(config)

    # Verify secure permissions are set
    assert "chmod 600 /etc/nginx/ssl/selfsigned.key" in script
    assert "chmod 644 /etc/nginx/ssl/selfsigned.crt" in script
    assert "chmod 700 /etc/nginx/ssl" in script


def test_userdata_certificate_verification() -> None:
    """Test that UserData verifies certificate creation."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
    )

    script = generator.generate(config)

    # Verify certificate existence check (single compound condition)
    assert "if [ ! -f /etc/nginx/ssl/selfsigned.crt ] || [ ! -f /etc/nginx/ssl/selfsigned.key ]" in script
    assert "SSL certificate files not found after generation" in script


def test_userdata_nginx_installation() -> None:
    """Test that NGINX is installed AFTER Docker services when HTTPS is enabled."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
    )

    script = generator.generate(config)

    # Verify NGINX installation happens
    assert "Installing NGINX web server" in script
    assert "pkg_install nginx" in script or "yum install -y nginx" in script

    # Verify installation verification
    assert "command -v nginx" in script
    assert "NGINX installation failed" in script

    # Verify nginx installation happens AFTER Docker services start
    nginx_install_pos = script.find("Installing NGINX web server")
    docker_services_pos = script.find("Starting Docker Compose services")
    assert nginx_install_pos > docker_services_pos, "NGINX must be installed after Docker services start"


def test_userdata_nginx_config_validation() -> None:
    """Test that NGINX configuration is validated with nginx -t."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
    )

    script = generator.generate(config)

    # Verify NGINX config validation
    assert "Validating NGINX configuration" in script
    assert "nginx -t" in script
    assert "NGINX configuration validation failed" in script


def test_userdata_nginx_service_startup() -> None:
    """Test that NGINX service is enabled and started."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
    )

    script = generator.generate(config)

    # Verify NGINX service management
    assert "Starting NGINX service" in script
    assert "systemctl enable nginx" in script
    assert "systemctl start nginx" in script

    # Verify service status check
    assert "systemctl is-active" in script
    assert "NGINX failed to start" in script

    # Verify final success message
    assert "NGINX configured and running with HTTPS on port 443" in script


def test_userdata_nginx_skipped_when_https_disabled() -> None:
    """Test that NGINX installation is skipped when HTTPS is disabled."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=False,
    )

    script = generator.generate(config)

    # Verify NGINX setup is completely skipped
    assert "Installing NGINX web server" not in script
    assert "pkg_install nginx" not in script
    assert "nginx -t" not in script
    assert "systemctl enable nginx" not in script
    assert "NGINX_GUARD" not in script


def test_userdata_nginx_guard_file() -> None:
    """Test that NGINX setup uses idempotency guard file."""
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
    )

    script = generator.generate(config)

    # Verify guard file pattern for idempotency
    assert 'NGINX_GUARD="/var/lib/geusemaker/nginx-configured"' in script
    assert 'if [ -f "$NGINX_GUARD" ]' in script
    assert 'touch "$NGINX_GUARD"' in script


def test_nginx_config_uses_localhost_not_container_names() -> None:
    """NGINX config must use localhost for proxying, not Docker container names.

    NGINX runs on the host system (not in Docker), so it cannot resolve
    Docker container names. It must use localhost since containers expose
    their ports to the host (0.0.0.0:5678, etc.).
    """
    generator = UserDataGenerator()

    config = UserDataConfig(
        efs_id="fs-12345",
        efs_dns="fs-12345.efs.us-east-1.amazonaws.com",
        stack_name="test-stack",
        region="us-east-1",
        tier="dev",
        postgres_password="test-password",
        enable_https=True,
        public_ip="203.0.113.42",
    )

    script = generator.generate(config)

    # NGINX config should use localhost for all services
    assert "proxy_pass http://localhost:5678" in script, "n8n should proxy to localhost:5678"
    assert "proxy_pass http://localhost:11434" in script, "ollama should proxy to localhost:11434"
    assert "proxy_pass http://localhost:6333" in script, "qdrant should proxy to localhost:6333"
    assert "proxy_pass http://localhost:6333" in script, "qdrant-ui should proxy to localhost:6333 (Qdrant dashboard)"
    assert "/dashboard/" in script, "qdrant-ui should rewrite to /dashboard/"
    assert "location = /qdrant-ui" in script or "location=/qdrant-ui" in script, "qdrant-ui should redirect /qdrant-ui to /qdrant-ui/"
    assert "proxy_pass http://localhost:11235" in script, "crawl4ai should proxy to localhost:11235"

    # Should NOT use container names (these don't resolve on host system)
    assert "proxy_pass http://n8n:" not in script, "Should not use n8n container name"
    assert "proxy_pass http://ollama:" not in script, "Should not use ollama container name"
    assert "proxy_pass http://qdrant:" not in script, "Should not use qdrant container name"
    assert "proxy_pass http://crawl4ai:" not in script, "Should not use crawl4ai container name"
