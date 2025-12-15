"""UserData script generation service."""

from __future__ import annotations

import base64
import io
import tarfile
from importlib import resources
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from geusemaker.models.userdata import UserDataConfig


class UserDataGenerator:
    """Generates EC2 UserData bash scripts from templates."""

    def __init__(self) -> None:
        """Initialize the generator with Jinja2 environment."""
        template_dir = Path(__file__).parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,  # noqa: S701 - Generating bash scripts, not HTML
        )

    def generate(self, config: UserDataConfig) -> str:
        """
        Generate complete UserData bash script.

        Args:
            config: UserData configuration

        Returns:
            Complete bash script as string

        Raises:
            RuntimeError: If template rendering fails
        """
        try:
            # Load all templates
            base_tmpl = self._env.get_template("base.sh.j2")
            gpu_tmpl = self._env.get_template("gpu.sh.j2")
            docker_tmpl = self._env.get_template("docker.sh.j2")
            efs_tmpl = self._env.get_template("efs.sh.j2")
            services_tmpl = self._env.get_template("services.sh.j2")
            nginx_setup_tmpl = self._env.get_template("nginx-setup.sh.j2")
            healthcheck_tmpl = self._env.get_template("healthcheck.sh.j2")
            ollama_models_tmpl = self._env.get_template("ollama-models.sh.j2")

            # Convert config to dict for template rendering and backfill runtime bundle when requested
            context = config.model_dump()
            if context.get("use_runtime_bundle") and not context.get("runtime_bundle_b64"):
                context["runtime_bundle_b64"] = self._build_runtime_bundle_b64(
                    override_path=config.runtime_bundle_path,
                )

            # Render each section
            # GPU validation runs after base setup but before Docker (NVIDIA drivers must be present)
            # NGINX setup runs after Docker services (requires container hostnames for validation)
            # Model preloading runs after healthcheck in background (non-blocking)
            sections = [
                base_tmpl.render(context),
                gpu_tmpl.render(context),
                efs_tmpl.render(context),
                docker_tmpl.render(context),
                services_tmpl.render(context),
                nginx_setup_tmpl.render(context),
                healthcheck_tmpl.render(context),
                ollama_models_tmpl.render(context),
            ]

            # Combine sections into complete script
            combined = "\n".join(sections)
            return self._trim_script(combined)

        except Exception as e:
            raise RuntimeError(f"Failed to generate UserData script: {e}") from e

    def _build_runtime_bundle_b64(self, override_path: str | None = None) -> str:
        """Return base64-encoded runtime bundle bytes."""
        bundle_bytes = self._load_runtime_bundle_bytes(override_path)
        return base64.b64encode(bundle_bytes).decode()

    def _load_runtime_bundle_bytes(self, override_path: str | None = None) -> bytes:
        """Create a tar.gz of packaged runtime assets or load a provided bundle path."""
        if override_path:
            bundle_path = Path(override_path).expanduser()
            if not bundle_path.exists():
                raise RuntimeError(f"Runtime bundle override not found at {bundle_path}")
            return bundle_path.read_bytes()

        asset_root = resources.files("geusemaker.runtime_assets")
        if not asset_root.exists():
            raise RuntimeError("Runtime assets missing from package; rebuild or reinstall GeuseMaker.")

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for asset in asset_root.rglob("*"):
                name = asset.name
                if name in {"__pycache__", ".DS_Store"}:
                    continue
                rel_parts = asset.relative_to(asset_root).parts
                if "dist" in rel_parts:
                    continue
                tar.add(str(asset), arcname=str(asset.relative_to(asset_root)))

        return buffer.getvalue()

    @staticmethod
    def _trim_script(script: str) -> str:
        """Trim comment-only lines and collapse extra blank lines to reduce UserData size."""
        lines = script.splitlines()
        trimmed: list[str] = []
        for idx, line in enumerate(lines):
            if idx == 0 and line.startswith("#!"):
                trimmed.append(line)
                continue
            stripped = line.strip()
            if stripped == "" and (not trimmed or trimmed[-1] == ""):
                # Skip consecutive blank lines
                continue
            if stripped.startswith("#"):
                # Drop comment-only lines (keep inline comments untouched)
                continue
            trimmed.append(line)

        return "\n".join(trimmed).strip() + "\n"
