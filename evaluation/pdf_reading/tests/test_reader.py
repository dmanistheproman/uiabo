from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reader
from compare import EXPECTED, score_associations


def document():
    grouped = {}
    for metric, year, month, unit, value in EXPECTED:
        if metric not in grouped:
            grouped[metric] = dict(page=1, metric_label=metric, metric_type=metric,
                                   population_label='Fresh university graduates', points=[])
        grouped[metric]['points'].append(dict(date_label=f'{year}-{month:02}', year=year, month=month,
            value=value, unit=unit, cohort_label=f'{year} cohort'))
    return reader.DocumentRead(document_title='Synthetic regression copy of reviewed associations',
                               publication_label=None, series=list(grouped.values()), limitations=[])


def test_wrong_panel_is_detected_even_when_ocr_contains_every_number():
    value = document()
    unemployed = next(s for s in value.series if s.metric_type == 'unemployed_count')
    outside = next(s for s in value.series if s.metric_type == 'outside_labour_force_count')
    unemployed.points, outside.points = outside.points, unemployed.points
    ocr_text = ' '.join(row[4] for row in EXPECTED)
    assert all(p['present_in_ocr'] for p in reader.numeric_presence(value, ocr_text))
    score = score_associations(value)
    assert score['correct_associations'] == 8
    assert len(score['missing']) == 4 and len(score['unexpected']) == 4


def test_wrong_year_and_duplicate_points_are_not_counted_as_correct_extraction():
    value = document()
    value.series[0].points[0].year = 2026
    value.series[0].points.append(deepcopy(value.series[0].points[1]))
    score = score_associations(value)
    assert score['correct_associations'] == 11 and score['duplicate_observations'] == 1


@pytest.mark.parametrize('change', ['wrong_unit', 'invented_field', 'impossible_percent', 'invalid_month'])
def test_invalid_structure_cannot_pass_validation(change):
    value = document().model_dump()
    if change == 'wrong_unit': value['series'][0]['points'][0]['unit'] = 'percent'
    elif change == 'invented_field': value['verdict'] = 'false'
    elif change == 'impossible_percent': value['series'][-1]['points'][0]['value'] = '101'
    else: value['series'][0]['points'][0]['month'] = 13
    with pytest.raises(ValidationError): reader.DocumentRead.model_validate(value)


def test_number_corroboration_requires_complete_values():
    assert Decimal('4300') in reader.literal_numbers('4,300 people; 39.0%')
    assert Decimal('43') not in reader.literal_numbers('4,300 people; 39.0%')


def test_cache_avoids_another_paid_call_and_changes_with_model_prompt_or_pdf(monkeypatch, tmp_path):
    calls = []
    def extract(content, key, model):
        calls.append(model)
        return {'document': document().model_dump(), 'usage': {}}
    monkeypatch.setattr(reader, 'read_gemini', extract)
    content = b'%PDF-synthetic cache test'
    first, reused = reader.run_cached(content, 'gemini', tmp_path, key='fake-key')
    second, reused_second = reader.run_cached(content, 'gemini', tmp_path, key='fake-key')
    assert not reused and reused_second and len(calls) == 1 and first == second
    assert 'fake-key' not in next(tmp_path.glob('*.json')).read_text()
    original = reader.cache_identity(content, 'gemini', 'model-a')
    assert reader.cache_identity(content, 'gemini', 'model-b') != original
    assert reader.cache_identity(content + b'changed', 'gemini', 'model-a') != original
    monkeypatch.setattr(reader, 'PROMPT', reader.PROMPT + ' new instructions')
    assert reader.cache_identity(content, 'gemini', 'model-a') != original


def test_failed_calls_are_not_cached_or_retried(monkeypatch, tmp_path):
    calls = []
    def fail(*args):
        calls.append(1)
        raise ValueError('Synthetic failed response')
    monkeypatch.setattr(reader, 'read_gemini', fail)
    with pytest.raises(ValueError): reader.run_cached(b'%PDF-test', 'gemini', tmp_path)
    assert calls == [1] and not list(tmp_path.glob('*.json'))


def test_non_pdf_and_oversize_input_rejected_before_provider_call(tmp_path):
    file = tmp_path / 'sample.pdf'
    file.write_bytes(b'not a PDF')
    with pytest.raises(ValueError): reader.checked_pdf(file)
    file.write_bytes(b'%PDF-' + b'x' * reader.MAX_PDF_BYTES)
    with pytest.raises(ValueError): reader.checked_pdf(file)


def test_unknown_reader_is_rejected():
    with pytest.raises(ValueError): reader.cache_identity(b'%PDF-test', 'unknown')
