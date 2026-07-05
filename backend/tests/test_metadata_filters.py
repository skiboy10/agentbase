"""Unit tests for build_metadata_filter — focuses on the date-facet additions
(range queries, numeric exact match, bool guard) plus existing list/str shapes.
"""
from qdrant_client import models

from app.services.rag.filters import build_metadata_filter, FILTERABLE_FIELDS


def _conds(f):
    return list(f.must or [])


def test_published_date_range_emits_range_condition():
    f = build_metadata_filter({"published_date": {"gte": 20260101, "lte": 20261231}})
    conds = _conds(f)
    assert len(conds) == 1
    c = conds[0]
    assert c.key == "metadata.published_date"
    assert isinstance(c.range, models.Range)
    assert c.range.gte == 20260101 and c.range.lte == 20261231


def test_published_year_int_emits_exact_match():
    f = build_metadata_filter({"published_year": 2026})
    c = _conds(f)[0]
    assert c.key == "metadata.published_year"
    assert isinstance(c.match, models.MatchValue) and c.match.value == 2026


def test_published_month_list_emits_matchany():
    f = build_metadata_filter({"published_month": ["2026-04", "2026-05"]})
    c = _conds(f)[0]
    assert c.key == "metadata.published_month"
    assert isinstance(c.match, models.MatchAny)
    assert set(c.match.any) == {"2026-04", "2026-05"}


def test_partial_range_bounds_ok():
    f = build_metadata_filter({"published_date": {"gte": 20260101}})
    c = _conds(f)[0]
    assert c.range.gte == 20260101 and c.range.lte is None


def test_empty_range_dict_yields_no_condition():
    assert build_metadata_filter({"published_date": {}}) is None


def test_bool_value_is_ignored_not_matched_as_int():
    # bool is a subclass of int; it must be skipped, not treated as 0/1.
    assert build_metadata_filter({"published_year": True}) is None


def test_range_drops_non_numeric_bounds():
    # A string bound must be dropped at build time, not passed into Qdrant.
    f = build_metadata_filter({"published_date": {"gte": "oops", "lte": 20261231}})
    c = _conds(f)[0]
    assert c.range.gte is None and c.range.lte == 20261231


def test_range_all_non_numeric_yields_no_condition():
    assert build_metadata_filter({"published_date": {"gte": "x", "lte": None}}) is None


def test_combined_filters_and_together():
    f = build_metadata_filter({
        "published_year": 2026,
        "platforms": ["AcmeCRM"],
    })
    keys = {c.key for c in _conds(f)}
    assert keys == {"metadata.published_year", "metadata.platforms"}


def test_date_fields_registered():
    for k in ("published_date", "published_year", "published_month"):
        assert k in FILTERABLE_FIELDS
