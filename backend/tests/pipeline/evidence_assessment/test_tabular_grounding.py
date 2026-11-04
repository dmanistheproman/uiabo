from types import SimpleNamespace

import pytest

from app.pipeline.evidence_assessment.tabular_grounding import comparison_cells_match


def point(value, period, population='Singapore', measure='Unemployed people', unit='people'):
    return SimpleNamespace(value=value, period=period, population=population, measure=measure, unit=unit)


WIDE = '''Unemployed people by population.
| Population | 2024 | 2025 |
| --- | --- | --- |
| Singapore | 100 | 110 |
| Australia | 400 | 800 |'''


def test_valid_wide_year_columns():
    assert comparison_cells_match(WIDE,point('100','2024'),point('110','2025')) is True


def test_values_from_another_population_are_not_accepted():
    assert comparison_cells_match(WIDE,point('400','2024'),point('800','2025')) is False


def test_swapped_year_values_are_rejected():
    assert comparison_cells_match(WIDE,point('110','2024'),point('100','2025')) is False


def test_measure_rows_cannot_be_interchanged():
    text='''Singapore unemployment statistics.
| Measure | Unit | 2024 | 2025 |
| --- | --- | --- | --- |
| Unemployed | People | 100 | 110 |
| Unemployment rate | Percent | 2 | 4 |'''
    assert comparison_cells_match(text,point('100','2024',measure='Unemployed'),point('110','2025',measure='Unemployed')) is True
    assert comparison_cells_match(text,point('2','2024',measure='Unemployed'),point('4','2025',measure='Unemployed')) is False
    assert comparison_cells_match(text,point('2','2024',measure='Unemployment rate',unit='percent'),
                                  point('4','2025',measure='Unemployment rate',unit='percent')) is True


def test_long_form_year_rows_bind_measure_column():
    text='''Unemployed people and Employed people in Singapore.
| Year | Population | Unemployed people | Employed people |
| --- | --- | --- | --- |
| 2024 | Singapore | 100 | 400 |
| 2025 | Singapore | 110 | 800 |'''
    assert comparison_cells_match(text,point('100','2024'),point('110','2025')) is True
    assert comparison_cells_match(text,point('400','2024'),point('800','2025')) is False


def test_long_form_generic_value_with_measure_and_population_dimensions():
    text='''Annual official observations.
| Year | Population | Measure | Value |
| --- | --- | --- | --- |
| 2024 | Singapore | Unemployed people | 100 |
| 2025 | Singapore | Unemployed people | 110 |
| 2024 | Australia | Unemployed people | 400 |
| 2025 | Australia | Unemployed people | 800 |'''
    assert comparison_cells_match(text,point('100','2024'),point('110','2025')) is True
    assert comparison_cells_match(text,point('400','2024'),point('800','2025')) is False


def test_hierarchical_rows_preserve_gender_parent_and_do_not_use_child_as_total():
    text='''University Intake by discipline and sex.
| DataSeries | 2024 | 2025 |
| --- | --- | --- |
| Male | 100 | 110 |
|   Accountancy | 30 | 40 |
| Female | 200 | 220 |
|   Accountancy | 60 | 80 |'''
    p=lambda value,year:point(value,year,population='Male',measure='Accountancy',unit='people')
    assert comparison_cells_match(text,p('30','2024'),p('40','2025')) is True
    assert comparison_cells_match(text,p('60','2024'),p('80','2025')) is False
    total=lambda value,year:point(value,year,population='Male',measure='University Intake',unit='people')
    assert comparison_cells_match(text,total('100','2024'),total('110','2025')) is True
    assert comparison_cells_match(text,total('30','2024'),total('40','2025')) is False


def test_ambiguous_rows_do_not_choose_by_desired_value():
    text='''Unemployed people in Singapore.
| Year | Value |
| --- | --- |
| 2024 | 100 |
| 2024 | 400 |
| 2025 | 110 |
| 2025 | 800 |'''
    assert comparison_cells_match(text,point('400','2024'),point('800','2025')) is False


def test_non_table_prose_preserves_existing_literal_validation():
    assert comparison_cells_match('Singapore had 100 unemployed people in 2024 and 110 in 2025.',
                                  point('100','2024'),point('110','2025')) is None


def test_clipped_table_without_headers_is_not_prose():
    assert comparison_cells_match('| Singapore | 100 | 110 |\n| Australia | 400 | 800 |',
                                  point('100','2024'),point('110','2025')) is False


def test_unrelated_table_does_not_lend_prose_numbers_to_it():
    text='''Singapore unemployed people 100 in 2024 and 110 in 2025.
| Area | 2024 | 2025 |
| --- | --- | --- |
| Australia | 400 | 800 |'''
    assert comparison_cells_match(text,point('100','2024'),point('110','2025')) is False


def test_formatted_numbers_and_specific_period_headers():
    text='''Unemployed people in Singapore.
| Population | June 2024 | June 2025 |
| --- | --- | --- |
| Singapore | **1,000** | 1,100 |'''
    assert comparison_cells_match(text,point('1,000','June 2024'),point('1,100','June 2025')) is True
    assert comparison_cells_match(text,point('1,000','May 2024'),point('1,100','May 2025')) is False
