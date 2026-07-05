"""Unit tests for the pure YouTube transcript helpers (#133).

These cover the deterministic VTT-cleaning logic — the part the spike flagged
as the one thing we had to get right — with no network or DB.
"""
from app.services.ingestion.indexers.youtube_transcript import (
    clean_vtt,
    rank_vtt_path,
    looks_like_block,
    date_facets,
)


# A realistic auto-caption VTT: header metadata, cue timings, inline word
# timestamps, &gt;&gt; speaker carets, and the rolling-window duplicate lines.
# Mirrors the actual shape captured during the spike.
SAMPLE_AUTO_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:00.830 align:start position:0%

How<00:00:00.200><c> do</c><00:00:00.320><c> I</c><00:00:00.400><c> sound?</c>

00:00:00.830 --> 00:00:00.840 align:start position:0%
How do I sound?


00:00:00.840 --> 00:00:01.470 align:start position:0%
How do I sound?
&gt;&gt; You<00:00:00.880><c> sound</c><00:00:01.080><c> perfect.</c>

00:00:01.470 --> 00:00:01.480 align:start position:0%
&gt;&gt; You sound perfect.

"""


def test_clean_vtt_produces_readable_prose():
    out = clean_vtt(SAMPLE_AUTO_VTT)
    assert out == "How do I sound? You sound perfect."


def test_clean_vtt_strips_structural_noise():
    out = clean_vtt(SAMPLE_AUTO_VTT)
    assert "WEBVTT" not in out
    assert "-->" not in out
    assert "<c>" not in out and "00:00:00" not in out
    assert "&gt;" not in out and ">>" not in out


def test_clean_vtt_dedupes_rolling_window():
    # The phrase appears in four cues but must survive exactly once.
    assert clean_vtt(SAMPLE_AUTO_VTT).count("How do I sound?") == 1


def test_clean_vtt_handles_srt_style_comma_timestamps():
    vtt = "WEBVTT\n\n00:00:01,000 --> 00:00:02,000\nHello world\n"
    assert clean_vtt(vtt) == "Hello world"


def test_clean_vtt_empty_input():
    assert clean_vtt("WEBVTT\n\n") == ""


def test_rank_vtt_path_prefers_manual_over_auto():
    paths = ["x.en-orig.vtt", "x.es.vtt", "x.en.vtt"]
    best = sorted(paths, key=rank_vtt_path)[0]
    assert best == "x.en.vtt"


def test_looks_like_block_detects_antibot_and_rate_limit():
    assert looks_like_block("ERROR: Sign in to confirm you're not a bot")
    assert looks_like_block("HTTP Error 429: Too Many Requests")
    # A genuine "no captions" outcome must NOT read as a block.
    assert not looks_like_block("WARNING: video does not have subtitles")
    assert not looks_like_block("")


def test_date_facets_valid():
    assert date_facets("20260503") == {
        "published_date": 20260503,
        "published_year": 2026,
        "published_month": "2026-05",
    }


def test_date_facets_invalid_or_missing_returns_empty():
    # Must be safe to dict-update unconditionally.
    assert date_facets(None) == {}
    assert date_facets("") == {}
    assert date_facets("NA") == {}
    assert date_facets("2026-05-03") == {}   # wrong shape
    assert date_facets("20261303") == {}     # month 13
    assert date_facets("20260500") == {}     # day 00
