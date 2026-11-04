"""A model's reading of PDF charts, kept separate from literal source quotations."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PdfPoint(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date_label: str = Field(min_length=1, max_length=120)
    year: int | None = Field(ge=1900, le=2200)
    month: int | None = Field(ge=1, le=12)
    value: str = Field(pattern=r'^\d+(?:\.\d+)?$', max_length=30)
    unit: Literal['people', 'percent', 'currency', 'other']
    cohort_label: str | None = Field(max_length=200)


class PdfSeries(BaseModel):
    model_config = ConfigDict(extra='forbid')
    page: int = Field(ge=1, le=5)
    metric_label: str = Field(min_length=1, max_length=200)
    metric_type: Literal['employed_count', 'unemployed_count', 'outside_labour_force_count',
                         'permanent_employment_share', 'employment_rate', 'unemployment_rate', 'other']
    population_label: str = Field(min_length=1, max_length=250)
    points: list[PdfPoint] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def units_and_dates(self):
        expected = ('people' if self.metric_type.endswith('_count') else
                    'percent' if self.metric_type.endswith(('_rate', '_share')) else None)
        if expected and any(p.unit != expected for p in self.points):
            raise ValueError('Measurement and units disagree')
        if expected == 'percent' and any(Decimal(p.value) > 100 for p in self.points):
            raise ValueError('Invalid percentage')
        dates = [(p.date_label, p.cohort_label) for p in self.points]
        if len(set(dates)) != len(dates):
            raise ValueError('Duplicate observation')
        return self


class PdfDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_title: str = Field(min_length=1, max_length=400)
    publication_label: str | None = Field(max_length=150)
    series: list[PdfSeries] = Field(max_length=20)
    limitations: list[str] = Field(max_length=30)

    @model_validator(mode='after')
    def bounded(self):
        if sum(len(s.points) for s in self.series) > 150 or any(len(x) > 500 for x in self.limitations):
            raise ValueError('PDF reading is too large')
        return self


class PdfReading(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['gemini-pdf-v1'] = 'gemini-pdf-v1'
    provider: Literal['gemini'] = 'gemini'
    model: str = Field(min_length=1, max_length=100)
    pdf_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    page_count: int = Field(ge=1, le=5)
    extracted_at: datetime
    # Corroborates tokens, not the model's spatial associations or source truth.
    validation: Literal['native_pdf_tokens'] = 'native_pdf_tokens'
    document: PdfDocument

    @model_validator(mode='after')
    def actual_pages(self):
        if any(s.page > self.page_count for s in self.document.series):
            raise ValueError('Reading cites a nonexistent page')
        return self


def assessment_context(reading):
    if reading is None:
        return ''
    return ('\n\nStructured PDF chart reading (Gemini; NOT a verbatim quotation). '
            'Numbers and labels were corroborated in native PDF text; chart/date associations '
            'remain model interpretations. Match the population, metric, dates and cohort. '
            'This adds no independent source and establishes no causal relationship. '
            'Never quote this reconstructed data as literal source prose.\n' + reading.document.model_dump_json())
