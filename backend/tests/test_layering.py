"""Import-boundary enforcement — biet-backend skill section 1.

`biet_engine` must perform no I/O of any kind (CLAUDE.md non-negotiable 1).
That is only actually true if nothing in it imports a library capable of I/O,
so this is checked by inspecting the AST of every module rather than trusted
by convention. A violation here means the module is no longer pure, whatever
its code otherwise looks like.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ENGINE_SRC = Path(__file__).resolve().parents[1] / "src" / "biet_engine"

# Root package names biet_engine must never import, directly or transitively
# through its own imports. Each represents a way to perform I/O or reach
# outside the engine: web framework, ORM/DB driver, HTTP clients, the API
# package itself (which would make the dependency arrow point the wrong way),
# and any config/settings loader.
_FORBIDDEN_ROOTS = frozenset({
    "fastapi", "sqlalchemy", "psycopg", "httpx", "requests",
    "biet_api", "pydantic_settings",
})


def _engine_modules() -> list[Path]:
    return sorted(_ENGINE_SRC.rglob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", _engine_modules(), ids=lambda p: p.name)
def test_biet_engine_module_has_no_forbidden_import(path: Path) -> None:
    violations = _imported_roots(path) & _FORBIDDEN_ROOTS
    assert not violations, f"{path.relative_to(_ENGINE_SRC)} imports {violations}"


def test_biet_engine_package_exists_and_is_not_empty() -> None:
    # Guards against the parametrized test above silently collecting zero
    # cases if biet_engine ever moves or is renamed.
    assert _engine_modules(), f"no modules found under {_ENGINE_SRC}"
