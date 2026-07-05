"""
Sub-source resolution for the search path.

A sub-source row in ``sources`` (``parent_source_id IS NOT NULL``) does not own
Qdrant chunks. When a caller passes a sub-source id to a search function, we
translate it into:

  - the parent root's id (which actually carries the chunks), and
  - an "overlay" dict ``{"path_prefix": [...], "path_excludes": [...]}`` that
    will be merged into the Qdrant Filter so the result set is scoped to the
    sub-source's subtree.

When two sub-sources of the same root are passed together, their path_prefixes
union (OR semantics via Qdrant MatchAny) so an agent bound to two sibling
folders (e.g. "ACME/Q4" and "ACME/Q3") sees the union of their subtrees.
Excludes likewise accumulate.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Source


async def resolve_source_ids(
    db: AsyncSession, source_ids: Optional[list[str]]
) -> tuple[Optional[list[str]], dict[str, dict]]:
    """Translate a mixed list of root + sub-source ids.

    Returns ``(root_ids, overlay_by_root)`` where:
      - ``root_ids`` is the deduplicated set of root source ids to search
        (preserves input order on first occurrence). ``None`` is passed through
        unchanged so callers can still say "no scoping".
      - ``overlay_by_root[root_id]`` is a dict
        ``{"path_prefix": [...], "path_excludes": [...]}`` with canonical
        ancestor paths from any sub-source that mapped to this root.
        Empty lists mean "no additional scoping for this root".
    """
    if not source_ids:
        return source_ids, {}

    stmt = select(Source).where(Source.id.in_(source_ids))
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    by_id = {s.id: s for s in rows}

    seen: set[str] = set()
    root_ids: list[str] = []
    overlay: dict[str, dict] = defaultdict(lambda: {"path_prefix": [], "path_excludes": []})

    for sid in source_ids:
        s = by_id.get(sid)
        if s is None:
            continue
        parent_id = getattr(s, "parent_source_id", None)
        if parent_id:
            # Sub-source: contribute prefix/excludes onto the parent's overlay.
            root_id = parent_id
            if root_id not in seen:
                seen.add(root_id)
                root_ids.append(root_id)
            if s.path_prefix:
                overlay[root_id]["path_prefix"].append(s.path_prefix)
            extra_excludes = s.path_excludes or []
            if extra_excludes:
                overlay[root_id]["path_excludes"].extend(extra_excludes)
        else:
            # Root source: searches its full scope. Even if a sub-source of
            # this root is also in the list, we *don't* narrow the root's
            # query — the root and the sub-source are separate scopes that
            # the caller asked for together (locked decision #1: overlap is
            # allowed). The overlay slot for this root stays empty so its
            # query is unscoped.
            if sid not in seen:
                seen.add(sid)
                root_ids.append(sid)
            # If the root has its own watcher-level path_excludes, those apply
            # to all queries against it.
            if getattr(s, "path_excludes", None):
                overlay[sid]["path_excludes"].extend(s.path_excludes)

    # Deduplicate prefix/exclude lists per root while preserving order
    for root_id, sl in overlay.items():
        sl["path_prefix"] = list(dict.fromkeys(sl["path_prefix"]))
        sl["path_excludes"] = list(dict.fromkeys(sl["path_excludes"]))

    return root_ids, dict(overlay)


def overlay_filters_for_root(
    overlay: dict[str, dict], root_id: str, base_filters: Optional[dict]
) -> Optional[dict]:
    """Merge the sub-source overlay for one root with a caller's base filters.

    Returns a new filters dict suitable for ``build_metadata_filter``. The
    overlay's path_prefix/path_excludes lists are added (or unioned with any
    same-named keys in ``base_filters``). When the overlay is empty and there
    are no base filters, returns the base filters unchanged.
    """
    root_overlay = overlay.get(root_id)
    if not root_overlay or (
        not root_overlay.get("path_prefix") and not root_overlay.get("path_excludes")
    ):
        return base_filters

    merged: dict = dict(base_filters) if base_filters else {}

    if root_overlay.get("path_prefix"):
        existing = merged.get("path_prefix")
        if isinstance(existing, str):
            existing = [existing]
        elif existing is None:
            existing = []
        merged["path_prefix"] = list(dict.fromkeys(list(existing) + list(root_overlay["path_prefix"])))

    if root_overlay.get("path_excludes"):
        existing = merged.get("path_excludes") or []
        if isinstance(existing, str):
            existing = [existing]
        merged["path_excludes"] = list(dict.fromkeys(list(existing) + list(root_overlay["path_excludes"])))

    return merged
