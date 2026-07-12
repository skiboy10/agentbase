"""
Agent skills API routes.

Serves the Claude Code / agent skills bundled with the repo (``.claude/skills/*``)
so users can discover and install them from the UI. Read-only: lists skill
metadata parsed from each ``SKILL.md`` frontmatter, returns a skill's markdown for
preview, and streams a zip archive of a skill directory for one-click install.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse

router = APIRouter()

# Directory / file names never included when walking a skill.
_IGNORED_NAMES = {"__pycache__", ".DS_Store"}


def get_skills_root() -> Path:
    """Locate the ``.claude/skills`` directory in Docker or local dev.

    In Docker the directory is bind-mounted read-only at
    ``/app/.claude/skills`` (see docker-compose.yml). Locally it lives at the
    repo root, four levels up from ``backend/app/api/skills.py``.
    """
    docker_path = Path("/app/.claude/skills")
    if docker_path.exists():
        return docker_path
    return Path(__file__).resolve().parents[3] / ".claude" / "skills"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract ``name`` and ``description`` from a SKILL.md YAML frontmatter block.

    Deliberately dependency-free (no PyYAML). Handles single-line ``key: value``
    pairs and folded/literal block scalars (``>-``, ``>``, ``|``, ``|-``) whose
    value spans indented continuation lines.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]

    result: dict[str, str] = {}
    key: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if key is not None:
            result[key] = " ".join(part.strip() for part in buf if part.strip()).strip()

    for line in block.split("\n"):
        stripped = line.strip()
        is_new_key = (
            ":" in line
            and not line[:1].isspace()
            and not stripped.startswith("#")
            and stripped != ""
        )
        if is_new_key:
            flush()
            raw_key, _, raw_val = line.partition(":")
            key = raw_key.strip()
            val = raw_val.strip()
            # Block-scalar indicator → value continues on indented lines.
            buf = [] if val in {">", ">-", "|", "|-", ""} else [val]
        elif key is not None:
            buf.append(stripped)
    flush()
    return result


def _skill_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        p for p in root.iterdir()
        if p.is_dir() and p.name not in _IGNORED_NAMES and (p / "SKILL.md").exists()
    )


def _resolve_skill_dir(slug: str) -> Path:
    """Return the validated directory for ``slug`` or raise 404.

    Guards against path traversal by requiring the slug to match a real
    immediate child directory of the skills root.
    """
    root = get_skills_root()
    for skill_dir in _skill_dirs(root):
        if skill_dir.name == slug:
            return skill_dir
    raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")


def _relative_files(skill_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(skill_dir.rglob("*")):
        if path.is_dir():
            continue
        if any(part in _IGNORED_NAMES for part in path.relative_to(skill_dir).parts):
            continue
        files.append(path)
    return files


def _skill_summary(skill_dir: Path) -> dict:
    meta = _parse_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    files = _relative_files(skill_dir)
    return {
        "slug": skill_dir.name,
        "name": meta.get("name", skill_dir.name),
        "description": meta.get("description", ""),
        "files": [str(f.relative_to(skill_dir)) for f in files],
        "file_count": len(files),
        "size_bytes": sum(f.stat().st_size for f in files),
    }


@router.get("")
async def list_skills():
    """List the agent skills bundled with this Agentbase instance."""
    root = get_skills_root()
    skills = [_skill_summary(d) for d in _skill_dirs(root)]
    return {"skills": skills}


@router.get("/{slug}")
async def get_skill(slug: str):
    """Get a single skill's metadata plus its SKILL.md content for preview."""
    skill_dir = _resolve_skill_dir(slug)
    summary = _skill_summary(skill_dir)
    summary["readme"] = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    return summary


@router.get("/{slug}/archive")
async def download_skill_archive(slug: str):
    """Stream a zip archive of the skill directory for one-click install.

    The archive contains the skill folder itself (``<slug>/SKILL.md`` etc.) so
    it unpacks directly into a ``.claude/skills/`` directory.
    """
    skill_dir = _resolve_skill_dir(slug)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in _relative_files(skill_dir):
            arcname = Path(slug) / file_path.relative_to(skill_dir)
            archive.write(file_path, arcname.as_posix())
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )
