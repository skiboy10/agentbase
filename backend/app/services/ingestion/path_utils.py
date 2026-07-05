"""
Path normalisation helpers used by the sub-source filter overlay.

The contract:
- Every chunk written by directory/file-item indexers carries a payload field
  ``folder_ancestors``: a list of POSIX, NFC-normalised, no-trailing-slash
  absolute paths covering every parent folder of the chunk's source file.
- A sub-source's ``path_prefix`` (and any ``path_excludes``) is canonicalised
  with the same rules at create-time and at query-time so a literal
  ``MatchAny`` lookup against ``folder_ancestors`` is reliable.

Canonicalisation:
1. ``Path.resolve()`` once (resolves symlinks).
2. POSIX representation (``as_posix()``).
3. NFC unicode normalisation (Mac filesystems return NFD; sources from other
   systems return NFC — picking NFC keeps both decomposable forms in agreement).
4. Strip trailing slash, except for the root ``/``.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Iterable


def canonicalise_path(path: str | Path) -> str:
    """Return the canonical POSIX/NFC absolute path string.

    Resolves symlinks via ``Path.resolve()``. Non-existent paths still
    canonicalise (resolve() succeeds for non-existent paths and just makes them
    absolute), so this is safe to use on user-supplied prefixes that may not
    yet exist on disk.
    """
    p = Path(path).expanduser().resolve()
    s = p.as_posix()
    s = unicodedata.normalize("NFC", s)
    if len(s) > 1 and s.endswith("/"):
        s = s.rstrip("/")
    return s


def compute_folder_ancestors(file_path: str | Path, root: str | Path | None = None) -> list[str]:
    """Return every ancestor folder of ``file_path`` as canonical POSIX strings.

    The list runs from the immediate parent up to (and including) ``root`` when
    provided, otherwise up to the filesystem root. Both ``file_path`` and
    ``root`` are canonicalised first so they share representation.

    Example::

        compute_folder_ancestors("/OneDrive/Client/ACME/Q4/deck.pdf",
                                 root="/OneDrive")
        # → ["/OneDrive/Client/ACME/Q4",
        #    "/OneDrive/Client/ACME",
        #    "/OneDrive/Client",
        #    "/OneDrive"]
    """
    file_canon = canonicalise_path(file_path)
    file_p = Path(file_canon)

    root_canon = canonicalise_path(root) if root is not None else None

    ancestors: list[str] = []
    for parent in file_p.parents:
        parent_canon = unicodedata.normalize("NFC", parent.as_posix())
        if len(parent_canon) > 1 and parent_canon.endswith("/"):
            parent_canon = parent_canon.rstrip("/")
        ancestors.append(parent_canon)
        if root_canon is not None and parent_canon == root_canon:
            break

    return ancestors


def path_under(path: str | Path, root: str | Path) -> bool:
    """True when ``path`` is equal to or strictly nested under ``root`` (canonically)."""
    p = canonicalise_path(path)
    r = canonicalise_path(root)
    if p == r:
        return True
    return p.startswith(r.rstrip("/") + "/")


def normalise_excludes(excludes: Iterable[str] | None) -> list[str]:
    """Canonicalise a list of exclude prefixes; drops empties."""
    if not excludes:
        return []
    out: list[str] = []
    for ex in excludes:
        if not ex:
            continue
        out.append(canonicalise_path(ex))
    return out
