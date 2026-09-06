"""
Auth scope lint check — ensures every API endpoint has require_scope.

Prevents "forgotten lock" regressions where new endpoints default to open.
Uses AST static analysis so no running server is needed.

Per-handler, not per-file: a file with one protected route must fail if
another handler in the same file is missing Depends(require_scope(...)).
"""
import ast
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
    # Agent query uses its own X-API-Key + agent-scoped auth
    "agents/query.py",
    # Router init files (no route handlers)
    "__init__.py",
    "agents/__init__.py",
    "sources/__init__.py",
    "projects/__init__.py",
    "auth/__init__.py",
}

# File-level known-unprotected list. Empty: new exemptions must be
# per-route (KNOWN_UNPROTECTED_ROUTES) so a sibling handler is still linted.
KNOWN_UNPROTECTED: set[str] = set()

# Per-route exemptions: (relative path from backend/app/api/, function name).
# Prefer this over file-level skips.
KNOWN_UNPROTECTED_ROUTES: set[tuple[str, str]] = {
    # First-key bootstrap: self-disables once any active key exists (409).
    # Intentionally unauthenticated — the only way to create the initial admin key.
    ("auth/routes.py", "bootstrap_api_key"),
}


def _find_route_files() -> list[Path]:
    """Discover all Python files in the API directory."""
    return sorted(API_DIR.rglob("*.py"))


def _get_relative(filepath: Path) -> str:
    """Get path relative to API_DIR, using forward slashes."""
    return str(filepath.relative_to(API_DIR))


def _is_route_decorator(node: ast.AST) -> bool:
    """Match @router.get(...), @router.post(...), etc."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return isinstance(func, ast.Attribute) and func.attr in ROUTE_DECORATORS


def _is_require_scope_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "require_scope":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "require_scope":
        return True
    return False


def _is_depends_require_scope(node: ast.AST) -> bool:
    """Match Depends(require_scope(...))."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    is_depends = (
        (isinstance(func, ast.Name) and func.id == "Depends")
        or (isinstance(func, ast.Attribute) and func.attr == "Depends")
    )
    if not is_depends:
        return False
    if any(_is_require_scope_call(arg) for arg in node.args):
        return True
    return any(_is_require_scope_call(kw.value) for kw in node.keywords)


def _subtree_has_depends_require_scope(node: ast.AST | None) -> bool:
    if node is None:
        return False
    for child in ast.walk(node):
        if _is_depends_require_scope(child):
            return True
    return False


def _handler_has_require_scope(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if this handler has Depends(require_scope(...)) on itself.

    Checks the function's decorator_list (e.g. dependencies=[...]) and
    its positional/keyword-only defaults (the FastAPI Depends() pattern).
    """
    for decorator in fn.decorator_list:
        if _subtree_has_depends_require_scope(decorator):
            return True
    for default in fn.args.defaults:
        if _subtree_has_depends_require_scope(default):
            return True
    for default in fn.args.kw_defaults:
        if _subtree_has_depends_require_scope(default):
            return True
    return False


def _iter_route_handlers(tree: ast.AST):
    """Yield (function_name, function_node) for @router.<method> handlers."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(_is_route_decorator(dec) for dec in node.decorator_list):
            yield node.name, node


def unprotected_handlers_in_source(source: str) -> list[str]:
    """Return names of route handlers missing Depends(require_scope(...))."""
    tree = ast.parse(source)
    missing = []
    for name, fn in _iter_route_handlers(tree):
        if not _handler_has_require_scope(fn):
            missing.append(name)
    return missing


def test_lint_detects_unprotected_sibling_handler():
    """A file with one protected route must fail if a sibling is open."""
    source = """
from fastapi import APIRouter, Depends
from app.core.auth import Scope, require_scope

router = APIRouter()

@router.get("/protected")
async def protected(_auth=Depends(require_scope(Scope.READ))):
    return {}

@router.post("/unprotected")
async def unprotected():
    return {}
"""
    assert unprotected_handlers_in_source(source) == ["unprotected"]


def test_lint_accepts_depends_on_decorator():
    """require_scope in the decorator's dependencies= list counts as protected."""
    source = """
from fastapi import APIRouter, Depends
from app.core.auth import Scope, require_scope

router = APIRouter()

@router.get("/x", dependencies=[Depends(require_scope(Scope.READ))])
async def via_decorator():
    return {}
"""
    assert unprotected_handlers_in_source(source) == []


def test_lint_accepts_kwonly_depends():
    source = """
from fastapi import APIRouter, Depends
from app.core.auth import Scope, require_scope

router = APIRouter()

@router.get("/x")
async def via_kwonly(*, _auth=Depends(require_scope(Scope.WRITE))):
    return {}
"""
    assert unprotected_handlers_in_source(source) == []


def test_all_route_handlers_have_require_scope():
    """
    Every @router.<method> handler (except documented exemptions) must
    have Depends(require_scope(...)) on that handler itself.
    """
    missing: list[str] = []

    for filepath in _find_route_files():
        rel = _get_relative(filepath)

        if rel in EXEMPT_FILES:
            continue
        if rel in KNOWN_UNPROTECTED:
            continue

        source = filepath.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for name, fn in _iter_route_handlers(tree):
            if (rel, name) in KNOWN_UNPROTECTED_ROUTES:
                continue
            if not _handler_has_require_scope(fn):
                missing.append(f"{rel}:{name}")

    assert not missing, (
        "API route handlers missing Depends(require_scope(...)) "
        "(add auth, or add (file, function) to KNOWN_UNPROTECTED_ROUTES "
        "with justification):\n"
        + "\n".join(f"  - {f}" for f in missing)
    )


def test_known_unprotected_routes_still_unprotected():
    """
    Catch stale per-route exemptions — if auth was added, remove the
    (file, function) pair so the handler stays protected.
    """
    now_protected = []
    missing_fn = []

    for rel, func_name in sorted(KNOWN_UNPROTECTED_ROUTES):
        filepath = API_DIR / rel
        if not filepath.exists():
            missing_fn.append(f"{rel}:{func_name} (file gone)")
            continue

        source = filepath.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        handlers = {name: fn for name, fn in _iter_route_handlers(tree)}
        fn = handlers.get(func_name)
        if fn is None:
            missing_fn.append(f"{rel}:{func_name} (function gone)")
            continue
        if _handler_has_require_scope(fn):
            now_protected.append(f"{rel}:{func_name}")

    assert not missing_fn, (
        "KNOWN_UNPROTECTED_ROUTES entries no longer exist — remove them:\n"
        + "\n".join(f"  - {f}" for f in missing_fn)
    )
    assert not now_protected, (
        "These handlers now have require_scope — remove them from "
        "KNOWN_UNPROTECTED_ROUTES in test_auth_scope_lint.py:\n"
        + "\n".join(f"  - {f}" for f in now_protected)
    )


def test_known_unprotected_still_unprotected():
    """
    Catch stale KNOWN_UNPROTECTED file-level entries — if auth was added,
    remove the file from the known list so it stays protected.
    """
    now_protected = []

    for rel in sorted(KNOWN_UNPROTECTED):
        filepath = API_DIR / rel
        if not filepath.exists():
            continue

        source = filepath.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        handlers = list(_iter_route_handlers(tree))
        if handlers and all(_handler_has_require_scope(fn) for _, fn in handlers):
            now_protected.append(rel)

    assert not now_protected, (
        f"These files now have require_scope on every handler — remove them "
        f"from KNOWN_UNPROTECTED in test_auth_scope_lint.py:\n"
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
