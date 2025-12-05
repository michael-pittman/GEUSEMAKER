"""Container update helpers."""

from __future__ import annotations

from geusemaker.infra import AWSClientFactory
from geusemaker.models import DeploymentState
from geusemaker.services.ssm import SSMService


class ContainerUpdater:
    """Update container images on the deployment host."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        region: str = "us-east-1",
        ssm_service: SSMService | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.region = region
        self.ssm = ssm_service or SSMService(self.client_factory, region=region)

    def update_container_images(self, state: DeploymentState, images: dict[str, str]) -> list[str]:
        """Update docker-compose images on the host via SSM."""
        if not images:
            return []

        script = self._build_script(images)
        result = self.ssm.run_shell_script(
            state.instance_id,
            [script],
            comment=f"GeuseMaker update: {state.stack_name}",
            timeout_seconds=900,
        )
        status = result.get("Status")
        if status != "Success":
            detail = result.get("StatusDetails") or status
            raise RuntimeError(f"Container update failed via SSM: {detail}")

        state.container_images.update(images)
        return [f"{name} -> {ref}" for name, ref in images.items()]

    def _build_script(self, images: dict[str, str]) -> str:
        """Render a shell script to update compose images and restart services."""
        import json

        overrides = json.dumps(images)
        script_lines = [
            "set -euo pipefail",
            'COMPOSE_FILE="/opt/geusemaker/docker-compose.yml"',
            'WORKDIR="/opt/geusemaker"',
            'if [ ! -f "$COMPOSE_FILE" ]; then echo "compose file missing at $COMPOSE_FILE"; exit 1; fi',
            'ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }',
            "LOG_DIR=$(mktemp -d)",
            'cleanup() { rm -rf "$LOG_DIR"; }',
            "trap cleanup EXIT",
            f"export GM_IMAGE_OVERRIDES='{overrides}'",
            "mapfile -t IMAGES_TO_PULL < <(python - \"$COMPOSE_FILE\" <<'PY'",
            "import json, os, sys, subprocess, pathlib",
            "data_file = pathlib.Path(sys.argv[1])",
            "overrides = json.loads(os.environ['GM_IMAGE_OVERRIDES'])",
            "try:",
            "    import yaml",
            "except ImportError:",
            "    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', 'PyYAML'])",
            "    import yaml  # type: ignore",
            "with data_file.open() as fh:",
            "    compose = yaml.safe_load(fh) or {}",
            "services = compose.get('services', {}) or {}",
            "for name, image in overrides.items():",
            "    service = services.get(name)",
            "    if isinstance(service, dict):",
            "        service['image'] = image",
            "compose['services'] = services",
            "with data_file.open('w') as fh:",
            "    yaml.safe_dump(compose, fh, sort_keys=False)",
            "for image in dict.fromkeys(overrides.values()):",
            "    print(image)",
            "PY",
            ")",
            'cd "$WORKDIR"',
            'if [ ${#IMAGES_TO_PULL[@]} -eq 0 ]; then echo "$(ts) No images to pull"; exit 0; fi',
            "pids=()",
            "images=()",
            "logs=()",
            'for image in "${IMAGES_TO_PULL[@]}"; do',
            "  log_file=\"$LOG_DIR/$(echo \"$image\" | tr '/:' '__').log\"",
            '  echo "$(ts) [pull-start] $image (log: $log_file)"',
            '  (docker pull "$image" >"$log_file" 2>&1) &',
            "  pids+=($!)",
            '  images+=("$image")',
            '  logs+=("$log_file")',
            "done",
            "pull_failed=0",
            'for i in "${!pids[@]}"; do',
            "  pid=${pids[$i]}",
            "  image=${images[$i]}",
            "  log_file=${logs[$i]}",
            '  if wait "$pid"; then',
            '    echo "$(ts) [pull-success] $image"',
            '    rm -f "$log_file"',
            "  else",
            '    echo "$(ts) [pull-failed] $image (see $log_file)"',
            "    sed -e 's/^/    /' \"$log_file\" || true",
            "    pull_failed=1",
            "  fi",
            "done",
            'if [ "$pull_failed" -ne 0 ]; then',
            '  echo "$(ts) Docker pull failures detected"',
            "  exit 1",
            "fi",
            'echo "$(ts) Starting docker compose up -d"',
            "docker compose up -d || docker-compose up -d",
        ]
        return "\n".join(script_lines)


__all__ = ["ContainerUpdater"]
