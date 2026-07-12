"""
Auth scope lint check — ensures every API endpoint has require_scope.

Prevents "forgotten lock" regressions where new endpoints default to open.
Uses AST static analysis so no running server is needed.

Closes #5.
"""
import ast
import os
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "app" / "api"

# HTTP method decorators that define route handlers
ROUTE_DECORATORS = {"get", "post", "put", "delete", "patch"}

# Files/paths intentionally exempt from require_scope.
# Each entry is a relative path from backend/app/api/.
# Reason must be documented for each exemption.
EXEMPT_FILES = {
    # SSE streams — browser EventSource can't send Authorization headers
    "events.py",
    # Public API reference docs
    "docs.py",
    # Public, read-only catalog of repo-bundled agent skills (.claude/skills/*);
    # serves the same non-secret static content shown on the Agent Skills page
    "skills.py",
    # Agent query uses its own X-API-Key + agent-scoped auth
    "agents/query.py",
    # Router init files (no route handlers)
    "__init__.py",
    "agents/__init__.py",
    "sources/__init__.py",
    "projects/__init__.py",
    "auth/__init__.py",
}

# Files with known unprotected endpoints (new code not yet secured).
# These are tracked so the test passes today while flagging any NEW
# unprotected files. Remove entries as auth is added.
# 2026-07-04: emptied — taxonomy.py, library.py, and agents/libraries.py
# now carry require_scope on every handler; tests.py no longer exists.
KNOWN_UNPROTECTED: set[str] = set()


def _find_route_files() -> list[Path]:
    """Discover all Python files in the API directory."""
    return sorted(API_DIR.rglob("*.py"))


def _get_relative(filepath: Path) -> str:
    """Get path relative to API_DIR, using forward slashes."""
    return str(filepath.relative_to(API_DIR))


def _file_has_routes(source: str) -> bool:
    """Check if a Python file defines any route handlers via @router decorators."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                # Match @router.get(...), @router.post(...), etc.
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in ROUTE_DECORATORS
                ):
                    return True
    return False


def _file_has_require_scope(source: str) -> bool:
    """Check if a file references require_scope anywhere in its source."""
    return "require_scope" in source


def test_all_route_files_have_require_scope():
    """
    Every API route file (except exempt ones) must use require_scope.

    New files without require_scope will fail this test, forcing the
    developer to either add auth or explicitly add to KNOWN_UNPROTECTED
    (with a plan to fix).
    """
    missing = []

    for filepath in _find_route_files():
        rel = _get_relative(filepath)

        # Skip exempt files
        if rel in EXEMPT_FILES:
            continue

        # Skip known unprotected (tracked separately)
        if rel in KNOWN_UNPROTECTED:
            continue

        source = filepath.read_text()

        # Skip files with no route handlers
        if not _file_has_routes(source):
            continue

        # This file has routes — it must have require_scope
        if not _file_has_require_scope(source):
            missing.append(rel)

    assert not missing, (
        f"API route files missing require_scope (add auth or update "
        f"EXEMPT_FILES/KNOWN_UNPROTECTED with justification):\n"
        + "\n".join(f"  - {f}" for f in missing)
    )


def test_known_unprotected_still_unprotected():
    """
    Catch stale KNOWN_UNPROTECTED entries — if auth was added, remove
    the file from the known list so it stays protected.
    """
    now_protected = []

    for rel in sorted(KNOWN_UNPROTECTED):
        filepath = API_DIR / rel
        if not filepath.exists():
            continue

        source = filepath.read_text()
        if _file_has_require_scope(source):
            now_protected.append(rel)

    assert not now_protected, (
        f"These files now have require_scope — remove them from "
        f"KNOWN_UNPROTECTED in test_auth_scope_lint.py:\n"
        + "\n".join(f"  - {f}" for f in now_protected)
    )


def test_exempt_files_exist():
    """
    Catch stale EXEMPT_FILES entries — if a file was removed, clean up
    the exemption list.
    """
    stale = []

    for rel in sorted(EXEMPT_FILES):
        filepath = API_DIR / rel
        if not filepath.exists():
            stale.append(rel)

    # Filter to only files that aren't __init__.py (those may come and go)
    stale = [f for f in stale if not f.endswith("__init__.py")]

    assert not stale, (
        f"Exempt files no longer exist — remove from EXEMPT_FILES:\n"
        + "\n".join(f"  - {f}" for f in stale)
    )
