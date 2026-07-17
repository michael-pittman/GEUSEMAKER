from click.testing import CliRunner

from geusemaker.cli.commands import tui as tui_module
from geusemaker.cli.commands.tui import tui_command


def test_tui_missing_extra_has_actionable_hint(monkeypatch):
    monkeypatch.setattr(tui_module, "__import__", None, raising=False)
    # Exercise lazy launch deterministically by making the import fail.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "textual":
            raise ImportError
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = CliRunner().invoke(tui_command)
    assert result.exit_code == 1
    assert "geusemaker[tui]" in result.output
