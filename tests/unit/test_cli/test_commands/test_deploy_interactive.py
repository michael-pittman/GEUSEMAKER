from __future__ import annotations

from io import StringIO

from click.testing import CliRunner
from rich.console import Console

from geusemaker.cli.main import cli


def test_deploy_defaults_to_interactive_when_no_args(monkeypatch):
    called: dict[str, object] = {}

    class FakeInteractive:
        def __init__(self, *args, **kwargs):  # noqa: D401
            called["init"] = True

        def run(self, initial_state=None):  # type: ignore[no-untyped-def]
            called["state"] = initial_state
            return None

    fake_console = Console(file=StringIO(), force_terminal=True)
    monkeypatch.setattr("geusemaker.cli.commands.deploy.console", fake_console)
    monkeypatch.setattr("geusemaker.cli.commands.deploy.InteractiveDeployer", FakeInteractive)

    result = CliRunner().invoke(cli, ["deploy"])

    assert result.exit_code == 0
    assert called["init"] is True
    assert isinstance(called["state"], dict)
    assert called["state"].get("tier") == "dev"
