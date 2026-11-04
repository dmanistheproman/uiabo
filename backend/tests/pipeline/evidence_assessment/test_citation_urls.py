"""Only the known OpenAI tracking pair may relax exact citation identity."""

import re

import pytest

from app.pipeline.evidence_assessment.citation_urls import (
    citation_comparison_key,
    citation_match_kind,
    url_fingerprint,
)


@pytest.mark.parametrize("url", [
    "https://example.com/article",
    "https://example.com/article?id=42",
    "https://example.com/article?utm_source=openai",
    "https://example.com/article?id=42&utm_source=openai&id=43",
])
def test_identical_citations_match_exactly_even_with_tracking(url):
    assert citation_match_kind(url, url) == "exact"


@pytest.mark.parametrize("clean,tracked", [
    ("https://example.com/article", "https://example.com/article?utm_source=openai"),
    ("https://example.com/article?id=42", "https://example.com/article?id=42&utm_source=openai"),
    ("https://example.com/article?id=42", "https://example.com/article?utm_source=openai&id=42"),
    ("https://example.com/article?id=42&edition=2",
     "https://example.com/article?id=42&utm_source=openai&edition=2"),
    ("https://example.com/article", "https://example.com/article?%75tm_source=op%65nai"),
    ("https://example.com/article", "https://example.com/article?utm%5Fsource=%6Fpenai"),
    ("https://example.com/article",
     "https://example.com/article?utm_source=openai&utm_source=openai"),
    ("https://example.com/article?utm_source=publisher",
     "https://example.com/article?utm_source=openai&utm_source=publisher"),
])
def test_known_tracking_pair_matches_in_both_directions(clean, tracked):
    assert citation_comparison_key(tracked) == clean
    assert citation_match_kind(clean, tracked) == "tracking_alias"
    assert citation_match_kind(tracked, clean) == "tracking_alias"


@pytest.mark.parametrize("query", [
    "utm_source=other",
    "utm_source=OpenAI",
    "UTM_SOURCE=openai",
    "utm_source=openai+",
    "utm_source=+openai",
    "utm_source=openai%20",
    "utm_source=openai=extra",
    "utm_source=openai%26id%3D42",
    "utm_source=%256Fpenai",
    "utm_source",
    "utm_source=",
    "utm_medium=openai",
    "utm_campaign=openai",
    "source=openai",
    "id=42;utm_source=openai",
])
def test_unknown_or_near_matching_tracking_pairs_are_preserved(query):
    url = "https://example.com/article?" + query
    assert citation_comparison_key(url) == url
    assert citation_match_kind(url, "https://example.com/article") is None


@pytest.mark.parametrize("first,second", [
    ("https://example.com/article?id=42", "https://example.com/article?id=43"),
    ("https://example.com/article", "https://example.com/other-article"),
    ("https://example.com/article", "https://example.com/article/"),
    ("https://example.com/", "https://example.com"),
    ("https://example.com/article", "http://example.com/article"),
    ("https://example.com/article", "https://example.com:443/article"),
    ("http://example.com/article", "http://example.com:80/article"),
    ("https://example.com/article", "https://www.example.com/article"),
    ("https://example.com/article", "https://other.example.com/article"),
    ("https://example.com/article?id=42&lang=en", "https://example.com/article?lang=en&id=42"),
    ("https://example.com/article?id=42&id=43", "https://example.com/article?id=43&id=42"),
    ("https://example.com/article?id=42&id=42", "https://example.com/article?id=42"),
    ("https://example.com/article?id=%34%32", "https://example.com/article?id=42"),
    ("https://example.com/article?q=two+words", "https://example.com/article?q=two%20words"),
    ("https://example.com/article?id=42&empty=", "https://example.com/article?id=42"),
    ("https://example.com/article?flag", "https://example.com/article?flag="),
])
def test_substantive_url_differences_never_match(first, second):
    assert citation_match_kind(first, second) is None
    separator = "&" if "?" in first else "?"
    tracked = first + separator + "utm_source=openai"
    assert citation_match_kind(tracked, second) is None
    assert citation_match_kind(second, tracked) is None


def test_other_query_pairs_stay_byte_for_byte_and_in_original_order():
    url = ("https://example.com:443/article/?id=%34%32&utm_source=openai"
           "&id=43&q=two+words&empty=&flag&utm_source=publisher")
    expected = ("https://example.com:443/article/?id=%34%32"
                "&id=43&q=two+words&empty=&flag&utm_source=publisher")
    assert citation_comparison_key(url) == expected
    assert "utm_source=openai" in url  # The source/display value is retained.


@pytest.mark.parametrize("url,expected", [
    ("https://example.com/article?", "https://example.com/article?"),
    ("https://example.com/article?utm_source=openai&", "https://example.com/article?"),
    ("https://example.com/article?&utm_source=openai&&", "https://example.com/article?&&"),
    ("https://example.com/article?id=42&&utm_source=openai&", "https://example.com/article?id=42&&"),
    ("https://example.com/article?utm_source=openai#part", "https://example.com/article#part"),
    ("https://example.com/article#part?utm_source=openai", "https://example.com/article#part?utm_source=openai"),
])
def test_empty_pairs_and_fragments_are_not_normalized(url, expected):
    assert citation_comparison_key(url) == expected


def test_fingerprints_are_opaque_deterministic_and_distinguish_exact_urls():
    url = "https://example.com/article?id=42&utm_source=openai"
    fingerprint = url_fingerprint(url)
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert fingerprint == url_fingerprint(url)
    assert fingerprint != url_fingerprint(citation_comparison_key(url))
