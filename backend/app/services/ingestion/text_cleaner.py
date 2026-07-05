"""
Text cleaner for ingestion enrichment pipeline.

Removes PDF artifacts, normalizes whitespace, and detects presentation-style
documents using a scoring algorithm ported from the n8n enrichment pipeline.
"""
import re
from pathlib import Path
from typing import TypedDict

import structlog

logger = structlog.get_logger()

# Filename keywords that suggest a presentation
PRESENTATION_KEYWORDS = {"qbr", "gtm", "blueprint", "deck", "slides", "palooza"}

# Regex patterns for artifact removal
_MACOS_VERSION_RE = re.compile(
    r"Mac OS X \d+\.\d+(?:\.\d+)?\s+Quartz PDFContext", re.IGNORECASE
)
_ADOBE_RE = re.compile(
    r"Adobe\s+(?:PDF Library|Systems|Acrobat)[^\n]*", re.IGNORECASE
)
_COPYRIGHT_RE = re.compile(
    r"(?:©|\bCopyright\b)[^\n]{0,120}", re.IGNORECASE
)
_CONFIDENTIAL_RE = re.compile(
    r"\bConfidential\b[^\n]{0,80}", re.IGNORECASE
)
_TIME_PATTERN_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", re.IGNORECASE)
_SLIDE_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*$", re.MULTILINE)
_ORDINAL_ARTIFACT_RE = re.compile(
    r"\b(\d+)\s*(st|nd|rd|th)\b", re.IGNORECASE
)


class CleanResult(TypedDict):
    text: str
    document_type: str
    presentation_score: int


def clean_text(raw_text: str, filename: str = "") -> CleanResult:
    """
    Clean extracted document text and detect its type.

    Steps:
    1. Remove macOS/Adobe PDF artifacts
    2. Deduplicate confidentiality/copyright notices
    3. Normalize whitespace
    4. Score for presentation detection
    5. Apply presentation-specific cleanup if score >= 50

    Returns a CleanResult dict with keys: text, document_type, presentation_score.
    """
    text = raw_text

    # --- Phase 1: Remove PDF artifacts ---
    text = _MACOS_VERSION_RE.sub("", text)
    text = _ADOBE_RE.sub("", text)

    # --- Phase 2: Deduplicate notices ---
    # Keep first occurrence of repeated copyright/confidential lines
    text = _deduplicate_pattern(text, _COPYRIGHT_RE, keep=1)
    text = _deduplicate_pattern(text, _CONFIDENTIAL_RE, keep=1)

    # --- Phase 3: Normalize whitespace ---
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple spaces to single (but not newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = text.strip()

    # --- Phase 4: Presentation scoring ---
    score = _score_presentation(raw_text, filename)

    # --- Phase 5: Presentation-specific cleanup ---
    document_type = "standard"
    if score >= 50:
        document_type = "presentation"
        text = _clean_presentation(text)

    logger.debug(
        "Text cleaned",
        filename=filename,
        original_len=len(raw_text),
        cleaned_len=len(text),
        document_type=document_type,
        presentation_score=score,
    )

    return CleanResult(
        text=text,
        document_type=document_type,
        presentation_score=score,
    )


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _deduplicate_pattern(text: str, pattern: re.Pattern, keep: int = 1) -> str:
    """Remove repeated matches of pattern, keeping only the first `keep` occurrences."""
    matches = list(pattern.finditer(text))
    if len(matches) <= keep:
        return text

    # Remove all occurrences after the first `keep`
    # Work backwards so indices stay valid
    for match in reversed(matches[keep:]):
        text = text[: match.start()] + text[match.end():]
    return text


def _score_presentation(text: str, filename: str) -> int:
    """
    Score a document on the likelihood it is a presentation slide deck.

    Scoring rubric:
    - Bullet count > 15:                   +25 pts
    - Bullet count > 8:                    +15 pts
    - Copyright/Confidential repetition > 5: +30 pts
    - Copyright/Confidential repetition > 2: +15 pts
    - Time patterns (HH:MM AM/PM):         +20 pts
    - Short average line length (< 40):    +15 pts
    - Filename keywords:                   +10 pts each
    """
    score = 0

    # Bullet/list item count
    bullet_count = len(re.findall(r"^[\s]*[•\-\*◦▪▸►]", text, re.MULTILINE))
    if bullet_count > 15:
        score += 25
    elif bullet_count > 8:
        score += 15

    # Repeated copyright/confidential notices
    copyright_count = len(_COPYRIGHT_RE.findall(text)) + len(_CONFIDENTIAL_RE.findall(text))
    if copyright_count > 5:
        score += 30
    elif copyright_count > 2:
        score += 15

    # Time patterns (common in meeting notes / slides)
    if _TIME_PATTERN_RE.search(text):
        score += 20

    # Short average line length
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if lines:
        avg_len = sum(len(ln.strip()) for ln in lines) / len(lines)
        if avg_len < 40:
            score += 15

    # Filename keyword hints
    stem = Path(filename).stem.lower() if filename else ""
    for keyword in PRESENTATION_KEYWORDS:
        if keyword in stem:
            score += 10

    return score


def _clean_presentation(text: str) -> str:
    """Apply extra cleanup rules for detected presentations."""
    # Remove lone slide numbers (a line containing only 1-3 digits)
    text = _SLIDE_NUMBER_RE.sub("", text)

    # Fix ordinal spacing artifacts: "2 n d" → "2nd", "1 s t" → "1st"
    text = re.sub(r"\b(\d+)\s+([nsrt])\s+(t|d|h)\b", r"\1\2\3", text, flags=re.IGNORECASE)

    # Fix standard ordinal spacing: "2 nd" → "2nd"
    text = _ORDINAL_ARTIFACT_RE.sub(r"\1\2", text)

    # Re-normalize whitespace after presentation cleanup
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text
