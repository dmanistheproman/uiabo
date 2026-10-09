"""Exact-span decomposition never turns scope qualifications into assertions."""

import pytest

from app.pipeline.shared.components import component_queries, decompose_claim, component_discovery_anchor


CLAIM = ("Government officials are discussing raising the retirement age to 75 "
         "because CPF reserves are running out faster than expected.")


def test_discussion_and_financial_premise_have_separate_current_scope():
    parts = decompose_claim(CLAIM)
    assert [part.component_id for part in parts] == ["event", "premise", "causal_link"]
    assert [part.kind for part in parts] == ["event", "premise", "causal_link"]
    assert parts[0].text == "Government officials are discussing raising the retirement age to 75"
    assert parts[1].text == "CPF reserves are running out faster than expected."
    assert parts[2].text == CLAIM
    assert all(part.material and part.time_scope == "current" for part in parts)
    assert all(part.text in CLAIM for part in parts)


@pytest.mark.parametrize("connector", ["because", "because of", "due to", "owing to", "as a result of"])
def test_general_causal_markers_are_not_specific_to_retirement_claim(connector):
    text = f"The airport cancelled flights {connector} an engine supply shortage."
    parts = decompose_claim(text)
    assert len(parts) == 3
    assert parts[1].text == "an engine supply shortage."
    assert all(part.text in text for part in parts)


@pytest.mark.parametrize("text", [
    "Government officials are discussing raising the retirement age to 75.",
    "If officials raise the retirement age because CPF reserves are falling, people will object.",
    "Officials might raise the retirement age because CPF reserves are falling.",
    "Officials are not raising the retirement age because CPF reserves are falling.",
    "Officials are raising the retirement age because CPF reserves are not growing.",
    "Officials say the retirement age will rise because CPF reserves are falling.",
    'A message says "Officials are raising retirement age because reserves are falling."',
    '"Officials are raising retirement age because reserves are falling."',
    "Officials are raising retirement age because reserves are falling because investment returns fell.",
    "Are officials raising retirement age because reserves are falling?",
    "Officials are raising retirement age because they are running out of money.",
    "Because reserves are falling, officials are raising retirement age.",
    "Officials are raising retirement age. CPF reserves are falling because returns fell.",
])
def test_ambiguous_or_unasserted_scope_stays_with_whole_claim(text):
    assert decompose_claim(text) == []
    assert component_queries(text) == []


def test_possessive_qualifiers_and_explicit_period_remain_literal():
    text = "In 2024 the council raised its levy because the council’s maintenance costs had doubled."
    parts = decompose_claim(text)
    assert len(parts) == 3
    assert parts[0].time_scope == "stated"
    assert "council’s" in parts[1].text
    assert parts[1].time_scope == "unspecified"
    assert all(part.text in text for part in parts)


@pytest.mark.parametrize("prefix", ["In 2020 ", "Next year "])
def test_explicit_discussion_period_overrides_present_tense_default(prefix):
    parts = decompose_claim(prefix + CLAIM)
    assert parts[0].time_scope == "stated"
    assert parts[2].time_scope == "stated"


def test_discovery_queries_cover_both_parts_without_inventing_a_verdict():
    event, premise = component_queries(CLAIM)
    assert "retirement age to 75" in event
    assert "CPF reserves are running out faster than expected" in premise
    assert "financial statements" in premise
    assert all("Singapore Central Provident Fund (CPF)" in query for query in (event, premise))
    assert "75" not in premise
    assert all("false" not in query and "misinformation" not in query for query in (event, premise))


def test_query_length_limit_does_not_truncate_qualifiers():
    text = "The council has raised its levy because " + "maintenance costs " * 40 + "doubled."
    assert decompose_claim(text)
    assert component_queries(text) == []


@pytest.mark.parametrize("text", [
    "CPF stock will improve retirement savings because corporate reserves are growing.",
    "Central Pacific CPF retirement shares are declining because financial reserves are shrinking.",
    "CPF Foods will raise retirement payments because company reserves are growing.",
    "Brazil is raising its retirement age because CPF reserves are declining.",
    "Malaysia is raising its retirement age because CPF reserves are declining.",
    "CPF assets are declining because investment returns are falling.",
])
def test_acronym_expansion_does_not_replace_another_entity_or_country(text):
    assert "Central Provident Fund" not in component_discovery_anchor(text)
    assert all("Central Provident Fund" not in query for query in component_queries(text))


def test_explicit_country_survives_premise_focused_discovery():
    claim = "Canada is raising its retirement age because public pension reserves are declining."
    queries = component_queries(claim)
    assert len(queries) == 2
    assert all("Canada" in query for query in queries)
    assert "Singapore" not in " ".join(queries)
