"""Pure helpers for YouTube transcript handling (#133).

Kept free of network / subprocess / DB so they can be unit-tested in isolation:
- ``clean_vtt``     : WebVTT (incl. messy auto-captions) -> clean running text
- ``rank_vtt_path`` : prefer manual English subs over auto-generated
- ``looks_like_block`` : distinguish a rate-limit/anti-bot block from "no captions"
- ``date_facets``   : derive filterable date fields from a yt-dlp upload_date
"""
from __future__ import annotations

import html
import re

# Inline tags: <00:00:00.200>, <c>, </c>, <c.colorXXXX> etc.
_INLINE_TAG_RE = re.compile(r"<[^>]+>")
# A cue timing line: "00:00:01.470 --> 00:00:02.150 align:start position:0%"
_TIMING_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
# Collapse runs of whitespace
_WS_RE = re.compile(r"\s+")
# Leading speaker carets ">>" / "&gt;&gt;" (after entity decode)
_SPEAKER_RE = re.compile(r"^>>+\s*")

# Substrings that indicate yt-dlp was blocked/throttled rather than the video
# simply having no captions. Used to avoid silently marking real content
# "skipped (no captions)" on a bad day.
_BLOCK_SIGNATURES = (
    "sign in to confirm",
    "not a bot",
    "http error 429",
    "too many requests",
    "http error 403",
    "this content isn't available",
    "blocked it in your country",
    "failed to extract any player response",
)


def looks_like_block(stderr: str) -> bool:
    """True if yt-dlp stderr looks like an anti-bot / rate-limit block."""
    low = (stderr or "").lower()
    return any(sig in low for sig in _BLOCK_SIGNATURES)


def date_facets(upload_date: str | None) -> dict:
    """Derive filterable date fields from a yt-dlp ``upload_date`` (``YYYYMMDD``).

    Returns a dict suitable for merging into a chunk's nested ``metadata`` so the
    transcript becomes filterable by publish date:

        published_date  (int)  20260503    — sortable/rangeable YYYYMMDD
        published_year  (int)  2026        — exact / MatchAny
        published_month (str)  "2026-05"   — exact / MatchAny

    Returns ``{}`` when the input is missing or not a valid 8-digit date, so
    callers can ``dict.update(...)`` unconditionally. Input is a structured
    field from yt-dlp metadata — never transcript prose — and is validated
    strictly here regardless.
    """
    if not upload_date:
        return {}
    s = str(upload_date).strip()
    if not re.fullmatch(r"\d{8}", s):
        return {}
    month = int(s[4:6])
    day = int(s[6:8])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return {}
    return {
        "published_date": int(s),
        "published_year": int(s[:4]),
        "published_month": f"{s[:4]}-{s[4:6]}",
    }


def rank_vtt_path(path: str) -> tuple:
    """Sort key: prefer manual English (``*.en.vtt``) over auto (``*.en-orig.vtt``).

    Lower sorts first. Manual subtitle files use the bare language tag
    (``<id>.en.vtt``); auto-captions carry a suffix (``<id>.en-orig.vtt``,
    ``<id>.en-US.vtt``). We prefer the cleaner manual track when both exist.
    """
    low = path.lower()
    if re.search(r"\.en\.vtt$", low):
        return (0, low)
    if re.search(r"\.en[-.]", low):
        return (1, low)
    return (2, low)


def clean_vtt(raw: str) -> str:
    """Convert a WebVTT caption file to clean running text.

    Strips the WEBVTT header, NOTE/Kind/Language metadata, cue numbers, cue
    timing lines, inline timestamp/``<c>`` tags, and HTML entities. Then
    removes the rolling-window duplication that auto-captions emit (each cue
    repeats the previous cue's tail), producing readable prose suitable for
    chunking + embedding.
    """
    lines: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "WEBVTT" or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if "-->" in line and _TIMING_RE.match(line):
            continue
        if line.isdigit():  # cue sequence number
            continue
        line = _INLINE_TAG_RE.sub("", line)
        line = html.unescape(line)
        line = _SPEAKER_RE.sub("", line).strip()
        if not line:
            continue
        line = _WS_RE.sub(" ", line)
        # Drop exact consecutive duplicates (the most common rolling artifact)
        if lines and lines[-1] == line:
            continue
        lines.append(line)

    # Second pass: drop a line when the next line is a strict superset that
    # starts with it (auto-caption carryover that grows word-by-word).
    deduped: list[str] = []
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if nxt is not None and nxt != line and nxt.startswith(line):
            continue
        deduped.append(line)

    text = " ".join(deduped)
    return _WS_RE.sub(" ", text).strip()
