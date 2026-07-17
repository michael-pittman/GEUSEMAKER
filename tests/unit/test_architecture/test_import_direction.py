"""Guard test: orchestration and services must not depend on the CLI layer.

Presentation (Rich/Click/Textual under ``geusemaker.cli``) renders progress and
log events. Orchestration and service code must only emit them. This test walks
every module under ``geusemaker/orchestration`` and ``geusemaker/services`` and
asserts none of them import ``geusemaker.cli`` (directly or via ``from``), nor
call ``console.print`` as a presentation backstop.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "geusemaker"
GUARDED_DIRS = ("orchestration", "services")
FORBIDDEN_ROOT = "geusemaker.cli"

# Matches the bare module-level ``console`` (the singleton exported from
# ``geusemaker.cli``) but NOT attribute usage like ``self.console.print(`` on a
# private Rich ``Console`` instance (e.g. services/monitoring/notifiers.py,
# which owns its own Rich console and is out of scope for this guard).
_CONSOLE_PRINT_RE = re.compile(r"(?<![.\w])console\.print\(")


def _guarded_files() -> list[Path]:
    files: list[Path] = []
    for subdir in GUARDED_DIRS:
        files.extend(sorted((PACKAGE_ROOT / subdir).rglob("*.py")))
    return files


def _imports_forbidden(tree: ast.AST) -> bool:
    """Return True if the module imports ``geusemaker.cli`` in any form."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == FORBIDDEN_ROOT or alias.name.startswith(FORBIDDEN_ROOT + "."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # node.level > 0 means a relative import; those can't reach geusemaker.cli.
            if node.level == 0 and (module == FORBIDDEN_ROOT or module.startswith(FORBIDDEN_ROOT + ".")):
                return True
    return False


def test_orchestration_and_services_do_not_import_cli() -> None:
    """No module under orchestration/ or services/ may import geusemaker.cli."""
    violations: list[str] = []
    for path in _guarded_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _imports_forbidden(tree):
            violations.append(str(path))

    assert not violations, (
        "The following orchestration/services modules import 'geusemaker.cli' "
        "(presentation must depend on orchestration/services, not vice versa):\n  " + "\n  ".join(violations)
    )


def test_orchestration_and_services_have_no_console_print() -> None:
    """Backstop: no bare 'console.print(' (the geusemaker.cli singleton) in guarded modules."""
    violations: list[str] = []
    for path in _guarded_files():
        if _CONSOLE_PRINT_RE.search(path.read_text(encoding="utf-8")):
            violations.append(str(path))

    assert not violations, (
        "The following orchestration/services modules use the CLI 'console.print(' "
        "singleton (emit progress events or use module logging instead):\n  " + "\n  ".join(violations)
    )
