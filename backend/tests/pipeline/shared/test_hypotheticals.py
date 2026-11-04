import pytest
from app.pipeline.shared.interpretation import input_intent
from app.pipeline.claim_analysis.pool_v3 import analyse_claim_v3
from app.pipeline.input_preparation.service import prepare_text


@pytest.mark.parametrize('text', [
    'What if Singapore reached 50 degrees Celsius?',
    'What would happen if all MRT rides were free?',
    'Imagine Changi Airport closed for a week. How would travellers be affected?',
    'If CPF did not exist, how would people save for retirement?',
    'How would people travel if all buses stopped running?',
])
def test_pure_hypotheticals_skip_external_claim_calls(text, monkeypatch):
    monkeypatch.setattr('app.pipeline.claim_analysis.pool_v3._keys', lambda: pytest.fail('No provider needed'))
    assert input_intent(text) == 'hypothetical'
    claim = analyse_claim_v3(prepare_text(text))
    assert claim.checkable is False


@pytest.mark.parametrize('text', [
    'Will Singapore reach 50 degrees Celsius tomorrow?',
    'Could Singapore reach 50 degrees Celsius tomorrow?',
    'Is the retirement age 75?',
    'What if all buses stopped? The MRT will close tomorrow.',
    'Imagine free MRT rides, but the government announced a new fare yesterday.',
    'If my passport has six months left, can I enter Singapore?',
    'What happens if I travel with an expired passport?',
])
def test_factual_questions_and_mixed_messages_are_not_pure_hypotheticals(text):
    assert input_intent(text) != 'hypothetical'
