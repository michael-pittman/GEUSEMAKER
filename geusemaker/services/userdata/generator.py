"""UserData script generation service."""

from __future__ import annotations

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
            docker_tmpl = self._env.get_template("docker.sh.j2")
            efs_tmpl = self._env.get_template("efs.sh.j2")
            services_tmpl = self._env.get_template("services.sh.j2")
            healthcheck_tmpl = self._env.get_template("healthcheck.sh.j2")

            # Convert config to dict for template rendering
            context = config.model_dump()

            # Render each section
            sections = [
                base_tmpl.render(context),
                efs_tmpl.render(context),
                docker_tmpl.render(context),
                services_tmpl.render(context),
                healthcheck_tmpl.render(context),
            ]

            # Combine sections into complete script
            combined = "\n".join(sections)
            return self._trim_script(combined)

        except Exception as e:
            raise RuntimeError(f"Failed to generate UserData script: {e}") from e

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
